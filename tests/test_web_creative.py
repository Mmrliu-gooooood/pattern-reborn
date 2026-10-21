"""Offline tests of paid-job boundaries, local settings and actual artifacts."""
from datetime import UTC, datetime
from io import BytesIO
import json
from pathlib import Path
from threading import Event, RLock
import time
from zipfile import ZipFile

import pytest
from PIL import Image, ImageDraw

pytest.importorskip("fastapi")
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from pattern_reborn.domain import CategoryId, ProfileId, ProvenanceClass, StepId
from pattern_reborn.generation.base import FailureKind, GenerationFailure, ProviderId, RemoteGenerationResult
from pattern_reborn.generation.service import GenerationService, ProviderConfigCredentialResolver
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.projects import ProjectRepository
from pattern_reborn.workflow import CreateProjectCommand, ExtractCommand, PatternRebornService
from pattern_reborn.web_creative import register_creative_routes

ROOT = Path(__file__).resolve().parents[1]
SECRET = "sk-test-session-credential-do-not-persist"


class Adapter:
    def __init__(self):
        self.calls = []
        self.started = Event()
        self.release = Event()
        self.release.set()
        self.failure = None
        self.config = None
        self.output = None
        self.reference_bytes = None
        self.invalid_output = False

    def generate(self, request, credential):
        self.calls.append((request, credential.get_secret_value()))
        self.reference_bytes = request.reference_path.read_bytes()
        self.started.set()
        assert self.release.wait(10), "Test did not release fake provider"
        if self.failure:
            raise self.failure
        self.output.mkdir(parents=True, exist_ok=True)
        image = self.output / "actual-provider-output.png"
        if self.invalid_output:
            image.write_bytes(b"not-an-image")
        else:
            Image.new("RGBA", (96, 64), (13, 120, 91, 255)).save(image)
        return RemoteGenerationResult(provider=request.provider, model=request.model, prompt=request.prompt, local_files=[image])

    def factory(self, *, config, output_dir):
        self.config, self.output = config, output_dir
        return GenerationService({identifier: self for identifier in ProviderId}, ProviderConfigCredentialResolver(config), config=config)


@pytest.fixture
def creative(tmp_path, monkeypatch):
    for key in ("SEEDREAM_API_KEY", "QWEN_API_KEY", "SEEDREAM_BASE_URL", "QWEN_BASE_URL", "SEEDREAM_MODEL", "QWEN_MODEL", "OPENROUTER_API_KEY", "CUSTOM_API_KEY", "OPENROUTER_BASE_URL", "CUSTOM_BASE_URL", "OPENROUTER_MODEL", "CUSTOM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PATTERN_REBORN_DISABLE_OPTIONAL", "1")
    repository = ProjectRepository(tmp_path / "projects")
    catalog = KnowledgeCatalog.load(ROOT / "data/knowledge")
    output = tmp_path / "exports"
    source = tmp_path / "source.png"
    image = Image.new("RGBA", (128, 128), (255, 255, 255, 0))
    ImageDraw.Draw(image).rectangle((24, 24, 104, 104), fill=(190, 30, 35, 255))
    image.save(source)
    original = source.read_bytes()
    service = PatternRebornService(repository, knowledge=catalog, export_root=output)
    project = service.create_project(CreateProjectCommand(name="本地创作", source=source, category=CategoryId.PAPER_CUTTING,
                                                        provenance=ProvenanceClass.USER_SUPPLIED_UNVERIFIED))
    artifact = service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    project = service.confirm_extraction(project.id, artifact.artifact_id)
    lock = RLock()
    app = FastAPI()
    snapshots = []
    snapshot_fail = {"before": False, "after": False}

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(OSError)
    async def storage(request, error):
        return JSONResponse({"detail": "本地磁盘暂不可用"}, status_code=503)

    def current(project_id, revision):
        saved = repository.load(project_id)
        if saved.updated_at.isoformat() != revision:
            raise HTTPException(409, "版本冲突")
        return saved

    def public(project, detail=False):
        return {"id": project.id, "name": project.name, "revision": project.updated_at.isoformat(),
                "source_sha256": project.source.sha256,
                "exports": project.processing_parameters.get("web_workspace", {}).get("exports", [])}

    def safe_artifact(project, relative):
        base = repository.project_dir(project.id)
        path = (base / relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(base) or ".." in Path(relative).parts:
            raise HTTPException(400, "非法路径")
        if not path.is_file():
            raise HTTPException(404, "文件不存在")
        return path

    adapter = Adapter()

    def capture(project, label):
        snapshots.append((label, project.model_dump(mode="json")))
        if snapshot_fail["before" if "前" in label else "after"]:
            raise OSError("Fake snapshot disk failure")

    register_creative_routes(app, repository, catalog, lock, current, public, safe_artifact, output,
                             generation_factory=adapter.factory, auto_snapshot=capture, settings_path=tmp_path / '.private/provider-settings.json')
    with TestClient(app) as client:
        yield {"client": client, "app": app, "repository": repository, "service": service,
               "project": public(project), "adapter": adapter, "output": output, "original": original,
               "snapshots": snapshots, "snapshot_fail": snapshot_fail, "settings_path": tmp_path / '.private/provider-settings.json'}
    adapter.release.set()


def setup_key(state):
    response = state["client"].put("/api/settings", json={"provider": "seedream", "api_key": SECRET})
    assert response.status_code == 200, response.text
    return response.json()


def payload(state, **updates):
    settings = state['client'].get('/api/settings').json()
    revision = next(p['settings_revision'] for p in settings['providers'] if p['id'] == updates.get('provider', 'seedream'))
    return {"revision": state["project"]["revision"], "request_id": "test-request-1", "provider": "seedream",
            "settings_revision": revision,
            "prompt": "传统牡丹纹样", "size": "1024x1024", "structure_level": "high",
            "target_application": "textile", "colors": ["#B71C1C"], "mode": "byok", "paid_confirmed": True, **updates}


def submit(state, **updates):
    # Pick a real catalog color instead of tying tests to a mutable color value.
    updates.setdefault("colors", [])
    data = payload(state, **updates)
    response = state["client"].post(f'/api/projects/{state["project"]["id"]}/generation', json=data)
    return response, data


def wait_job(state, job):
    endpoint = f'/api/projects/{state["project"]["id"]}/generation/jobs/{job["id"]}'
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = state["client"].get(endpoint)
        assert response.status_code == 200, response.text
        result = response.json()
        if result["job"]["status"] not in {"queued", "running", "cancelling"}:
            return result
        time.sleep(0.01)
    pytest.fail("Fake generation did not finish")


def test_settings_keys_are_local_and_invalid_inputs_never_echo_them(creative):
    cookie = creative["client"].get("/api/settings").headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    result = setup_key(creative)
    seedream = next(p for p in result["providers"] if p["id"] == "seedream")
    assert seedream["session_credential"] and seedream["available"]
    assert not seedream["platform_credential"]
    assert SECRET not in json.dumps(result)
    with TestClient(creative["app"]) as other:
        providers = other.get("/api/settings").json()["providers"]
        assert next(p for p in providers if p['id'] == 'seedream')['stored_credential']
    invalid = creative["client"].put("/api/settings", json={"provider": "seedream", "api_key": SECRET, "base_url": "https://user:secret@example.org"})
    assert invalid.status_code == 400 and SECRET not in invalid.text and "user:secret" not in invalid.text
    for path in creative["repository"].workspace.rglob("*.json"):
        assert SECRET not in path.read_text(encoding="utf-8")
    cleared = creative["client"].put("/api/settings", json={"provider": "seedream", "api_key": ""}).json()
    assert not next(p for p in cleared["providers"] if p["id"] == "seedream")["session_credential"]


@pytest.mark.parametrize("change", [{"base_url": "http://example.org"}, {"base_url": "https://example.org/?api_key=secret"},
                                     {"base_url": "https://example.org/#secret"}, {"model": "model with spaces"},
                                     {"api_key": {"bad": "shape"}}])
def test_settings_validate_endpoint_model_and_key_without_remote_calls(creative, change):
    response = creative["client"].put("/api/settings", json={"provider": "seedream", **change})
    assert response.status_code == 400
    assert creative["adapter"].calls == []


@pytest.mark.parametrize("torch_installed,weights_present,disabled,available", [
    (False, True, False, False), (True, False, False, False),
    (True, True, False, True), (True, True, True, False),
])
def test_settings_mobile_sam_matches_editor_dependencies_and_weights(creative, monkeypatch, tmp_path,
        torch_installed, weights_present, disabled, available):
    import pattern_reborn.web_extraction as extraction

    model_root = tmp_path / "capability-probe"
    if weights_present:
        checkpoint = model_root / "models/mobile_sam/mobile_sam.pt"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(b"not-loaded-by-a-capability-probe")
    monkeypatch.setattr(extraction, "_root", lambda root: model_root)
    monkeypatch.setattr(extraction, "_installed", lambda module: module == "mobile_sam" or torch_installed)
    monkeypatch.setenv("PATTERN_REBORN_DISABLE_OPTIONAL", "1" if disabled else "0")
    expected = extraction.extraction_capabilities(ROOT)["mobile_sam"]
    actual = creative["client"].get("/api/settings").json()["capabilities"]["mobile_sam"]
    assert actual == expected
    assert actual["available"] is available
    assert not creative["adapter"].calls


def test_analysis_is_real_persisted_and_revision_checked(creative):
    client, project = creative["client"], creative["project"]
    endpoint = f'/api/projects/{project["id"]}'
    assert client.get(endpoint + "/analysis").json()["analysis"] is None
    response = client.post(endpoint + "/analyze", json={"revision": project["revision"]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["analysis"]["palette"] and result["analysis"]["contours"]
    assert result["analysis"]["algorithm"] == "opencv-baseline-1.0"
    assert result["project"]["revision"] != project["revision"]
    assert client.get(endpoint + "/analysis").json()["analysis"] == result["analysis"]
    assert client.post(endpoint + "/analyze", json={"revision": project["revision"]}).status_code == 409


def test_view_analysis_after_generation_and_mockup_preserves_current_artworks(creative):
    setup_key(creative)
    response, _ = submit(creative)
    result = wait_job(creative, response.json()["job"])
    assert result["job"]["status"] == "succeeded"
    client = creative["client"]
    endpoint = f'/api/projects/{creative["project"]["id"]}'
    context = client.get(endpoint + "/creative").json()
    generated = context["generations"][0]
    mocked = client.post(endpoint + "/mockups", json={"revision": result["project"]["revision"],
        "template_id": "bookmark", "artwork_id": generated["id"]})
    assert mocked.status_code == 200
    before = creative["repository"].load(creative["project"]["id"])
    assert not before.artifacts.analysis and not before.artifacts.recomposition
    assert StepId.ANALYSIS not in before.confirmed_steps
    generated_bytes = client.get(generated["url"]).content
    mockup_url = mocked.json()["mockup"]["url"]
    mockup_bytes = client.get(mockup_url).content
    analyzed = client.post(endpoint + "/analyze", json={"revision": before.updated_at.isoformat()})
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["analysis"]["palette"]
    after = creative["repository"].load(before.id)
    assert after.generations == before.generations
    assert after.artifacts.generation == before.artifacts.generation
    assert after.artifacts.recomposition == before.artifacts.recomposition
    assert after.artifacts.export == before.artifacts.export
    assert after.processing_parameters["current_mockups"] == before.processing_parameters["current_mockups"]
    assert after.processing_parameters["current_step"] == before.processing_parameters["current_step"]
    assert after.stale_artifacts == before.stale_artifacts
    assert StepId.GENERATION in after.confirmed_steps and StepId.ANALYSIS in after.confirmed_steps
    assert client.get(generated["url"]).content == generated_bytes
    assert client.get(mockup_url).content == mockup_bytes
    assert (creative["repository"].project_dir(after.id) / after.source.relative_path).read_bytes() == creative["original"]


def test_real_output_publish_provider_overrides_source_unchanged_and_duplicate(creative):
    setup_key(creative)
    settings = creative["client"].put("/api/settings", json={"provider": "seedream", "base_url": "https://provider.example/v1", "model": "test-model", "api_key": SECRET})
    assert settings.status_code == 200
    response, data = submit(creative)
    assert response.status_code == 202, response.text
    result = wait_job(creative, response.json()["job"])
    assert result["job"]["status"] == "succeeded", result
    adapter = creative["adapter"]
    assert len(adapter.calls) == 1 and adapter.calls[0][1] == SECRET
    extraction = creative["repository"].load(creative["project"]["id"]).artifacts.extraction[0]
    assert adapter.reference_bytes == (creative["repository"].project_dir(creative["project"]["id"]) / extraction).read_bytes()
    assert adapter.config.provider(ProviderId.SEEDREAM).base_url == "https://provider.example/v1"
    assert adapter.calls[0][0].model == "test-model"
    duplicate = creative["client"].post(f'/api/projects/{creative["project"]["id"]}/generation', json=data)
    assert duplicate.status_code == 202 and duplicate.json()["job"]["id"] == result["job"]["id"]
    assert len(adapter.calls) == 1
    endpoint = f'/api/projects/{creative["project"]["id"]}'
    context = creative["client"].get(endpoint + "/creative").json()
    generated = context["generations"][0]
    image = creative["client"].get(generated["url"])
    assert image.status_code == 200
    assert Image.open(BytesIO(image.content)).getpixel((0, 0)) == (13, 120, 91, 255)
    assert SECRET not in json.dumps(context)
    record = creative["repository"].load(creative["project"]["id"])
    assert StepId.GENERATION in record.confirmed_steps
    assert record.processing_parameters["generation"]["mode"] == "byok"
    assert record.processing_parameters['web_workspace']['creative_generations'][record.artifacts.generation[0]]['protocol'] == 'seedream_images'
    assert [label for label, _ in creative["snapshots"]] == ["AI 生成前的状态", "AI 生成作品保存"]
    assert not creative["snapshots"][0][1]["generations"] and len(creative["snapshots"][1][1]["generations"]) == 1
    assert SECRET not in json.dumps(creative["snapshots"])
    assert (creative["repository"].project_dir(record.id) / record.source.relative_path).read_bytes() == creative["original"]
    assert SECRET not in record.model_dump_json()
    conflict = creative["client"].post(endpoint + "/generation", json={**data, "prompt": "另一个请求"})
    assert conflict.status_code == 409 and len(adapter.calls) == 1


def test_paid_confirmation_credentials_size_and_reference_are_required(creative):
    for updates in ({"paid_confirmed": False}, {}, {"size": "9000x9000"}, {"reference_id": "../../source.png"}, {"model": "other-model"}):
        response, _ = submit(creative, **updates)
        assert response.status_code == 400, response.text
    assert not creative["adapter"].calls
    setup_key(creative)
    response, _ = submit(creative, reference_id="source/hidden.png")
    assert response.status_code == 400


def test_platform_credentials_reuse_environment_without_exposure(creative, monkeypatch):
    monkeypatch.setenv("SEEDREAM_API_KEY", SECRET)
    settings = creative["client"].get("/api/settings").json()
    provider = next(p for p in settings["providers"] if p["id"] == "seedream")
    assert provider["platform_credential"] and not provider["session_credential"]
    response, _ = submit(creative, mode="platform")
    result = wait_job(creative, response.json()["job"])
    assert result["job"]["status"] == "succeeded"
    assert creative["adapter"].calls[0][1] == SECRET
    record = creative["repository"].load(creative["project"]["id"])
    assert record.processing_parameters["generation"]["mode"] == "platform"
    assert SECRET not in json.dumps(settings) and SECRET not in record.model_dump_json()


def test_qwen_negative_and_color_controls_reach_provider_and_provenance(creative):
    client = creative["client"]
    settings = client.put("/api/settings", json={"provider": "qwen", "api_key": SECRET}).json()
    color = settings["options"]["colors"][0]["hex_value"]
    response, _ = submit(creative, provider="qwen", negative_constraints="不要文字", colors=[color])
    assert response.status_code == 202, response.text
    assert wait_job(creative, response.json()["job"])["job"]["status"] == "succeeded"
    request = creative["adapter"].calls[0][0]
    assert request.negative_constraints == "不要文字" and request.colors == [color]
    project = creative['repository'].load(creative['project']['id'])
    assert project.processing_parameters['web_workspace']['creative_generations'][project.artifacts.generation[0]]['protocol'] == 'qwen_multimodal'
    record = creative["repository"].load(creative["project"]["id"])
    metadata = record.processing_parameters["web_workspace"]["creative_generations"][record.generations[0].artifact_path]
    assert metadata["negative_constraints"] == "不要文字" and metadata["colors"] == [color]


def test_snapshot_failure_before_submission_prevents_paid_dispatch(creative):
    setup_key(creative)
    creative["snapshot_fail"]["before"] = True
    response, _ = submit(creative)
    assert response.status_code == 503
    assert not creative["adapter"].calls


def test_snapshot_failure_after_publication_keeps_successful_job(creative):
    setup_key(creative)
    creative["snapshot_fail"]["after"] = True
    response, _ = submit(creative)
    result = wait_job(creative, response.json()["job"])
    assert result["job"]["status"] == "succeeded" and "快照" in result["job"]["message"]
    assert creative["repository"].load(creative["project"]["id"]).generations


def test_malformed_provider_image_does_not_publish_or_mutate_source(creative):
    setup_key(creative)
    creative["adapter"].invalid_output = True
    before = creative["repository"].load(creative["project"]["id"]).model_dump_json()
    response, _ = submit(creative)
    result = wait_job(creative, response.json()["job"])
    assert result["job"]["status"] == "failed"
    assert creative["repository"].load(creative["project"]["id"]).model_dump_json() == before
    assert not list(creative["repository"].project_dir(creative["project"]["id"]).glob("generated/*.png"))


def test_queued_cancel_never_dispatches_remote_request(creative, monkeypatch):
    import pattern_reborn.web_creative as routes
    pending = []

    class DeferredThread:
        def __init__(self, *, target, args, **kwargs):
            pending.append((target, args))

        def start(self):
            pass

    monkeypatch.setattr(routes, "Thread", DeferredThread)
    setup_key(creative)
    response, _ = submit(creative)
    job = response.json()["job"]
    assert job["status"] == "queued"
    endpoint = f'/api/projects/{creative["project"]["id"]}/generation/jobs/{job["id"]}/cancel'
    cancelled = creative["client"].post(endpoint).json()["job"]
    assert cancelled["status"] == "cancelled"
    target, args = pending[0]
    target(*args)
    assert not creative["adapter"].calls
    assert wait_job(creative, job)["job"]["status"] == "cancelled"


def test_failed_remote_call_does_not_modify_project_and_retry_is_explicit(creative):
    setup_key(creative)
    adapter = creative["adapter"]
    adapter.failure = GenerationFailure(FailureKind.AUTH, f"remote leaked {SECRET}", SECRET)
    original = creative["repository"].load(creative["project"]["id"]).model_dump_json()
    response, data = submit(creative)
    result = wait_job(creative, response.json()["job"])
    assert result["job"]["status"] == "failed" and result["job"]["failure_kind"] == "auth"
    assert SECRET not in json.dumps(result)
    assert creative["repository"].load(creative["project"]["id"]).model_dump_json() == original
    duplicate = creative["client"].post(f'/api/projects/{creative["project"]["id"]}/generation', json=data)
    assert duplicate.json()["job"]["status"] == "failed" and len(adapter.calls) == 1
    adapter.failure = None
    retry, _ = submit(creative, request_id="test-request-2")
    assert wait_job(creative, retry.json()["job"])["job"]["status"] == "succeeded"
    assert len(adapter.calls) == 2


@pytest.mark.parametrize("action,expected", [("edit", "stale"), ("cancel", "cancelled")])
def test_stale_and_cancelled_jobs_never_publish(creative, action, expected):
    setup_key(creative)
    adapter = creative["adapter"]
    adapter.release.clear()
    response, _ = submit(creative)
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert adapter.started.wait(3)
    project = creative["repository"].load(creative["project"]["id"])
    original = project.model_dump_json()
    if action == "edit":
        project.name = "修改后的项目"
        project.updated_at = datetime.now(UTC)
        creative["repository"].save(project)
        original = project.model_dump_json()
    else:
        endpoint = f'/api/projects/{project.id}/generation/jobs/{job["id"]}/cancel'
        cancel = creative["client"].post(endpoint).json()["job"]
        assert cancel["status"] == "cancelling" and cancel["cancel_requested"]
        assert "计费" in cancel["message"]
    adapter.release.set()
    result = wait_job(creative, job)
    assert result["job"]["status"] == expected
    assert creative["repository"].load(project.id).model_dump_json() == original
    assert not list(creative["repository"].project_dir(project.id).glob("generated/*.png"))


def test_inflight_double_submit_and_job_session_ownership(creative):
    setup_key(creative)
    creative["adapter"].release.clear()
    first, data = submit(creative)
    assert creative["adapter"].started.wait(3)
    endpoint = f'/api/projects/{creative["project"]["id"]}/generation'
    repeated = creative["client"].post(endpoint, json=data)
    assert repeated.json()["job"]["id"] == first.json()["job"]["id"]
    different = creative["client"].post(endpoint, json={**data, "request_id": "test-request-2"})
    assert different.status_code == 409 and len(creative["adapter"].calls) == 1
    with TestClient(creative["app"]) as other:
        job_url = endpoint + "/jobs/" + first.json()["job"]["id"]
        assert other.get(job_url).status_code == 404
        assert other.post(job_url + "/cancel").status_code == 404
    creative["adapter"].release.set()
    assert wait_job(creative, first.json()["job"])["job"]["status"] == "succeeded"


def test_mockup_export_provenance_history_and_stale_artwork_allowlist(creative):
    setup_key(creative)
    response, _ = submit(creative)
    result = wait_job(creative, response.json()["job"])
    endpoint = f'/api/projects/{creative["project"]["id"]}'
    context = creative["client"].get(endpoint + "/creative").json()
    generated = context["generations"][0]
    assert creative["client"].get(context["templates"][0]["url"]).status_code == 200
    mockup = creative["client"].post(endpoint + "/mockups", json={"revision": result["project"]["revision"], "template_id": "bookmark", "artwork_id": generated["id"]})
    assert mockup.status_code == 200, mockup.text
    current = mockup.json()["project"]
    assert mockup.json()["mockup"]["ai_assisted"]
    assert creative["client"].get(mockup.json()["mockup"]["url"]).status_code == 200
    exported = creative["client"].post(endpoint + "/creative/exports", json={"revision": current["revision"], "artwork_id": generated["id"], "format": "zip"})
    assert exported.status_code == 200, exported.text
    export = exported.json()["export"]
    export_snapshots = [record for label, record in creative["snapshots"] if label == "作品导出保存"]
    assert export_snapshots[-1]["processing_parameters"]["web_workspace"]["exports"][0] == export
    path = creative["output"] / creative["project"]["id"] / export["id"] / export["filename"]
    immutable_bytes = path.read_bytes()
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert any(f["kind"] == "generation" and f["ai_assisted"] for f in manifest["files"])
        assert manifest["source"]["sha256"] == current["source_sha256"]
        assert "AI 辅助" in archive.read("provenance.md").decode("utf-8")
        assert SECRET.encode() not in b"".join(archive.read(p) for p in archive.namelist())
    project = creative["repository"].load(creative["project"]["id"])
    creative["repository"].confirm(project.id, StepId.EXTRACTION, project.artifacts.extraction)
    assert creative["client"].get(generated["url"]).status_code == 404
    assert creative["client"].get(mockup.json()["mockup"]["url"]).status_code == 404
    assert path.read_bytes() == immutable_bytes
    project = creative["repository"].load(project.id)
    assert project.processing_parameters["web_workspace"]["exports"][0] == export
    invalid = creative["client"].post(endpoint + "/creative/exports", json={"revision": project.updated_at.isoformat(), "artwork_id": generated["id"], "format": "png"})
    assert invalid.status_code == 400
    assert creative["client"].get(endpoint + "/artwork/arbitrary-path-token").status_code == 404


@pytest.mark.parametrize('provider,size', [('seedream', '1024x1024'), ('custom', '1024x1024'), ('openrouter', '1K')])
def test_real_web_app_generation_mockup_download_and_zip_roundtrip(creative, monkeypatch, provider, size):
    import pattern_reborn.web_creative as routes
    from pattern_reborn.web_api import create_app

    monkeypatch.setattr(routes, "build_generation_service", creative["adapter"].factory)
    monkeypatch.setenv("PATTERN_REBORN_OUTPUTS", str(creative["output"]))
    endpoint = f'/api/projects/{creative["project"]["id"]}'
    with TestClient(create_app(creative["repository"].workspace, settings_path=creative['settings_path']), headers={"X-Pattern-Reborn": "local-workspace"}) as client:
        state = {**creative, "client": client, "project": client.get(endpoint).json()}
        assert client.put('/api/settings', json={'provider': provider, 'api_key': SECRET}).status_code == 200
        response, _ = submit(state, provider=provider, size=size)
        assert response.status_code == 202, response.text
        result = wait_job(state, response.json()["job"])
        assert result["job"]["status"] == "succeeded", result
        context = client.get(endpoint + "/creative").json()
        artwork = context["generations"][0]
        assert client.get(artwork["url"]).status_code == 200
        mockup = client.post(endpoint + "/mockups", json={"revision": result["project"]["revision"],
            "template_id": "tote_bag", "artwork_id": artwork["id"]})
        assert mockup.status_code == 200, mockup.text
        current = mockup.json()["project"]
        analyzed = client.post(endpoint + "/analyze", json={"revision": current["revision"]})
        assert analyzed.status_code == 200, analyzed.text
        current = analyzed.json()["project"]
        assert client.get(artwork["url"]).status_code == 200
        assert client.get(mockup.json()["mockup"]["url"]).status_code == 200
        for format in ("png", "zip"):
            exported = client.post(endpoint + "/creative/exports", json={"revision": current["revision"],
                "artwork_id": mockup.json()["mockup"]["id"], "format": format})
            assert exported.status_code == 200, exported.text
            current = exported.json()["project"]
            download = client.get(exported.json()["export"]["url"])
            assert download.status_code == 200
            assert "attachment" in download.headers["content-disposition"]
            if format == "png":
                assert Image.open(BytesIO(download.content)).size == (480, 560)
            else:
                with ZipFile(BytesIO(download.content)) as archive:
                    manifest = json.loads(archive.read("manifest.json"))
                    assert any(f["kind"] == "mockup" and f["ai_assisted"] for f in manifest["files"])
                    assert SECRET.encode() not in b"".join(archive.read(p) for p in archive.namelist())
        backup = client.get(endpoint + '/backup')
        assert backup.status_code == 200
        with ZipFile(BytesIO(backup.content)) as archive:
            assert not any('.private' in name or 'provider-settings' in name for name in archive.namelist())
            assert SECRET.encode() not in b''.join(archive.read(name) for name in archive.namelist())
