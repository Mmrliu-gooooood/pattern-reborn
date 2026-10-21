"""Local creative routes, session credentials and revision-safe paid jobs.

Provider calls run against an isolated copy of the core workflow. Only a
completed job whose input revision is still current can publish into a project.
Nothing in this module probes a provider or submits work during startup.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, ValidationError, field_validator

from .config import ConfigError, ProviderConfig, load_provider_config, require_https_url
from .domain import StepId
from .exporter import Exporter, ExportSelection
from .generation.base import (
    CredentialMode, FailureKind, GenerationFailure, GenerationRequest, ProviderId,
    StructureLevel, TargetApplication,
)
from .generation.http import USER_MESSAGE_ZH
from .generation.service import build_generation_service
from .images import probe_image, save_png_atomic
from .mockups import load_mockup_catalog
from .projects import ProjectRepository
from .ui.labels import mockup_template_label
from .ui.presenters import confirmed_extraction, current_artworks, current_generations, current_mockups, load_analysis
from .vectorize import Vectorizer
from .web_extraction import extraction_capabilities
from .workflow import PatternRebornService

_COOKIE = "pattern_reborn_session"
_ACTIVE = {"queued", "running", "cancelling"}
_SECRET_TEXT = re.compile(r"(?i)(?:api[_-]?key|\bauthorization\b|\bbearer\b|sk-[A-Za-z0-9._-]+)")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _redacted(value: str) -> str:
    return "[REDACTED]" if _SECRET_TEXT.search(value) else value


def _redacted_tree(value):
    if isinstance(value, str):
        return _redacted(value)
    if isinstance(value, list):
        return [_redacted_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: _redacted_tree(item) for key, item in value.items()}
    return value


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=1, max_length=100)


class SettingsChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: ProviderId
    api_key: SecretStr | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    model: str | None = Field(default=None, min_length=1, max_length=150, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")

    @field_validator("base_url")
    @classmethod
    def safe_endpoint(cls, value):
        if value is None:
            return value
        require_https_url(value)
        parts = urlsplit(value)
        if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
            raise ValueError("服务地址不能包含认证信息、查询参数或片段。")
        # Ports are parsed here as well, so invalid port strings never reach HTTP.
        _ = parts.port
        return value.rstrip("/")


class GenerationEdit(Revision):
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    provider: ProviderId
    prompt: str = Field(min_length=1, max_length=6000)
    model: str | None = Field(default=None, min_length=1, max_length=150)
    size: str = Field(min_length=1, max_length=30)
    structure_level: StructureLevel = StructureLevel.HIGH
    target_application: TargetApplication = TargetApplication.TEXTILE
    colors: list[str] = Field(default_factory=list, max_length=12)
    negative_constraints: str = Field(default="", max_length=2000)
    reference_id: str | None = Field(default=None, max_length=250)
    mode: CredentialMode = CredentialMode.PLATFORM
    paid_confirmed: StrictBool = False

    @field_validator("prompt")
    @classmethod
    def nonempty_prompt(cls, value):
        if not value.strip():
            raise ValueError("请填写提示词。")
        return value.strip()


class MockupEdit(Revision):
    template_id: str = Field(min_length=1, max_length=80)
    artwork_id: str = Field(min_length=1, max_length=250)


class CreativeExport(Revision):
    artwork_id: str = Field(min_length=1, max_length=250)
    format: Literal["png", "zip"] = "png"
    include_original: StrictBool = False


@dataclass
class _Session:
    keys: dict[ProviderId, SecretStr] = field(default_factory=dict)
    overrides: dict[ProviderId, dict[str, str]] = field(default_factory=dict)


@dataclass
class _Job:
    id: str
    session: str
    project_id: str
    revision: str
    request_id: str
    fingerprint: str
    provider: str
    created_at: str = field(default_factory=_now)
    status: str = "queued"
    finished_at: str | None = None
    failure_kind: str | None = None
    message: str = "等待生成。"
    cancel_requested: bool = False
    artifacts: list[str] = field(default_factory=list)

    def public(self):
        return {"id": self.id, "project_id": self.project_id, "revision": self.revision,
                "request_id": self.request_id, "provider": self.provider, "status": self.status,
                "created_at": self.created_at, "finished_at": self.finished_at,
                "failure_kind": self.failure_kind, "message": self.message,
                "cancel_requested": self.cancel_requested, "artifacts": list(self.artifacts),
                "retryable": self.status in {"failed", "stale", "cancelled"}}


def register_creative_routes(app, repository, catalog, lock, current, public, safe_artifact, export_root,
                             *, generation_factory=None, config_path=None, auto_snapshot=None):
    """Register creative endpoints. ``generation_factory`` is an offline test seam."""
    factory = generation_factory or build_generation_service
    root = Path(__file__).resolve().parents[2]
    config_file = Path(config_path) if config_path else root / "config/providers.json"
    try:
        base_config = load_provider_config(config_file)
        config_error = None
    except ConfigError:
        base_config = None
        config_error = "提供方配置无法读取，请检查本地 config/providers.json 和环境变量。"
    sessions: dict[str, _Session] = {}
    jobs: dict[str, _Job] = {}
    templates = load_mockup_catalog()
    service = PatternRebornService(repository, knowledge=catalog, export_root=export_root, mockup_catalog=templates)

    def capture(project, label, *, published=False):
        if auto_snapshot is not None:
            try:
                auto_snapshot(project, label)
            except Exception:
                if not published:
                    raise
                return False
        return True

    def session(request: Request, response: Response):
        identifier = request.cookies.get(_COOKIE, "")
        if identifier not in sessions:
            identifier = uuid4().hex
            sessions[identifier] = _Session()
            response.set_cookie(_COOKIE, identifier, httponly=True, samesite="strict", secure=request.url.scheme == "https")
        return identifier, sessions[identifier]

    def configured(value: _Session) -> ProviderConfig:
        if base_config is None:
            raise HTTPException(503, config_error)
        config = base_config.model_copy(deep=True)
        for provider in config.providers:
            overrides = value.overrides.get(provider.id, {})
            if "base_url" in overrides:
                provider.base_url = overrides["base_url"]
            if "model" in overrides:
                provider.default_model = overrides["model"]
        return config

    def provider_views(value: _Session):
        if base_config is None:
            return []
        config = configured(value)
        values = []
        for provider in config.providers:
            platform = bool(os.environ.get(provider.api_key_env, "").strip())
            byok = provider.id in value.keys
            # Malformed environment overrides must not become a secret-bearing URL.
            try:
                endpoint = SettingsChange.safe_endpoint(provider.base_url)
            except ValueError:
                endpoint = "[REDACTED]"
            values.append({"id": provider.id.value, "name": provider.display_name_zh,
                           "base_url": endpoint, "model": _redacted(provider.default_model),
                           "size_options": provider.size_options, "platform_credential": platform,
                           "session_credential": byok, "available": platform or byok,
                           "reason": "" if platform or byok else "请在设置中填写本次会话密钥，或配置本地环境变量。",
                           "key_env": provider.api_key_env, "endpoint_env": provider.base_url_env,
                           "model_env": provider.model_env,
                           "capabilities": {"reference_images": 1, "output_count": 1,
                                            "negative_constraints": provider.id is ProviderId.QWEN}})
        return values

    def settings_view(value: _Session):
        vector = Vectorizer().capability()
        return {"providers": provider_views(value), "session_only": True, "config_error": config_error,
                "capabilities": {"opencv": {"available": True, "reason": "本地提取和分析可用。"},
                                 "vtracer": {"available": vector.available, "reason": vector.reason_zh},
                                 "mobile_sam": extraction_capabilities(root)["mobile_sam"],
                                 "canvas": {"available": True, "reason": "浏览器画布可用。"}},
                "setup": ["提取、分析、重组、贴图和 PNG 导出均在本地运行。",
                          "密钥、服务地址和模型覆盖仅保存在当前浏览器会话的服务进程内存中；重启后清除。",
                          "长期配置可在本地 .env 中设置提供方环境变量；密钥不会写入项目和导出包。",
                          "AI 生成会向选定提供方发送参考图和提示词，并可能产生费用；每次提交均需明确确认。",
                          "取消会阻止本地发布；已发送的远程请求可能继续执行并计费。"],
                "options": {"structure_levels": [value.value for value in StructureLevel],
                            "target_applications": [value.value for value in TargetApplication],
                            "colors": [color.model_dump(mode="json") for color in catalog.colors]}}

    def artwork_url(project_id, artifact_id):
        token = sha256(artifact_id.encode()).hexdigest()[:32]
        return f"/api/projects/{project_id}/artwork/{token}"

    def allowed_artworks(project, *, references=False):
        project_dir = repository.project_dir(project.id)
        values = {view.artifact_id: {"id": view.artifact_id,
                  "kind": "generation" if view.ai_assisted else "pattern",
                  "url": artwork_url(project.id, view.artifact_id), "ai_assisted": view.ai_assisted}
                  for view in current_artworks(project_dir, project) if view.path.suffix.lower() == ".png"}
        for path in current_mockups(project_dir, project):
            relative = path.relative_to(project_dir).as_posix()
            ai = False
            try:
                sidecar = safe_artifact(project, str(Path(relative).with_suffix(".json")).replace("\\", "/"))
                ai = json.loads(sidecar.read_text(encoding="utf-8")).get("ai_assisted") is True
            except (ValueError, OSError, HTTPException):
                pass
            values[relative] = {"id": relative, "kind": "mockup", "url": artwork_url(project.id, relative), "ai_assisted": ai}
        if references:
            extracted = confirmed_extraction(project_dir, project)
            if extracted:
                relative, _ = extracted
                values[relative] = {"id": relative, "kind": "extracted", "url": artwork_url(project.id, relative), "ai_assisted": False}
        return values

    def creative_view(project, session_id, value):
        artifacts = allowed_artworks(project, references=True)
        generations = []
        for generated in current_generations(repository.project_dir(project.id), project):
            if generated.artifact_id in artifacts:
                generations.append({**artifacts[generated.artifact_id], "provider": generated.provider,
                                    "model": _redacted(generated.model), "prompt": _redacted(generated.prompt),
                                    "created_at": generated.created_at})
        return {"project": public(project, True), "settings": settings_view(value),
                "artworks": [a for a in artifacts.values() if a["kind"] in {"pattern", "generation"}],
                "references": [a for a in artifacts.values() if a["kind"] != "mockup"],
                "generations": generations,
                "mockups": [a for a in artifacts.values() if a["kind"] == "mockup"],
                "templates": [{"id": t.id, "name": mockup_template_label(t.id),
                               "url": f"/api/mockup-templates/{t.id}", "width": t.canvas_size[0], "height": t.canvas_size[1],
                               "creator": t.creator, "license": t.license} for t in templates.values()],
                "jobs": [job.public() for job in jobs.values() if job.project_id == project.id and job.session == session_id]}

    @app.get("/api/settings")
    def get_settings(request: Request, response: Response):
        with lock:
            _, value = session(request, response)
            return settings_view(value)

    @app.put("/api/settings")
    async def put_settings(request: Request, response: Response):
        # Deliberately validate manually: default 422 bodies echo invalid inputs,
        # which would echo credentials supplied alongside malformed settings.
        try:
            data = SettingsChange.model_validate(await request.json())
            if data.api_key is not None and len(data.api_key.get_secret_value()) > 4096:
                raise ValueError("invalid credential")
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(400, "设置无效；请检查提供方、HTTPS 服务地址、模型和密钥。") from None
        with lock:
            _, value = session(request, response)
            configured(value)
            if "api_key" in data.model_fields_set:
                if data.api_key is not None and data.api_key.get_secret_value().strip():
                    value.keys[data.provider] = data.api_key
                else:
                    value.keys.pop(data.provider, None)
            overrides = value.overrides.setdefault(data.provider, {})
            if data.base_url is not None:
                overrides["base_url"] = data.base_url
            if data.model is not None:
                overrides["model"] = data.model
            return settings_view(value)

    @app.get("/api/projects/{project_id}/analysis")
    def get_analysis(project_id: str):
        with lock:
            project = repository.load(project_id)
            view = load_analysis(repository.project_dir(project_id), project)
            return {"analysis": asdict(view) if view else None, "project": public(project, True)}

    @app.post("/api/projects/{project_id}/analyze")
    def analyze(project_id: str, data: Revision):
        with lock:
            project = current(project_id, data.revision)
            capture(project, "分析前的状态")
            # Analysis is an inspection of the same confirmed extraction. The
            # core step confirmation invalidates later workflow steps, so run
            # it on an isolated snapshot and publish only its report here.
            staging_parent = Path(export_root).resolve() / ".analysis-jobs"
            staging_parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=uuid4().hex + "-", dir=staging_parent) as temporary:
                stage_repository = ProjectRepository(Path(temporary) / "projects")
                stage_project_dir = stage_repository.project_dir(project_id)
                stage_project_dir.mkdir()
                snapshot = project.model_copy(deep=True)
                snapshot.artifacts.extraction = [p for p in project.artifacts.extraction if p not in project.stale_artifacts]
                for relative in snapshot.artifacts.extraction:
                    source = safe_artifact(project, relative)
                    destination = stage_project_dir / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                stage_repository.save(snapshot)
                core = PatternRebornService(stage_repository, knowledge=catalog,
                                            export_root=Path(temporary) / "exports", mockup_catalog=templates)
                core.analyze(project_id)
                analyzed = stage_repository.load(project_id)
                relative = f"analysis/web-{uuid4().hex}.json"
                destination = repository.project_dir(project_id) / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary_report = destination.with_suffix(".json.tmp")
                try:
                    shutil.copyfile(stage_project_dir / analyzed.artifacts.analysis[0], temporary_report)
                    os.replace(temporary_report, destination)
                    saved = project.model_copy(deep=True)
                    saved.artifacts.analysis = [relative]
                    saved.processing_parameters["analysis"] = {**analyzed.processing_parameters["analysis"], "artifact_id": relative}
                    confirmed = set(saved.confirmed_steps) | {StepId.ANALYSIS}
                    saved.confirmed_steps = [step for step in StepId if step in confirmed]
                    if not confirmed.intersection({StepId.RECOMPOSITION, StepId.GENERATION, StepId.EXPORT}):
                        saved.processing_parameters["current_step"] = StepId.ANALYSIS.value
                    saved.updated_at = datetime.now(UTC)
                    repository.save(saved)
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                finally:
                    temporary_report.unlink(missing_ok=True)
            captured = capture(repository.load(project_id), "纹样分析", published=True)
            result = get_analysis(project_id)
            if not captured:
                result["warning"] = "分析已保存，但版本快照未能写入，请检查磁盘。"
            return result

    @app.get("/api/projects/{project_id}/creative")
    def get_creative(project_id: str, request: Request, response: Response):
        with lock:
            identifier, value = session(request, response)
            return creative_view(repository.load(project_id), identifier, value)

    @app.get("/api/mockup-templates/{template_id}")
    def get_template(template_id: str):
        template = templates.get(template_id)
        if template is None:
            raise HTTPException(404, "贴图模板不存在。")
        return FileResponse(template.path, media_type="image/png")

    @app.get("/api/projects/{project_id}/artwork/{token}")
    def get_artwork(project_id: str, token: str):
        with lock:
            project = repository.load(project_id)
            for artifact in allowed_artworks(project, references=True).values():
                if artifact["url"].rsplit("/", 1)[-1] == token:
                    return FileResponse(safe_artifact(project, artifact["id"]), media_type="image/png")
            raise HTTPException(404, "当前作品不存在或已因上游修改而失效。")

    @app.post("/api/projects/{project_id}/mockups")
    def make_mockup(project_id: str, data: MockupEdit):
        with lock:
            project = current(project_id, data.revision)
            eligible = allowed_artworks(project)
            if data.artwork_id not in eligible or eligible[data.artwork_id]["kind"] not in {"pattern", "generation"}:
                raise HTTPException(400, "请选择当前已保存的重组或 AI 生成作品。")
            if data.template_id not in templates:
                raise HTTPException(400, "贴图模板不存在。")
            capture(project, "文创贴图前的状态")
            artifact = service.make_mockup(project_id, data.template_id, data.artwork_id)
            project = repository.load(project_id)
            captured = capture(project, "文创贴图保存", published=True)
            return {"project": public(project, True), "mockup": allowed_artworks(project)[artifact.artifact_id],
                    "warning": None if captured else "贴图已保存，但版本快照未能写入，请检查磁盘。"}

    def finish(job, status, message, kind=None):
        job.status, job.message, job.failure_kind = status, message, kind
        job.finished_at = _now()

    def run_job(job, snapshot, request_data, config, credential, mode):
        try:
            staging_parent = Path(export_root).resolve() / ".generation-jobs"
            staging_parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=job.id + "-", dir=staging_parent) as temporary:
                stage_root = Path(temporary)
                stage_repository = ProjectRepository(stage_root / "projects")
                stage_project_dir = stage_repository.project_dir(snapshot.id)
                stage_project_dir.mkdir()
                with lock:
                    if job.cancel_requested:
                        finish(job, "cancelled", "已取消，未发布结果。")
                        return
                    if repository.load(snapshot.id).updated_at.isoformat() != job.revision:
                        finish(job, "stale", "项目输入已修改，未发送生成请求。")
                        return
                    # Only indexed inputs are copied; provider adapters never see
                    # arbitrary filesystem paths or a mutable project directory.
                    for relative in {snapshot.source.relative_path, request_data.reference_path.as_posix()}:
                        source = safe_artifact(snapshot, relative)
                        destination = stage_project_dir / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, destination)
                    stage_repository.save(snapshot)
                    job.status, job.message = "running", "生成请求已发送，等待提供方返回。"
                generation = factory(config=config, output_dir=stage_root / "remote")
                core = PatternRebornService(stage_repository, knowledge=catalog, generation=generation,
                                            export_root=stage_root / "exports", mockup_catalog=templates)
                result = core.generate(snapshot.id, request_data, CredentialMode.BYOK, credential)
                if len(result.local_files) != 1:
                    raise GenerationFailure(FailureKind.MALFORMED, USER_MESSAGE_ZH[FailureKind.MALFORMED])
                probe_image(result.local_files[0])
                with lock:
                    if job.cancel_requested:
                        finish(job, "cancelled", "已取消，远程结果未发布；已发送的请求仍可能计费。")
                        return
                    latest = repository.load(snapshot.id)
                    if latest.updated_at.isoformat() != job.revision:
                        finish(job, "stale", "项目输入已修改，生成结果未发布。请检查最新输入后重新提交。")
                        return
                    staged = stage_repository.load(snapshot.id)
                    relative = f"generated/web-{job.id}.png"
                    destination = repository.project_dir(snapshot.id) / relative
                    from PIL import Image
                    with Image.open(result.local_files[0]) as image:
                        save_png_atomic(image.copy(), destination)
                    # Core has already performed confirmation and downstream
                    # invalidation on the identical snapshot. Publish once.
                    staged.generations[-1].artifact_path = relative
                    staged.artifacts.generation = [relative]
                    staged.processing_parameters["generation"]["mode"] = mode.value
                    web = dict(staged.processing_parameters.get("web_workspace", {}))
                    inputs = dict(web.get("creative_generations", {}))
                    inputs[relative] = {"reference_id": request_data.reference_path.as_posix(),
                        "request_id": job.request_id, "size": request_data.size,
                        "structure_level": request_data.structure_level.value,
                        "target_application": request_data.target_application.value,
                        "colors": request_data.colors, "negative_constraints": _redacted(request_data.negative_constraints),
                        "mode": mode.value, "created_at": _now()}
                    web["creative_generations"] = inputs
                    staged.processing_parameters["web_workspace"] = web
                    staged.updated_at = datetime.now(UTC)
                    try:
                        repository.save(staged)
                    except Exception:
                        destination.unlink(missing_ok=True)
                        raise
                    job.artifacts = [relative]
                    captured = capture(staged, "AI 生成作品保存", published=True)
                    finish(job, "succeeded", "生成完成，已保存 AI 辅助作品。" if captured else "生成作品已保存，但版本快照未能写入，请检查磁盘。")
        except GenerationFailure as error:
            with lock:
                if job.cancel_requested:
                    finish(job, "cancelled", "已取消，未发布结果；远程请求仍可能计费。")
                else:
                    # Use a fixed local message, never remote response content.
                    finish(job, "failed", USER_MESSAGE_ZH[error.kind], error.kind.value)
        except Exception:
            with lock:
                if job.cancel_requested:
                    finish(job, "cancelled", "已取消，未发布结果。")
                else:
                    finish(job, "failed", "生成未完成，未修改项目。请检查设置和本地磁盘后手动重试。", "local_error")

    @app.post("/api/projects/{project_id}/generation", status_code=202)
    def generate(project_id: str, data: GenerationEdit, request: Request, response: Response):
        with lock:
            identifier, value = session(request, response)
            fingerprint = sha256(data.model_dump_json().encode()).hexdigest()
            duplicate = next((j for j in jobs.values() if j.session == identifier and j.project_id == project_id and j.request_id == data.request_id), None)
            if duplicate:
                if duplicate.fingerprint != fingerprint:
                    raise HTTPException(409, "此请求编号已用于其他生成参数，请创建新请求。")
                return {"job": duplicate.public(), "project": public(repository.load(project_id), True)}
            project = current(project_id, data.revision)
            if not data.paid_confirmed:
                raise HTTPException(400, "请确认发送参考图和提示词，并知悉可能产生生成费用。")
            if any(j.project_id == project_id and j.status in _ACTIVE for j in jobs.values()):
                raise HTTPException(409, "项目已有正在进行的生成任务，请等待完成或取消。")
            if sum(j.status in _ACTIVE for j in jobs.values()) >= 4:
                raise HTTPException(429, "本地生成任务已满，请等待现有任务完成。")
            if StepId.EXTRACTION not in project.confirmed_steps:
                raise HTTPException(400, "请先保存提取结果。")
            config = configured(value)
            provider = config.provider(data.provider)
            try:
                SettingsChange.safe_endpoint(provider.base_url)
            except ValueError:
                raise HTTPException(400, "提供方服务地址无效，请在设置中修正。") from None
            if data.model is not None and data.model != provider.default_model:
                raise HTTPException(400, "模型与当前设置不同，请更新设置后重新提交。")
            if data.size not in provider.size_options:
                raise HTTPException(400, "当前模型不支持所选输出尺寸。")
            if data.negative_constraints.strip() and data.provider is ProviderId.SEEDREAM:
                raise HTTPException(400, "当前 Seedream 接口不支持排除内容，请将要求写入提示词，或选择 Qwen。")
            if any(color not in {c.hex_value for c in catalog.colors} for color in data.colors):
                raise HTTPException(400, "请选择色卡内的传统色彩。")
            references = {a["id"] for a in allowed_artworks(project, references=True).values() if a["kind"] != "mockup"}
            extraction = confirmed_extraction(repository.project_dir(project.id), project)
            reference = data.reference_id or (extraction[0] if extraction else None)
            if reference not in references:
                raise HTTPException(400, "参考图必须是当前已确认的提取、重组或生成作品。")
            safe_artifact(project, reference)
            if data.mode is CredentialMode.BYOK:
                credential = value.keys.get(data.provider)
                if credential is None:
                    raise HTTPException(400, "请先在设置中填写该提供方的会话密钥。")
            else:
                try:
                    credential = config.platform_credential(data.provider)
                except ConfigError:
                    raise HTTPException(400, "未配置平台密钥，请选择会话密钥或配置本地环境变量。") from None
            generation_request = GenerationRequest(prompt=data.prompt, reference_path=Path(reference), model=provider.default_model,
                provider=data.provider, size=data.size, structure_level=data.structure_level, target_application=data.target_application,
                colors=data.colors, negative_constraints=data.negative_constraints)
            job = _Job(uuid4().hex, identifier, project_id, data.revision, data.request_id, fingerprint, data.provider.value)
            if len(jobs) >= 500:
                raise HTTPException(429, "当前服务会话的生成记录已达上限，请重启本地服务后继续。")
            capture(project, "AI 生成前的状态")
            jobs[job.id] = job
            try:
                Thread(target=run_job, args=(job, project.model_copy(deep=True), generation_request, config, credential, data.mode),
                       name=f"pattern-generation-{job.id[:8]}", daemon=True).start()
            except RuntimeError:
                jobs.pop(job.id, None)
                raise HTTPException(503, "本地生成任务暂时无法启动，请稍后重试。") from None
            return {"job": job.public(), "project": public(project, True)}

    def owned_job(project_id, job_id, request):
        job = jobs.get(job_id)
        if job is None or job.project_id != project_id or job.session != request.cookies.get(_COOKIE):
            raise HTTPException(404, "生成任务不存在；服务重启后会清除会话任务。")
        return job

    @app.get("/api/projects/{project_id}/generation/jobs/{job_id}")
    def get_job(project_id: str, job_id: str, request: Request):
        with lock:
            return {"job": owned_job(project_id, job_id, request).public(), "project": public(repository.load(project_id), True)}

    @app.post("/api/projects/{project_id}/generation/jobs/{job_id}/cancel")
    def cancel_job(project_id: str, job_id: str, request: Request):
        with lock:
            job = owned_job(project_id, job_id, request)
            if job.status in _ACTIVE:
                job.cancel_requested = True
                if job.status == "queued":
                    finish(job, "cancelled", "已取消，未发送生成请求。")
                else:
                    job.status = "cancelling"
                    job.message = "已停止等待发布；已发送的远程请求可能继续执行并计费。"
            return {"job": job.public(), "project": public(repository.load(project_id), True)}

    @app.post("/api/projects/{project_id}/creative/exports")
    def export_creative(project_id: str, data: CreativeExport):
        with lock:
            project = current(project_id, data.revision)
            eligible = allowed_artworks(project)
            artwork = eligible.get(data.artwork_id)
            if artwork is None:
                raise HTTPException(400, "请选择当前已保存的重组、生成或贴图作品。")
            source = safe_artifact(project, data.artwork_id)
            capture(project, "作品导出前的状态")
            export_id = uuid4().hex
            folder = Path(export_root).resolve() / project.id / export_id
            folder.mkdir(parents=True, exist_ok=False)
            filename = f"pattern-{artwork['kind']}.{data.format}"
            target = folder / filename
            try:
                if data.format == "png":
                    shutil.copyfile(source, target)
                else:
                    selected = project.model_copy(deep=True)
                    selected.artifacts.extraction = []
                    selected.artifacts.recomposition = [data.artwork_id] if artwork["kind"] == "pattern" else []
                    selected.artifacts.generation = [data.artwork_id] if artwork["kind"] == "generation" else []
                    selected.generations = [g for g in project.generations if g.artifact_path == data.artwork_id]
                    selected.processing_parameters["current_mockups"] = [data.artwork_id] if artwork["kind"] == "mockup" else []
                    package = Exporter(repository.project_dir(project_id)).export(selected, ExportSelection(
                        source=data.include_original, patterns=artwork["kind"] == "pattern", generations=artwork["kind"] == "generation",
                        mockups=artwork["kind"] == "mockup", report=True), folder)
                    web = project.processing_parameters.get("web_workspace", {})
                    creative_inputs = web.get("creative_generations", {}).get(data.artwork_id)
                    if creative_inputs:
                        (package / "creative-settings.json").write_text(
                            json.dumps(_redacted_tree(creative_inputs), ensure_ascii=False, indent=2), encoding="utf-8")
                    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
                        for path in sorted(package.rglob("*")):
                            if path.is_file():
                                archive.write(path, path.relative_to(package).as_posix())
                record = {"id": export_id, "filename": filename, "format": data.format,
                          "source": artwork["kind"], "source_artifact": data.artwork_id, "created_at": _now(),
                          "ai_assisted": artwork["ai_assisted"], "url": f"/api/projects/{project_id}/exports/{export_id}"}
                web = dict(project.processing_parameters.get("web_workspace", {}))
                web["exports"] = [record, *web.get("exports", [])]
                project.processing_parameters["web_workspace"] = web
                project.updated_at = datetime.now(UTC)
                repository.save(project)
            except Exception:
                # The unindexed folder is private and cannot be downloaded.
                raise
            captured = capture(project, "作品导出保存", published=True)
            return {"export": record, "project": public(project, True),
                    "warning": None if captured else "导出已保存，但版本快照未能写入，请检查磁盘。"}

    return {"jobs": jobs}
