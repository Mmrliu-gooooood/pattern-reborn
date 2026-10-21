"""Local, same-origin HTTP adapter for the independent creation workspace.

Creative services require explicit per-request generation consent. Existing v1
projects remain readable by Streamlit; web UI metadata has its own namespace.
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime
from io import BytesIO
import json
from html import escape
import os
import shutil
from zipfile import ZipFile, ZIP_DEFLATED
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

import numpy as np
from PIL import Image
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .domain import CategoryId, ProfileId, ProvenanceClass, StepId
from .exporter import Exporter, ExportSelection, _redact_payload
from .vectorize import Vectorizer
from .web_design import DesignEdit, DesignSettings, palette_for, render_design
from .web_projects import register_project_routes
from .web_creative import register_creative_routes
from .web_extraction import ExtractionSettings, extract_local, extraction_capabilities
from .images import load_working_image, probe_image, save_png_atomic
from .knowledge import KnowledgeCatalog
from .projects import ProjectNotFoundError, ProjectRepository
from .segmentation import MaskEditMode, MaskStroke, SegmentHints
from .workflow import CreateProjectCommand, ExtractCommand, PatternRebornService

ROOT = Path(__file__).resolve().parents[2]
MAX_REQUEST = 24 * 1024 * 1024


class Stroke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["keep", "remove"]
    points: list[tuple[StrictInt, StrictInt]] = Field(min_length=1, max_length=3000)
    width: int = Field(ge=1, le=200, strict=True)


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    box: tuple[StrictInt, StrictInt, StrictInt, StrictInt] | None = None
    strokes: list[Stroke] = Field(default_factory=list, max_length=100)
    feather: int = Field(default=0, ge=0, le=10, strict=True)
    profile: ProfileId
    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)


class ProjectChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    name: str | None = Field(default=None, min_length=1, max_length=80)
    archived: bool | None = None


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    source: Literal["result", "pattern"] = "pattern"
    format: Literal["png", "svg", "zip"] = "png"
    include_original: bool = False


def _png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _data_url(image: Image.Image) -> str:
    return "data:image/png;base64," + base64.b64encode(_png(image)).decode("ascii")


def create_app(workspace: Path | None = None, *, root: Path = ROOT, settings_path: Path | None = None) -> FastAPI:
    root = root.resolve()
    repository = ProjectRepository(workspace or Path(os.getenv("PATTERN_REBORN_WORKSPACE", root / "workspace")))
    catalog = KnowledgeCatalog.load(root / "data/knowledge")
    export_root = Path(os.getenv("PATTERN_REBORN_OUTPUTS", root / "outputs"))
    service = PatternRebornService(repository, knowledge=catalog, export_root=export_root)
    lock = RLock()  # One local process serializes read-modify-write operations.
    app = FastAPI(title="纹启新生 · 本地工作台", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        # Reject cross-origin readers too. JSON mutations require an explicit
        # custom header, so third-party forms cannot operate the local service.
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return JSONResponse({"detail": "仅允许从本地工作台访问。"}, status_code=403)
        # A normal link/bookmark may open the public app shell. Project data
        # and mutations remain same-origin, including cross-site API reads.
        entry_navigation = request.method == "GET" and request.url.path == "/"
        if request.headers.get("sec-fetch-site") == "cross-site" and not entry_navigation:
            return JSONResponse({"detail": "不允许跨站请求。"}, status_code=403)
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            if request.headers.get("x-pattern-reborn") != "local-workspace":
                return JSONResponse({"detail": "请从本地工作台执行操作。"}, status_code=403)
            request_limit = 256 * 1024 * 1024 if request.url.path == "/api/projects/import" else MAX_REQUEST
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > request_limit:
                    return JSONResponse({"detail": "备份文件超过 256 MB。" if request_limit != MAX_REQUEST else "文件过大，请使用小于 24 MB 的图片。"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid_input(request: Request, error: ValueError):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(ProjectNotFoundError)
    async def not_found(request: Request, error: ProjectNotFoundError):
        return JSONResponse({"detail": "项目不存在或已被移动。"}, status_code=404)

    @app.exception_handler(OSError)
    async def storage_failure(request: Request, error: OSError):
        return JSONResponse({"detail": "本地文件暂时无法读取或保存，请检查磁盘后重试。"}, status_code=503)

    def records():
        # list_recent already scans and validates every project. No arbitrary
        # recent-three cutoff for the library.
        return repository.list_recent(limit=2**31 - 1)

    def safe_artifact(project, relative: str) -> Path:
        base = repository.project_dir(project.id)
        target = (base / relative).resolve()
        if Path(relative).is_absolute() or not target.is_relative_to(base) or ".." in Path(relative).parts:
            raise HTTPException(400, "文件路径无效。")
        if not target.is_file():
            raise HTTPException(404, "文件不存在。")
        return target

    def source(project):
        return load_working_image(safe_artifact(project, project.source.relative_path))

    def public(project, detail=False):
        web = project.processing_parameters.get("web_workspace", {})
        result_id = next((p for p in project.artifacts.extraction if p.startswith("extracted/") and p not in project.stale_artifacts), None)
        mask_id = next((p for p in project.artifacts.extraction if p.startswith("masks/") and p not in project.stale_artifacts), None)
        pattern_id = next((p for p in project.artifacts.recomposition if p.endswith(".png") and p not in project.stale_artifacts), None)
        value = {
            "id": project.id, "name": project.name, "category": project.category.value,
            "category_label": next(c.display_name_zh for c in catalog.categories if c.id == project.category),
            "profile": (project.profile or catalog.profile_for(project.category).id).value,
            "revision": project.updated_at.isoformat(), "updated_at": project.updated_at.isoformat(),
            "archived": bool(web.get("archived", False)), "demo": False,
            "image": f"/api/projects/{project.id}/image?kind=source&size=thumbnail",
            "has_result": result_id is not None,
            "has_pattern": pattern_id is not None,
        }
        if detail:
            image = source(project)
            value.update({
                "width": image.width, "height": image.height,
                "source_url": f"/api/projects/{project.id}/image?kind=source",
                "result_url": f"/api/projects/{project.id}/image?kind=result&v={project.updated_at.timestamp()}" if result_id else None,
                "mask_url": f"/api/projects/{project.id}/image?kind=mask&v={project.updated_at.timestamp()}" if mask_id else None,
                "draft": web.get("edit"), "source_name": project.source.original_filename,
                "warnings": web.get("extraction_warnings", []),
                "pattern_url": f"/api/projects/{project.id}/image?kind=pattern&v={project.updated_at.timestamp()}" if pattern_id else None,
                "source_sha256": project.source.sha256,
                "rights": web.get("rights", {"creator": "用户提供", "license": "未核实", "source": "本地上传"}),
                "provenance": project.provenance.value,
                "has_downstream": bool(project.artifacts.analysis or project.artifacts.recomposition or project.generations or project.artifacts.export),
            })
        return value

    demo_root = root / "data/demo"
    manifest = json.loads((demo_root / "manifest.json").read_text(encoding="utf-8"))
    demos = {}
    preferred = ["peony-embroidery", "fish-lotus-blue-calico", "new-year-picture-detail", "lotus-paper-cut", "scrolling-lotus-ceramic", "architectural-cloud"]
    for entry in manifest["cases"]:
        path = (demo_root / entry["source"]).resolve()
        if not path.is_relative_to(demo_root.resolve()) or not path.is_file():
            continue
        metadata = json.loads((path.parent / "metadata.json").read_text(encoding="utf-8"))
        demos[entry["id"]] = (entry, path, metadata)

    @app.get("/api/library")
    def library():
        with lock:
            examples = []
            for demo_id in preferred:
                if demo_id not in demos:
                    continue
                entry, path, metadata = demos[demo_id]
                examples.append({"id": demo_id, "name": entry["title_zh"], "category": metadata["category"], "category_label": next(c.display_name_zh for c in catalog.categories if c.id.value == metadata["category"]), "demo": True, "image": f"/api/examples/{demo_id}/image", "creator": metadata["creator_institution"], "license": metadata["license"], "has_result": False})
            return {"projects": [public(p) for p in records()], "examples": examples, "categories": [{"id": c.id.value, "name": c.display_name_zh} for c in catalog.categories]}

    @app.get("/api/examples/{demo_id}/image")
    def example_image(demo_id: str):
        if demo_id not in demos:
            raise HTTPException(404, "示例不存在。")
        return Response(_png(load_working_image(demos[demo_id][1], max_edge=720)), media_type="image/png")

    @app.post("/api/examples/{demo_id}/open")
    def open_example(demo_id: str):
        if demo_id not in demos:
            raise HTTPException(404, "示例不存在。")
        with lock:
            for project in records():
                web = project.processing_parameters.get("web_workspace", {})
                if web.get("demo_id") == demo_id and not web.get("archived"):
                    return public(project, True)
            entry, path, metadata = demos[demo_id]
            project = service.create_project(CreateProjectCommand(name=entry["title_zh"], source=path, category=CategoryId(metadata["category"]), provenance=ProvenanceClass.TRADITIONAL_REFERENCE))
            project.processing_parameters["web_workspace"] = {"demo_id": demo_id, "rights": {"creator": metadata["creator_institution"], "license": metadata["license"], "source": metadata["source_url"]}}
            repository.save(project)
            return published(project, "项目状态保存")

    @app.post("/api/projects")
    def upload(name: str = Form(..., min_length=1, max_length=80), category: CategoryId = Form(...), file: UploadFile = File(...)):
        if not name.strip():
            raise HTTPException(400, "请填写项目名称。")
        suffix = Path(file.filename or "source.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            raise HTTPException(400, "请选择 PNG、JPEG、WebP、BMP 或 TIFF 图片。")
        temp_dir = root / ".cache/web-upload"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp = temp_dir / f"{uuid4().hex}{suffix}"
        try:
            temp.write_bytes(file.file.read(MAX_REQUEST + 1))
            if temp.stat().st_size > MAX_REQUEST:
                raise HTTPException(413, "图片过大。")
            probe_image(temp)
            with lock:
                project = service.create_project(CreateProjectCommand(name=name.strip(), source=temp, category=category, provenance=ProvenanceClass.USER_SUPPLIED_UNVERIFIED))
                project.source.original_filename = (file.filename or "source" + suffix).replace("\\", "/").rsplit("/", 1)[-1]
                repository.save(project)
                return published(project, "创建项目")
        finally:
            temp.unlink(missing_ok=True)
            file.file.close()

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        with lock:
            return public(repository.load(project_id), True)

    def current(project_id, revision):
        if any(job.project_id == project_id and job.status in {"queued", "running", "cancelling"}
               for job in creative_state["jobs"].values()):
            raise HTTPException(409, "项目正在生成作品，请等待任务结束或取消后再修改、保存或导出。")
        project = repository.load(project_id)
        if project.updated_at.isoformat() != revision:
            raise HTTPException(409, "项目已在其他窗口更新，请重新打开后编辑。")
        return project

    def published(project, label):
        value = public(project, True)
        try:
            auto_snapshot(project, label)
        except (OSError, ValueError, HTTPException):
            value["warnings"] = [*value.get("warnings", []), "作品已保存，但版本备份未完成，请检查磁盘后手动保存版本。"]
        return value

    @app.patch("/api/projects/{project_id}")
    def change(project_id: str, data: ProjectChange):
        with lock:
            project = current(project_id, data.revision)
            if data.name is not None:
                if not data.name.strip():
                    raise HTTPException(400, "名称不能为空。")
                project.name = data.name.strip()
            if data.archived is not None:
                web = dict(project.processing_parameters.get("web_workspace", {}))
                web["archived"] = data.archived
                project.processing_parameters["web_workspace"] = web
            project.updated_at = datetime.now(UTC)
            repository.save(project)
            return published(project, "项目状态保存")

    @app.get("/api/projects/{project_id}/image")
    def project_image(project_id: str, kind: Literal["source", "result", "mask", "pattern"] = "source", size: Literal["working", "thumbnail"] = "working", download: bool = False):
        with lock:
            project = repository.load(project_id)
            relative = project.source.relative_path
            if kind == "pattern":
                relative = design_artifact(project, "pattern")
            elif kind != "source":
                prefix = "extracted/" if kind == "result" else "masks/"
                relative = next((p for p in project.artifacts.extraction if p.startswith(prefix) and p not in project.stale_artifacts), "")
                if not relative:
                    raise HTTPException(404, "尚无已保存的提取结果。")
            path = safe_artifact(project, relative)
            if download and kind == "result":
                return FileResponse(path, media_type="image/png", filename="pattern-extracted.png")
            return Response(_png(load_working_image(path, max_edge=720 if size == "thumbnail" else 2048)), media_type="image/png")

    def compute(project, data: Edit):
        image = source(project).convert("RGBA")
        width, height = image.size
        if data.box is not None:
            x0, y0, x1, y1 = data.box
            if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                raise HTTPException(400, "选区必须位于图像内，且宽高不能为零。")
        if sum(len(s.points) for s in data.strokes) > 20000:
            raise HTTPException(400, "笔触过多，请分次保存。")
        for stroke in data.strokes:
            if any(not (0 <= x < width and 0 <= y < height) for x, y in stroke.points):
                raise HTTPException(400, "笔触超出图像范围。")
        array = np.asarray(image)
        rgb = np.ascontiguousarray(array[:, :, :3])
        hints = SegmentHints(box=data.box)
        result = extract_local(rgb, np.ascontiguousarray(array[:, :, 3]), data.profile, hints, data.extraction,
                               strokes=[MaskStroke(MaskEditMode(stroke.mode), stroke.points, stroke.width) for stroke in data.strokes],
                               feather=data.feather, root=root)
        return result

    @app.post("/api/projects/{project_id}/preview")
    def preview(project_id: str, data: Edit):
        with lock:
            result = compute(current(project_id, data.revision), data)
            return {"result": _data_url(result.rgba), "mask": _data_url(Image.fromarray(result.mask)), "empty": not bool(np.any(result.mask)), "warnings": result.warnings}

    @app.post("/api/projects/{project_id}/save")
    def save(project_id: str, data: Edit):
        with lock:
            project = current(project_id, data.revision)
            result = compute(project, data)
            if not np.any(result.mask):
                raise HTTPException(400, "没有提取到纹样，请调整选区或使用保留笔刷。")

            auto_snapshot(project, "提取前的状态")

            class PreparedSegmenter:
                def segment(self, image, profile, hints):
                    return result

            local_service = PatternRebornService(repository, knowledge=catalog, export_root=export_root, segmenter=PreparedSegmenter())
            artifact = local_service.extract(project_id, ExtractCommand(profile=data.profile, hints=result.hints))
            save_png_atomic(result.rgba, artifact.path)
            project = local_service.confirm_extraction(project_id, artifact.artifact_id)
            web = dict(project.processing_parameters.get("web_workspace", {}))
            web["edit"] = data.model_dump(mode="json", exclude={"revision"})
            web["extraction_warnings"] = result.warnings
            project.processing_parameters["web_workspace"] = web
            project.updated_at = datetime.now(UTC)
            repository.save(project)
            return published(project, "提取保存")

    def design_artifact(project, kind="result"):
        paths = project.artifacts.recomposition if kind == "pattern" else project.artifacts.extraction
        prefix = "patterns/" if kind == "pattern" else "extracted/"
        relative = next((p for p in paths if p.startswith(prefix) and p.endswith(".png") and p not in project.stale_artifacts), None)
        if not relative:
            raise HTTPException(400, "请先保存重组作品。" if kind == "pattern" else "请先保存提取纹样。")
        return relative

    def motif(project):
        with Image.open(safe_artifact(project, design_artifact(project))) as image:
            return image.convert("RGBA")

    @app.get("/api/projects/{project_id}/design")
    def design_context(project_id: str):
        with lock:
            project = repository.load(project_id)
            web = project.processing_parameters.get("web_workspace", {})
            saved = web.get("design", {})
            same_source = saved.get("source_artifact") == design_artifact(project)
            capability = Vectorizer().capability()
            return {"settings": saved.get("settings") if same_source else DesignSettings().model_dump(mode="json"),
                    "palette": palette_for(motif(project)), "svg_available": capability.available,
                    "svg_reason": capability.reason_zh, "exports": web.get("exports", []),
                    "project": public(project, True)}

    @app.post("/api/projects/{project_id}/design/preview")
    def design_preview(project_id: str, data: DesignEdit):
        with lock:
            project = current(project_id, data.revision)
            image = render_design(motif(project), data.settings)
            image.thumbnail((1200, 1200))
            return {"image": _data_url(image)}

    @app.post("/api/projects/{project_id}/design/save")
    def design_save(project_id: str, data: DesignEdit):
        with lock:
            project = current(project_id, data.revision)
            source_id = design_artifact(project)
            image = render_design(motif(project), data.settings)
            auto_snapshot(project, "重组前的状态")
            if StepId.ANALYSIS not in project.confirmed_steps:
                service.analyze(project_id)
            relative = f"patterns/web-{uuid4().hex}.png"
            save_png_atomic(image, repository.project_dir(project_id) / relative)
            project = repository.confirm(project_id, StepId.RECOMPOSITION, [relative])
            web = dict(project.processing_parameters.get("web_workspace", {}))
            web["design"] = {"settings": data.settings.model_dump(mode="json"), "source_artifact": source_id,
                             "artifact": relative, "algorithm": "palette-delta-crop-1"}
            project.processing_parameters.update(web_workspace=web, compose=data.settings.request().model_dump(mode="json"), current_step="recomposition")
            repository.save(project)
            return published(project, "重组与配色保存")

    @app.post("/api/projects/{project_id}/exports")
    def export_design(project_id: str, data: ExportRequest):
        with lock:
            project = current(project_id, data.revision)
            relative = design_artifact(project, data.source)
            source_path = safe_artifact(project, relative)
            export_id = uuid4().hex
            folder = export_root.resolve() / project.id / export_id
            folder.mkdir(parents=True, exist_ok=False)
            filename = f"pattern-{data.source}.{data.format}"
            target = folder / filename
            web = dict(project.processing_parameters.get("web_workspace", {}))
            if data.format == "svg":
                vector = Vectorizer().vectorize(source_path, target)
                if not vector.available:
                    raise HTTPException(400, vector.reason_zh)
            elif data.format == "png":
                shutil.copyfile(source_path, target)
            else:
                package = Exporter(repository.project_dir(project_id)).export(project, ExportSelection(
                    source=data.include_original, extracted=True, patterns=data.source == "pattern", report=True), folder)
                settings = {"project": project.name, "source_sha256": project.source.sha256,
                            "rights": web.get("rights"), "edit": web.get("edit"),
                            "design": web.get("design") if data.source == "pattern" else None}
                (package / "workspace-settings.json").write_text(json.dumps(_redact_payload(settings), ensure_ascii=False, indent=2), encoding="utf-8")
                with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
                    for path in sorted(package.rglob("*")):
                        if path.is_file():
                            archive.write(path, path.relative_to(package).as_posix())
            record = {"id": export_id, "filename": filename, "format": data.format,
                      "source": data.source, "source_artifact": relative, "created_at": datetime.now(UTC).isoformat(),
                      "url": f"/api/projects/{project_id}/exports/{export_id}"}
            web["exports"] = [record, *web.get("exports", [])]
            project.processing_parameters["web_workspace"] = web
            project.updated_at = datetime.now(UTC)
            repository.save(project)
            return {"export": record, "project": published(project, "导出文件保存")}

    @app.get("/api/projects/{project_id}/exports/{export_id}")
    def download_export(project_id: str, export_id: str):
        with lock:
            project = repository.load(project_id)
            record = next((r for r in project.processing_parameters.get("web_workspace", {}).get("exports", []) if r["id"] == export_id), None)
            if not record:
                raise HTTPException(404, "导出记录不存在。")
            base = export_root.resolve() / project.id
            path = (base / export_id / record["filename"]).resolve()
            if not path.is_relative_to(base) or not path.is_file():
                raise HTTPException(404, "导出文件不存在。")
            return FileResponse(path, filename=record["filename"], media_type={"png": "image/png", "svg": "image/svg+xml", "zip": "application/zip"}[record["format"]])

    auto_snapshot = register_project_routes(app, repository, lock, current, public, safe_artifact, export_root)
    creative_state = register_creative_routes(app, repository, catalog, lock, current, public, safe_artifact, export_root,
        auto_snapshot=auto_snapshot, root=root, settings_path=settings_path)
    app.state.creative = creative_state

    @app.get("/api/extraction/capabilities")
    def local_extraction_capabilities():
        return extraction_capabilities(root)

    @app.get("/api/help", response_class=HTMLResponse)
    def local_help():
        guide = root / "docs/product/user-guide.md"
        content = guide.read_text(encoding="utf-8") if guide.is_file() else "请查看 docs/product/local-release.md。"
        return "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>纹启新生 · 使用手册</title><style>body{max-width:850px;margin:40px auto;padding:0 24px;background:#faf8f0;color:#25463b;font:16px/1.9 system-ui}pre{white-space:pre-wrap;font:inherit}</style><h1>纹启新生 · 本地使用手册</h1><pre>" + escape(content) + "</pre></html>"

    dist = root / "web/dist/client"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="纹启新生本地工作台")
    parser.add_argument("--port", type=int, default=8510)
    args = parser.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
