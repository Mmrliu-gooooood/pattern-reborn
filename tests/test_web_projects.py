"""Public persistence boundaries, immutable recovery and hostile ZIP inputs."""
from datetime import UTC, datetime
import hashlib
from io import BytesIO
import json
from pathlib import Path
from threading import RLock
import stat
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import pytest
from PIL import Image

pytest.importorskip("fastapi")
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from pattern_reborn.domain import CategoryId, ProvenanceClass, StepId
from pattern_reborn.exporter import Exporter, ExportSelection
from pattern_reborn.projects import ProjectRepository
from pattern_reborn.web_projects import SIDECAR, register_project_routes


def core_mockup(studio):
    from pattern_reborn.knowledge import KnowledgeCatalog
    from pattern_reborn.workflow import PatternRebornService

    _, project, repository, export_root, *_ = studio
    catalog = KnowledgeCatalog.load(Path(__file__).resolve().parents[1] / "data/knowledge")
    service = PatternRebornService(repository, knowledge=catalog, export_root=export_root)
    artifact = service.make_mockup(project.id, "bookmark", "patterns/v1.png")
    return repository.load(project.id), artifact


@pytest.fixture
def studio(tmp_path):
    repository = ProjectRepository(tmp_path / "workspace")
    export_root = tmp_path / "exports"
    source = tmp_path / "source.png"
    Image.new("RGBA", (40, 32), (190, 32, 32, 180)).save(source)
    original = source.read_bytes()
    project = repository.create("原作", source, CategoryId.PAPER_CUTTING, ProvenanceClass.USER_SUPPLIED_UNVERIFIED)
    folder = repository.project_dir(project.id)
    for relative, color in [("extracted/v1.png", "red"), ("masks/v1.png", "white"), ("patterns/v1.png", "blue")]:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (32, 32), color).save(path)
    project = repository.confirm(project.id, StepId.EXTRACTION, ["extracted/v1.png", "masks/v1.png"])
    project = repository.confirm(project.id, StepId.RECOMPOSITION, ["patterns/v1.png"])
    project.processing_parameters["web_workspace"] = {"design": {"source_artifact": "extracted/v1.png", "artifact": "patterns/v1.png", "settings": {"width": 256, "height": 256}}}
    repository.save(project)
    app = FastAPI()

    @app.exception_handler(ValueError)
    async def bad_input(request, error):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(error)}, status_code=400)

    def current(project_id, revision):
        value = repository.load(project_id)
        if value.updated_at.isoformat() != revision:
            raise HTTPException(409, "conflict")
        return value

    def public(value, detail=False):
        return {"id": value.id, "revision": value.updated_at.isoformat(), "name": value.name,
                "has_result": bool(value.artifacts.extraction), "has_pattern": bool(value.artifacts.recomposition)}

    def artifact(value, relative):
        return repository._validate_relative_path(repository.project_dir(value.id), relative)

    snapshot = register_project_routes(app, repository, RLock(), current, public, artifact, export_root)
    with TestClient(app) as client:
        yield client, project, repository, export_root, original, snapshot


def url(project, path=""):
    return f"/api/projects/{project.id}{path}"


def extraction():
    return {"profile": "silhouette", "box": [0, 0, 32, 32], "strokes": [], "feather": 2}


def version(studio, name="方案甲"):
    client, project, *_ = studio
    response = client.post(url(project, "/versions"), json={"revision": project.updated_at.isoformat(), "name": name})
    assert response.status_code == 200, response.text
    return response.json()["version"]


def archive(studio):
    response = studio[0].get(url(studio[1], "/backup"))
    assert response.status_code == 200, response.text
    return response.content


def import_zip(client, data):
    return client.post("/api/projects/import", files={"file": ("backup.zip", data, "application/zip")})


def rewrite_archive(data, edit):
    with ZipFile(BytesIO(data)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    edit(files)
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as target:
        for name, value in files.items():
            target.writestr(name, value)
    return stream.getvalue()


def update_manifest(files):
    manifest = json.loads(files["manifest.json"])
    manifest["files"] = {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                         for name, data in files.items() if name != "manifest.json"}
    files["manifest.json"] = json.dumps(manifest).encode()


def test_drafts_survive_reopen_without_advancing_revision_and_detect_stale(studio):
    client, project, repository, *_ = studio
    revision = project.updated_at.isoformat()
    target = url(project, "/drafts/extract")
    assert client.get(target).json()["draft"] is None
    saved = client.put(target, json={"base_revision": revision, "data": extraction()})
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == revision
    assert repository.load(project.id).updated_at == project.updated_at
    # A fresh repository reads the same sidecar; no in-memory state is required.
    path = ProjectRepository(repository.workspace).project_dir(project.id) / SIDECAR / "drafts/extract.json"
    assert json.loads(path.read_bytes())["data"] == saved.json()["draft"]["data"]
    assert client.get(target).json()["draft"]["data"] == saved.json()["draft"]["data"]
    project.updated_at = datetime.now(UTC)
    repository.save(project)
    assert client.get(target).json()["draft"]["stale"] is True
    assert client.put(target, json={"base_revision": revision, "data": extraction()}).status_code == 409
    assert client.delete(target).status_code == 204
    assert client.get(target).json()["draft"] is None


@pytest.mark.parametrize("kind,data", [("extract", {"profile": "unknown"}), ("extract", {**extraction(), "strokes": [{"mode": "keep", "points": [[0, 0]], "width": -1}]}), ("design", {"settings": {"width": 999999}}), ("design", {"settings": {"background": "javascript:bad"}})])
def test_invalid_draft_cannot_break_recovery(studio, kind, data):
    client, project, *_ = studio
    response = client.put(url(project, f"/drafts/{kind}"), json={"base_revision": project.updated_at.isoformat(), "data": data})
    assert response.status_code == 400
    assert client.get(url(project, f"/drafts/{kind}")).json()["draft"] is None


def test_design_draft_uses_normalized_settings(studio):
    client, project, *_ = studio
    response = client.put(url(project, "/drafts/design"), json={"base_revision": project.updated_at.isoformat(), "data": {"settings": {"width": 256, "height": 256}}})
    assert response.status_code == 200, response.text
    assert response.json()["draft"]["data"]["width"] == 256
    assert "settings" not in response.json()["draft"]["data"]


def test_named_versions_restore_invalidated_pattern_and_preserve_newer_exports(studio):
    client, project, repository, export_root, original, auto_snapshot = studio
    saved = version(studio)
    reference = client.get(saved["pattern_url"]).content
    assert client.get(url(project, "/versions")).json()["versions"][0]["name"] == "方案甲"
    # Save a newer source extraction, clearing the current downstream pattern.
    folder = repository.project_dir(project.id)
    Image.new("RGBA", (32, 32), "green").save(folder / "extracted/v2.png")
    newer = repository.confirm(project.id, StepId.EXTRACTION, ["extracted/v2.png"])
    export_id = "e" * 32
    exported = export_root / project.id / export_id / "pattern.png"
    exported.parent.mkdir(parents=True)
    exported.write_bytes(reference)
    newer.processing_parameters["web_workspace"]["exports"] = [{"id": export_id, "filename": "pattern.png", "format": "png", "source": "pattern", "source_artifact": "patterns/v1.png", "url": url(project, f"/exports/{export_id}")}]
    repository.save(newer)
    newer_revision = newer.updated_at.isoformat()
    assert client.post(url(project, f"/versions/{saved['id']}/restore"), json={"revision": project.updated_at.isoformat()}).status_code == 409
    response = client.post(url(project, f"/versions/{saved['id']}/restore"), json={"revision": newer_revision})
    assert response.status_code == 200, response.text
    restored = repository.load(project.id)
    assert restored.artifacts.recomposition == ["patterns/v1.png"]
    assert "patterns/v1.png" not in restored.stale_artifacts
    assert "extracted/v2.png" in restored.stale_artifacts
    assert response.json()["before_restore"]["id"] != saved["id"]
    assert restored.processing_parameters["web_workspace"]["exports"][0]["id"] == export_id
    assert exported.read_bytes() == reference
    assert (folder / restored.source.relative_path).read_bytes() == original
    assert client.get(saved["pattern_url"]).content == reference
    assert response.json()["project"]["revision"] != newer_revision
    count = len(client.get(url(project, "/versions")).json()["versions"])
    auto_snapshot(restored, "自动保存")
    auto_snapshot(restored, "重复自动保存")
    assert len(client.get(url(project, "/versions")).json()["versions"]) == count + 1


def test_lossless_backup_roundtrip_and_duplicate_have_independent_files(studio):
    client, project, repository, export_root, original, _ = studio
    saved = version(studio)
    data = archive(studio)
    with ZipFile(BytesIO(data)) as zipped:
        metadata = json.loads(zipped.read("project/project.json"))
        assert metadata["schema_version"] == 1
        assert zipped.read("project/" + project.source.relative_path) == original
    imported = import_zip(client, data)
    assert imported.status_code == 200, imported.text
    imported_project = repository.load(imported.json()["id"])
    assert imported_project.id != project.id
    assert (repository.project_dir(imported_project.id) / imported_project.source.relative_path).read_bytes() == original
    assert client.get(url(imported_project, "/versions")).json()["versions"][0]["pattern_url"].startswith(url(imported_project))
    duplicate = client.post(url(project, "/duplicate"), json={"revision": project.updated_at.isoformat(), "name": "独立副本"})
    assert duplicate.status_code == 200, duplicate.text
    clone = repository.load(duplicate.json()["id"])
    assert clone.name == "独立副本"
    clone_image = repository.project_dir(clone.id) / clone.artifacts.recomposition[0]
    original_image = repository.project_dir(project.id) / project.artifacts.recomposition[0]
    clone_image.write_bytes(b"modified separately")
    assert original_image.read_bytes() != clone_image.read_bytes()
    assert client.get(saved["pattern_url"]).status_code == 200


@pytest.mark.parametrize("historical_only", [False, True])
def test_backup_omits_core_runtime_locks_and_imports_older_backups_containing_them(studio, historical_only):
    from pattern_reborn.mockups import _LOCK_MAGIC

    client, _, repository, _, original, snapshot = studio
    project, mockup = core_mockup(studio)
    snapshot(project, "贴图作品")
    folder = repository.project_dir(project.id)
    lock = folder / "mockups/.bookmark-v1.mockup.lock"
    assert lock.read_bytes() == _LOCK_MAGIC
    if historical_only:
        project.processing_parameters["current_mockups"] = []
        project.updated_at = datetime.now(UTC)
        repository.save(project)
    data = archive(studio)
    with ZipFile(BytesIO(data)) as zipped:
        assert "project/mockups/bookmark-v1.png" in zipped.namelist()
        assert "project/mockups/.bookmark-v1.mockup.lock" not in zipped.namelist()

    def restore_old_lock(files):
        files["project/mockups/.bookmark-v1.mockup.lock"] = _LOCK_MAGIC
        update_manifest(files)

    older = rewrite_archive(data, restore_old_lock)
    response = import_zip(client, older)
    assert response.status_code == 200, response.text
    clone = repository.load(response.json()["id"])
    cloned_folder = repository.project_dir(clone.id)
    assert (cloned_folder / mockup.artifact_id).read_bytes() == mockup.path.read_bytes()
    assert (cloned_folder / mockup.artifact_id).with_suffix(".json").read_bytes() == mockup.path.with_suffix(".json").read_bytes()
    assert not (cloned_folder / "mockups/.bookmark-v1.mockup.lock").exists()
    assert (cloned_folder / clone.source.relative_path).read_bytes() == original
    assert lock.read_bytes() == _LOCK_MAGIC  # Live project is never modified.
    duplicate = client.post(url(project, "/duplicate"), json={"revision": project.updated_at.isoformat()})
    assert duplicate.status_code == 200, duplicate.text


@pytest.mark.parametrize("member,contents,indexed", [
    ("project/mockups/.bookmark-v1.mockup.lock", b"not a core runtime lock", True),
    ("project/mockups/.bookmark-v1.mockup.lock", b"Pattern Reborn mockup lock v1\n", False),
    ("project/mockups/arbitrary.lock", b"Pattern Reborn mockup lock v1\n", True),
    ("project/patterns/.v1.mockup.lock", b"Pattern Reborn mockup lock v1\n", True),
])
def test_import_lock_exception_requires_exact_core_signature_and_indexed_mockup(studio, member, contents, indexed):
    client, _, repository, *_ = studio
    project, _ = core_mockup(studio)
    if not indexed:
        project.processing_parameters["current_mockups"] = []
        repository.save(project)

    def inject(files):
        files[member] = contents
        update_manifest(files)

    response = import_zip(client, rewrite_archive(archive(studio), inject))
    assert response.status_code == 400, response.text
    assert len(repository.list_recent()) == 1
    assert not list(repository.workspace.glob(".import-*"))


def test_backup_remaps_export_urls_and_clones_downloads(studio):
    client, project, repository, export_root, *_ = studio
    export_id = "f" * 32
    path = export_root / project.id / export_id / "original.png"
    path.parent.mkdir(parents=True)
    payload = (repository.project_dir(project.id) / project.source.relative_path).read_bytes()
    path.write_bytes(payload)
    project.processing_parameters["web_workspace"]["exports"] = [{"id": export_id, "filename": path.name, "format": "png", "source": "result", "url": url(project, f"/exports/{export_id}")}]
    repository.save(project)
    response = import_zip(client, archive(studio))
    assert response.status_code == 200, response.text
    clone = repository.load(response.json()["id"])
    assert clone.processing_parameters["web_workspace"]["exports"][0]["url"] == url(clone, f"/exports/{export_id}")
    assert (export_root / clone.id / export_id / path.name).read_bytes() == payload


def test_import_export_directory_collision_never_deletes_existing_files(studio, monkeypatch):
    client, project, repository, export_root, *_ = studio
    export_id = "a" * 32
    path = export_root / project.id / export_id / "pattern.png"
    path.parent.mkdir(parents=True)
    path.write_bytes((repository.project_dir(project.id) / project.source.relative_path).read_bytes())
    project.processing_parameters["web_workspace"]["exports"] = [{"id": export_id, "filename": path.name, "format": "png"}]
    repository.save(project)
    data = archive(studio)
    collision_id = "project-" + "b" * 32
    protected = export_root / collision_id / "existing.txt"
    protected.parent.mkdir()
    protected.write_text("保留已有文件", encoding="utf-8")
    monkeypatch.setattr(repository, "_new_project_id", lambda: collision_id)
    response = import_zip(client, data)
    assert response.status_code == 409, response.text
    assert protected.read_text(encoding="utf-8") == "保留已有文件"
    assert len(repository.list_recent()) == 1
    assert not list(export_root.glob(".import-*"))


def test_backup_and_import_never_persist_credentials(studio):
    client, project, repository, *_ = studio
    project.processing_parameters["api_key"] = "sk-test-secret-credential"
    project.processing_parameters["web_workspace"]["rights"] = {"creator": "Bearer abc123", "password": "plain-password"}
    repository.save(project)
    data = archive(studio)
    with ZipFile(BytesIO(data)) as zipped:
        assert b"sk-test-secret" not in zipped.read("project/project.json")
        assert b"plain-password" not in zipped.read("project/project.json")
    response = import_zip(client, data)
    assert response.status_code == 200, response.text
    clone = repository.load(response.json()["id"])
    assert "api_key" not in clone.processing_parameters
    assert clone.processing_parameters["web_workspace"]["rights"]["creator"] == "[REDACTED]"


@pytest.mark.parametrize("member", ["../outside.txt", "project/../../outside.txt", "project\\..\\outside.txt", "/absolute.png", "C:/absolute.png", "project/source/file.png:evil", "project/CON.png", "project/source/trailing. "])
def test_import_rejects_hostile_paths_without_any_publication(studio, member):
    client, project, repository, *_ = studio
    stream = BytesIO()
    with ZipFile(stream, "w") as zipped:
        zipped.writestr(member, b"bad")
    response = import_zip(client, stream.getvalue())
    assert response.status_code == 400, response.text
    assert [p.id for p in repository.list_recent()] == [project.id]
    assert not list(repository.workspace.glob(".import-*"))


def test_import_rejects_symlink_duplicate_case_and_zip_bomb(studio, monkeypatch):
    client, project, repository, *_ = studio
    stream = BytesIO()
    with ZipFile(stream, "w") as zipped:
        link = ZipInfo("project/source/link.png")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zipped.writestr(link, "../../outside")
    assert import_zip(client, stream.getvalue()).status_code == 400
    stream = BytesIO()
    with ZipFile(stream, "w") as zipped:
        zipped.writestr("project/a.png", b"a")
        zipped.writestr("project/A.png", b"b")
    assert import_zip(client, stream.getvalue()).status_code == 400
    import pattern_reborn.web_projects as persistence
    monkeypatch.setattr(persistence, "MAX_UNPACKED_BYTES", 1024)
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr("project/large.txt", b"a" * 2048)
    assert import_zip(client, stream.getvalue()).status_code == 413
    assert len(repository.list_recent()) == 1


@pytest.mark.parametrize("corruption", ["hash", "missing", "schema", "source_hash", "snapshot_id", "snapshot_directory"])
def test_import_rejects_corrupt_or_incomplete_backup(studio, corruption):
    client, project, repository, *_ = studio
    version(studio)
    def corrupt(files):
        if corruption == "hash":
            files["project/patterns/v1.png"] = b"different"
            return
        if corruption == "missing":
            del files["project/patterns/v1.png"]
        elif corruption in {"schema", "source_hash"}:
            metadata = json.loads(files["project/project.json"])
            if corruption == "schema":
                metadata["schema_version"] = 2
            else:
                metadata["source"]["sha256"] = "0" * 64
            files["project/project.json"] = json.dumps(metadata).encode()
        elif corruption == "snapshot_directory":
            files["project/.web-workspace/versions/" + "d" * 32 + ".json/child.json"] = b"{}"
        else:
            name = next(name for name in files if "/versions/" in name)
            snapshot = json.loads(files[name])
            snapshot["project"]["id"] = "project-foreign"
            files[name] = json.dumps(snapshot).encode()
        update_manifest(files)
    response = import_zip(client, rewrite_archive(archive(studio), corrupt))
    assert response.status_code == 400, response.text
    assert len(repository.list_recent()) == 1
    assert not list(repository.workspace.glob(".import-*"))


def test_corrupt_project_metadata_recovers_from_checked_snapshot(studio):
    client, project, repository, _, original, _ = studio
    snapshot = version(studio)
    folder = repository.project_dir(project.id)
    before = (folder / project.source.relative_path).read_bytes()
    (folder / "project.json").write_bytes(b"{broken metadata")
    recovered = client.get("/api/recovery")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["projects"][0]["id"] == project.id
    response = client.post(url(project, "/recover"), json={"version_id": snapshot["id"]})
    assert response.status_code == 200, response.text
    assert repository.load(project.id).artifacts.recomposition == ["patterns/v1.png"]
    assert (folder / project.source.relative_path).read_bytes() == before == original
    assert list((folder / SIDECAR / "recovery").glob("*.txt"))
    assert client.post(url(project, "/recover"), json={"version_id": snapshot["id"]}).status_code == 409


def test_old_source_inclusive_delivery_zip_imports_as_editable_project(studio, tmp_path):
    client, project, repository, _, original, _ = studio
    project.artifacts.extraction = ["extracted/v1.png"]
    package = Exporter(repository.project_dir(project.id)).export(project, ExportSelection(source=True, extracted=True, patterns=True), tmp_path / "delivery")
    (package / "workspace-settings.json").write_text(json.dumps({"edit": extraction(), "rights": {"creator": "原作者", "license": "CC0"}, "design": project.processing_parameters["web_workspace"]["design"]}), encoding="utf-8")
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as zipped:
        for path in package.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(package).as_posix())
    response = import_zip(client, stream.getvalue())
    assert response.status_code == 200, response.text
    clone = repository.load(response.json()["id"])
    assert clone.artifacts.extraction and clone.artifacts.recomposition
    assert clone.processing_parameters["web_workspace"]["edit"]["profile"] == "silhouette"
    assert (repository.project_dir(clone.id) / clone.source.relative_path).read_bytes() == original
    assert response.json()["import_notice"]


def test_delivery_without_source_explains_recovery_requirement(studio, tmp_path):
    client, project, repository, *_ = studio
    package = Exporter(repository.project_dir(project.id)).export(project, ExportSelection(patterns=True), tmp_path / "delivery")
    stream = BytesIO()
    with ZipFile(stream, "w") as zipped:
        for path in package.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(package).as_posix())
    response = import_zip(client, stream.getvalue())
    assert response.status_code == 400
    assert "未包含原图" in response.json()["detail"]


def test_missing_project_json_can_recover_without_rewriting_source(studio):
    client, project, repository, _, original, _ = studio
    snapshot = version(studio)
    folder = repository.project_dir(project.id)
    (folder / "project.json").unlink()
    assert client.get("/api/recovery").json()["projects"][0]["id"] == project.id
    response = client.post(url(project, "/recover"), json={"version_id": snapshot["id"]})
    assert response.status_code == 200, response.text
    assert (folder / repository.load(project.id).source.relative_path).read_bytes() == original


@pytest.mark.parametrize("budget,value", [("MAX_ARCHIVE_FILES", 1), ("MAX_FILE_BYTES", 64), ("MAX_TOTAL_IMAGE_PIXELS", 1)])
def test_import_enforces_each_resource_budget(studio, monkeypatch, budget, value):
    import pattern_reborn.web_projects as persistence
    data = archive(studio)
    monkeypatch.setattr(persistence, budget, value)
    response = import_zip(studio[0], data)
    assert response.status_code == 413, response.text
    assert len(studio[2].list_recent()) == 1


def test_real_app_save_draft_history_export_backup_restore_flow(tmp_path, monkeypatch):
    from pattern_reborn.web_api import create_app
    from tests.test_web_api import HEADERS, edit, upload
    monkeypatch.setenv("PATTERN_REBORN_OUTPUTS", str(tmp_path / "exports"))
    root = tmp_path / "workspace"
    with TestClient(create_app(root, settings_path=tmp_path / 'private/settings.json'), headers=HEADERS) as client:
        project, original = upload(client)
        base = f"/api/projects/{project['id']}"
        initial = project["revision"]
        data = {key: value for key, value in edit(project).items() if key != "revision"}
        response = client.put(base + "/drafts/extract", json={"base_revision": initial, "data": data})
        assert response.status_code == 200, response.text
        assert client.get(base).json()["revision"] == initial
        response = client.post(base + "/save", json=edit(project))
        assert response.status_code == 200, response.text
        project = response.json()
        assert client.get(base + "/drafts/extract").json()["draft"]["stale"]
        context = client.get(base + "/design").json()
        response = client.post(base + "/design/save", json={"revision": project["revision"], "settings": {**context["settings"], "width": 128, "height": 128}})
        assert response.status_code == 200, response.text
        project = response.json()
        snapshot = client.post(base + "/versions", json={"revision": project["revision"], "name": "完整方案"}).json()["version"]
        image = client.get(snapshot["pattern_url"]).content
        response = client.post(base + "/exports", json={"revision": project["revision"], "source": "pattern", "format": "png"})
        assert response.status_code == 200, response.text
        exported = response.json()
        immutable_export = client.get(exported["export"]["url"]).content
        response = client.post(base + "/save", json=edit(exported["project"]))
        assert response.status_code == 200, response.text
        assert not response.json()["has_pattern"]
        restored = client.post(base + f"/versions/{snapshot['id']}/restore", json={"revision": response.json()["revision"]})
        assert restored.status_code == 200, restored.text
        assert restored.json()["project"]["has_pattern"]
        assert client.get(exported["export"]["url"]).content == immutable_export
        creative = client.get(base + "/creative").json()
        artwork = next(a for a in creative["artworks"] if a["kind"] == "pattern")
        mockup = client.post(base + "/mockups", json={"revision": restored.json()["project"]["revision"],
            "template_id": "bookmark", "artwork_id": artwork["id"]})
        assert mockup.status_code == 200, mockup.text
        mockup_image = client.get(mockup.json()["mockup"]["url"]).content
        mockup_export = client.post(base + "/creative/exports", json={"revision": mockup.json()["project"]["revision"],
            "artwork_id": mockup.json()["mockup"]["id"], "format": "png"})
        assert mockup_export.status_code == 200, mockup_export.text
        assert client.get(mockup_export.json()["export"]["url"]).content == mockup_image
        duplicate = client.post(base + "/duplicate", json={"revision": mockup_export.json()["project"]["revision"]})
        assert duplicate.status_code == 200, duplicate.text
        backup = client.get(base + "/backup")
        assert backup.status_code == 200, backup.text
        with ZipFile(BytesIO(backup.content)) as zipped:
            assert not any(name.endswith(".mockup.lock") for name in zipped.namelist())
        imported = import_zip(client, backup.content)
        assert imported.status_code == 200, imported.text
        clone = imported.json()
        assert clone["id"] != project["id"] and clone["has_pattern"]
        assert client.get(f"/api/projects/{clone['id']}/image?kind=pattern").content == image
        repository = ProjectRepository(root)
        record = repository.load(clone["id"])
        assert (repository.project_dir(record.id) / record.source.relative_path).read_bytes() == original
        cloned_exports = client.get(f"/api/projects/{clone['id']}/design").json()["exports"]
        exported_clone = next(item for item in cloned_exports if item["id"] == exported["export"]["id"])
        assert client.get(exported_clone["url"]).content == immutable_export
        cloned_mockup_export = next(item for item in cloned_exports if item["id"] == mockup_export.json()["export"]["id"])
        assert client.get(cloned_mockup_export["url"]).content == mockup_image
        cloned_creative = client.get(f"/api/projects/{clone['id']}/creative").json()
        assert client.get(cloned_creative["mockups"][0]["url"]).content == mockup_image
