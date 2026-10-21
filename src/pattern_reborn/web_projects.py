"""Local-only project drafts, immutable history and portable recovery archives.

The v1 project schema stays unchanged. Drafts and snapshots live beside the
project in ``.web-workspace``; image artifacts keep their existing immutable names.
No provider configuration or credentials are read by this module.
"""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import tempfile
from typing import Literal
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .domain import CategoryId, ProjectRecord, ProvenanceClass, SourceRecord, StepId
from .exporter import _redact_secrets
from .images import load_working_image, probe_image
from .mockups import _LOCK_MAGIC
from .projects import ProjectCorruptError, ProjectNotFoundError, ProjectRepository, ProjectRepositoryError
from .web_design import DesignSettings

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_UNPACKED_BYTES = 512 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_FILES = 2000
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_TOTAL_IMAGE_PIXELS = 268_435_456
SIDECAR = ".web-workspace"
_VERSION_ID = re.compile(r"^[a-f0-9]{32}$")
_HASH = re.compile(r"^[a-f0-9]{64}$")
_CREDENTIAL_KEY = re.compile(r"(?i)(?:api[_-]?key|authorization|credential|password|secret|access[_-]?token|refresh[_-]?token)")
_PROJECT_FOLDERS = {"source", "extracted", "masks", "analysis", "patterns", "generated", "mockups", SIDECAR}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_MOCKUP_RUNTIME_LOCK = re.compile(r"^mockups/\.(?P<stem>[A-Za-z0-9][A-Za-z0-9_-]*)\.mockup\.lock$")


class DraftSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: str = Field(min_length=1, max_length=80)
    data: dict


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=1, max_length=80)


class VersionCreate(Revision):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value):
        if not value.strip():
            raise ValueError("请填写版本名称。")
        return value.strip()


class Duplicate(Revision):
    name: str | None = Field(default=None, min_length=1, max_length=80)


class Recovery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: str


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=80)
    created_at: datetime
    revision: str
    automatic: bool
    project: ProjectRecord

    @field_validator("created_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("版本时间缺少时区。")
        return value.astimezone(UTC)


def _fail(message="项目备份无效，未更改现有项目。", status=400):
    raise HTTPException(status, message)


def _relative(value: str) -> PurePosixPath:
    """Reject Windows aliases as well as traversal before touching the disk."""
    if not isinstance(value, str) or not value or "\\" in value or len(value) > 500:
        _fail("文件路径无效。")
    path = PurePosixPath(value)
    if (path.is_absolute() or PureWindowsPath(value).drive or path.as_posix() != value
            or any(part in {".", "..", ""} for part in path.parts)):
        _fail("文件路径无效。")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    for part in path.parts:
        if (any(ord(c) < 32 or c in '<>:"|?*' for c in part) or part.endswith((".", " "))
                or part.split(".")[0].upper() in reserved):
            _fail("文件路径无效。")
    return path


def _contained(root: Path, relative: str) -> Path:
    path = root.joinpath(*_relative(relative).parts)
    base = root.resolve()
    # Inspect every lexical ancestor: resolving first would hide a symlink that
    # currently happens to point back inside the project.
    cursor = root
    for part in _relative(relative).parts:
        cursor = cursor / part
        try:
            mode = cursor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode.st_mode) or getattr(mode, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            _fail("项目包含链接文件，无法安全处理。")
    if not path.resolve().is_relative_to(base):
        _fail("文件路径超出项目目录。")
    return path


def _json(value) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        _fail("项目参数不是有效的 JSON 数据。")


def _read_json(path: Path):
    if path.stat().st_size > MAX_METADATA_BYTES:
        _fail("项目元数据过大。")
    try:
        return json.loads(path.read_bytes())
    except (UnicodeError, ValueError, RecursionError):
        _fail("项目元数据已损坏。")


def _sha256(path: Path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _clean(path: Path, parent: Path):
    """Only discard our generated staging directories under their exact parent."""
    if path.parent.resolve() != parent.resolve() or not path.name.startswith(".import-"):
        raise ValueError("临时目录位置无效。")
    if path.exists():
        shutil.rmtree(path)


def _scrub(value, depth=0):
    if depth > 50:
        _fail("项目参数嵌套过深。")
    if isinstance(value, str):
        return _redact_secrets(value)
    if isinstance(value, list):
        return [_scrub(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {key: _scrub(item, depth + 1) for key, item in value.items() if not _CREDENTIAL_KEY.search(key)}
    return value


def _web(project: ProjectRecord) -> dict:
    value = project.processing_parameters.get("web_workspace", {})
    if not isinstance(value, dict):
        _fail("项目工作台参数已损坏。")
    return value


def _active_image(project: ProjectRecord, kind: str):
    paths = project.artifacts.recomposition if kind == "pattern" else project.artifacts.extraction
    prefix = "patterns/" if kind == "pattern" else "extracted/"
    return next((p for p in paths if p.startswith(prefix) and p.endswith(".png") and p not in project.stale_artifacts), None)


def _references(project: ProjectRecord) -> set[str]:
    refs = {project.source.relative_path, *project.stale_artifacts}
    for paths in project.artifacts.model_dump().values():
        refs.update(paths)
    refs.update(g.artifact_path for g in project.generations)
    parameters = project.processing_parameters
    for value in parameters.get("current_mockups", []) if isinstance(parameters.get("current_mockups"), list) else []:
        if not isinstance(value, str):
            _fail("项目文件引用无效。")
        refs.add(value)
    pending = parameters.get("pending_extraction", {})
    if isinstance(pending, dict):
        for key in ("extracted_id", "mask_id", "artifact_id", "mask", "mask_path", "extracted_path"):
            if pending.get(key):
                refs.add(pending[key])
    design = _web(project).get("design", {})
    if isinstance(design, dict):
        for key in ("artifact", "source_artifact"):
            if design.get(key):
                refs.add(design[key])
    exports = _web(project).get("exports", [])
    if not isinstance(exports, list):
        _fail("导出记录无效。")
    for item in exports:
        if not isinstance(item, dict):
            _fail("导出记录无效。")
        if item.get("source_artifact"):
            refs.add(item["source_artifact"])
    return refs


def _validate_project(project: ProjectRecord, folder: Path, *, images=False):
    if not ProjectRepository._PROJECT_ID_PATTERN.fullmatch(project.id):
        _fail("项目标识无效。")
    for relative in _references(project):
        path = _contained(folder, relative)
        if not path.is_file():
            _fail("项目引用的素材或历史文件缺失。")
    source = _contained(folder, project.source.relative_path)
    if (not _HASH.fullmatch(project.source.sha256) or source.stat().st_size != project.source.byte_size
            or _sha256(source) != project.source.sha256):
        _fail("原始素材校验失败，备份未导入。")
    if images:
        probe_image(source)


def _snapshot_summary(snapshot: Snapshot):
    project = snapshot.project
    base = f"/api/projects/{project.id}/versions/{snapshot.id}"
    result = _active_image(project, "result") is not None
    pattern = _active_image(project, "pattern") is not None
    return {"id": snapshot.id, "name": snapshot.name, "created_at": snapshot.created_at.isoformat(),
            "revision": snapshot.revision, "automatic": snapshot.automatic,
            "has_result": result, "has_pattern": pattern,
            "result_url": base + "/image?kind=result" if result else None,
            "pattern_url": base + "/image?kind=pattern" if pattern else None}


def _draft_data(kind, value, revision):
    # Import at request time so this adapter can share the authoritative editor
    # schema without an import cycle with its composition root.
    if kind == "extract":
        from .web_api import Edit
        parsed = Edit.model_validate({**value, "revision": revision})
        if sum(len(stroke.points) for stroke in parsed.strokes) > 20000:
            _fail("草稿笔触过多。")
        return parsed.model_dump(mode="json", exclude={"revision"})
    if set(value) == {"settings"}:
        value = value["settings"]
    return DesignSettings.model_validate(value).model_dump(mode="json")


def _files(folder: Path):
    if not folder.exists():
        return
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        candidate = _contained(folder, relative)
        if candidate.is_file():
            if not stat.S_ISREG(candidate.stat().st_mode):
                _fail("项目包含不支持的文件类型。")
            yield relative, candidate


def _runtime_mockup_lock(relative, path, indexed_artifacts):
    """Recognize only the core's runtime lock for an indexed PNG artifact."""
    match = _MOCKUP_RUNTIME_LOCK.fullmatch(relative)
    return (match is not None and f"mockups/{match['stem']}.png" in indexed_artifacts
            and path.stat().st_size == len(_LOCK_MAGIC) and path.read_bytes() == _LOCK_MAGIC)


def _validate_layout(folder: Path, *, indexed_artifacts=()):
    allowed = {"source": _IMAGE_SUFFIXES, "extracted": _IMAGE_SUFFIXES, "masks": _IMAGE_SUFFIXES,
               "patterns": _IMAGE_SUFFIXES | {".svg"}, "analysis": {".json"},
               "generated": _IMAGE_SUFFIXES, "mockups": _IMAGE_SUFFIXES | {".json"}}
    for relative, path in _files(folder):
        parts = PurePosixPath(relative).parts
        if relative == "project.json":
            continue
        if parts[0] == SIDECAR:
            valid = (len(parts) == 3 and (
                (parts[1] == "versions" and path.suffix == ".json" and _VERSION_ID.fullmatch(path.stem)) or
                (parts[1] == "drafts" and parts[2] in {"extract.json", "design.json"}) or
                (parts[1] == "recovery" and path.suffix == ".txt" and _VERSION_ID.fullmatch(path.stem))))
            if not valid:
                _fail("备份的工作台文件结构无效。")
        elif _runtime_mockup_lock(relative, path, indexed_artifacts):
            # Older backups included these process-local files. Their manifest
            # hashes have already been checked; recreate locks only when needed.
            path.unlink()
        elif parts[0] not in allowed or path.suffix.lower() not in allowed[parts[0]]:
            _fail("备份包含不支持的项目文件。")


def _validate_export_layout(folder: Path):
    for relative, path in _files(folder):
        parts = PurePosixPath(relative).parts
        if (len(parts) < 2 or not _VERSION_ID.fullmatch(parts[0])
                or path.suffix.lower() not in _IMAGE_SUFFIXES | {".svg", ".zip", ".json", ".md", ".txt"}):
            _fail("备份的导出目录结构无效。")


def _metadata_bytes(relative, path):
    if path.stat().st_size > MAX_FILE_BYTES:
        _fail("项目中的文件超过备份上限。", 413)
    data = path.read_bytes()
    if path.suffix.lower() == ".json":
        parsed = _read_json(path)
        sanitized = _scrub(parsed)
        return data if sanitized == parsed else _json(sanitized)
    if path.suffix.lower() in {".txt", ".md", ".svg", ".csv"}:
        try:
            return _redact_secrets(data.decode("utf-8")).encode("utf-8")
        except UnicodeDecodeError:
            _fail("文本文件编码无效。")
    return data


def _archive_index(archive: ZipFile):
    files = {}
    aliases = set()
    total = 0
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_FILES:
        _fail("备份中的文件数量超出上限。", 413)
    for info in entries:
        if info.orig_filename != info.filename:
            _fail("备份文件名包含无效字符。")
        name = info.filename[:-1] if info.is_dir() else info.filename
        _relative(name)
        alias = name.casefold()
        mode = info.external_attr >> 16
        if alias in aliases or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
            _fail("备份包含重复路径或链接文件。")
        aliases.add(alias)
        if info.flag_bits & 1:
            _fail("不支持加密备份。")
        total += info.file_size
        if info.file_size > MAX_FILE_BYTES or total > MAX_UNPACKED_BYTES:
            _fail("备份解压后的大小超出上限。", 413)
        if info.is_dir():
            continue
        files[name] = info
    # A file cannot also be an ancestor directory (including case aliases).
    file_aliases = {name.casefold() for name in files}
    for name in files:
        if any(parent.as_posix().casefold() in file_aliases for parent in PurePosixPath(name).parents if parent.as_posix() != "."):
            _fail("备份中的目录结构无效。")
    return files


def _unpack(archive: ZipFile, folder: Path):
    files = _archive_index(archive)
    for name, info in files.items():
        target = _contained(folder, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Never use extractall: member names have already passed both the
        # platform-independent parser and lexical containment checks.
        with archive.open(info) as source, target.open("xb") as output:
            copied = 0
            while chunk := source.read(1024 * 1024):
                copied += len(chunk)
                if copied > info.file_size or copied > MAX_FILE_BYTES:
                    _fail("备份文件大小与目录记录不符。", 413)
                output.write(chunk)
            if copied != info.file_size:
                _fail("备份文件不完整。")
    return files


class _Workspace:
    def __init__(self, repository, export_root):
        self.repository = repository
        self.export_root = Path(export_root).resolve()

    def path(self, project_id, relative):
        return _contained(self.repository.project_dir(project_id), relative)

    def snapshots(self, project_id):
        folder = self.path(project_id, f"{SIDECAR}/versions")
        snapshots = []
        if folder.is_dir():
            for path in folder.glob("*.json"):
                try:
                    snapshots.append(self.snapshot(project_id, path.stem))
                except (HTTPException, ValidationError, OSError):
                    continue
        return sorted(snapshots, key=lambda item: item.created_at, reverse=True)

    def snapshot(self, project_id, version_id):
        if not _VERSION_ID.fullmatch(version_id):
            _fail("历史版本不存在。", 404)
        path = self.path(project_id, f"{SIDECAR}/versions/{version_id}.json")
        if not path.is_file():
            _fail("历史版本不存在。", 404)
        try:
            snapshot = Snapshot.model_validate(_read_json(path))
        except ValidationError:
            _fail("历史版本元数据已损坏。")
        if snapshot.project.id != project_id or snapshot.id != version_id:
            _fail("历史版本标识不一致。")
        return snapshot

    def make_snapshot(self, project, name, automatic=False):
        _validate_project(project, self.repository.project_dir(project.id))
        payload = _scrub(project.model_dump(mode="json"))
        if automatic:
            for existing in self.snapshots(project.id):
                if existing.revision == project.updated_at.isoformat() and existing.project.model_dump(mode="json") == payload:
                    return existing
        snapshot = Snapshot(id=uuid4().hex, name=name[:80], created_at=datetime.now(UTC),
                            revision=project.updated_at.isoformat(), automatic=automatic, project=payload)
        path = self.path(project.id, f"{SIDECAR}/versions/{snapshot.id}.json")
        _atomic(path, _json(snapshot.model_dump(mode="json")))
        return snapshot

    def exports(self, project):
        values = _web(project).get("exports", [])
        if not isinstance(values, list):
            _fail("导出历史无效。")
        seen = set()
        for value in values:
            if not isinstance(value, dict) or not _VERSION_ID.fullmatch(str(value.get("id", ""))):
                _fail("导出历史标识无效。")
            export_id = value["id"]
            filename = value.get("filename", "")
            if len(_relative(filename).parts) != 1 or export_id in seen or value.get("format") not in {"png", "svg", "zip"}:
                _fail("导出历史文件名无效。")
            seen.add(export_id)
            yield value

    def bundle(self, project):
        folder = self.repository.project_dir(project.id)
        _validate_project(project, folder)
        indexed_artifacts = _references(project)
        for snapshot in self.snapshots(project.id):
            _validate_project(snapshot.project, folder)
            indexed_artifacts.update(_references(snapshot.project))
        manifest = {"format": "pattern-reborn-local-backup", "version": 1,
                    "created_at": datetime.now(UTC).isoformat(), "project_id": project.id, "files": {}}
        stream = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        try:
            with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
                total = 0
                def write(name, data):
                    nonlocal total
                    total += len(data)
                    if len(data) > MAX_FILE_BYTES or total > MAX_UNPACKED_BYTES or len(manifest["files"]) >= MAX_ARCHIVE_FILES - 1:
                        _fail("项目过大，请分开备份导出文件。", 413)
                    archive.writestr(name, data)
                    manifest["files"][name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

                for relative, path in _files(folder):
                    parts = PurePosixPath(relative).parts
                    if relative != "project.json" and parts[0] not in _PROJECT_FOLDERS:
                        continue
                    if any(part.endswith(".tmp") for part in parts):
                        continue
                    if _runtime_mockup_lock(relative, path, indexed_artifacts):
                        continue
                    write("project/" + relative, _metadata_bytes(relative, path))
                exports = list(self.exports(project))
                external = _contained(self.export_root, project.id)
                for value in exports:
                    if not _contained(external, value["id"] + "/" + value["filename"]).is_file():
                        _fail("历史导出文件缺失，无法完整备份。")
                for relative, path in _files(external):
                    write("exports/" + relative, _metadata_bytes(relative, path))
                archive.writestr("manifest.json", _json(manifest))
            if stream.tell() > MAX_ARCHIVE_BYTES:
                _fail("备份压缩文件过大。", 413)
            stream.seek(0)
            return stream
        except BaseException:
            stream.close()
            raise

    def _validate_bundle(self, unpacked, names):
        manifest = _read_json(unpacked / "manifest.json")
        if not isinstance(manifest, dict) or manifest.get("format") != "pattern-reborn-local-backup" or manifest.get("version") != 1:
            return self._legacy(unpacked, manifest, names)
        index = manifest.get("files")
        if not isinstance(index, dict) or set(index) != set(names) - {"manifest.json"}:
            _fail("备份文件清单不完整。")
        for name, record in index.items():
            if not name.startswith(("project/", "exports/")) or not isinstance(record, dict):
                _fail("备份文件清单无效。")
            path = _contained(unpacked, name)
            if record.get("size") != path.stat().st_size or record.get("sha256") != _sha256(path):
                _fail("备份文件校验失败。")
        try:
            project = ProjectRecord.model_validate(_read_json(unpacked / "project/project.json"))
        except (ValidationError, FileNotFoundError):
            _fail("备份的项目格式不受支持或已损坏。")
        if manifest.get("project_id") != project.id:
            _fail("备份项目标识不一致。")
        return project, None

    def _legacy(self, unpacked, manifest, names):
        """Convert our source-inclusive delivery ZIP into an editable v1 project."""
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
            _fail("请选择本工作台的项目备份或包含原图的作品包。")
        entries = manifest["files"]
        if len(entries) > MAX_ARCHIVE_FILES:
            _fail("作品包中的素材数量超出上限。", 413)
        seen = set()
        for item in entries:
            if not isinstance(item, dict) or item.get("path") not in names:
                _fail("作品包文件清单不完整。")
            if item["path"] in seen:
                _fail("作品包文件清单包含重复路径。")
            seen.add(item["path"])
            path = _contained(unpacked, item["path"])
            if item.get("sha256") != _sha256(path):
                _fail("作品包文件校验失败。")
        sources = [item for item in entries if item.get("kind") == "source"]
        if len(sources) != 1:
            _fail("作品包未包含原图，请从原项目导出完整项目备份。")
        metadata = manifest.get("source", {})
        original = _contained(unpacked, sources[0]["path"])
        if metadata.get("sha256") != sources[0]["sha256"] or metadata.get("byte_size") != original.stat().st_size:
            _fail("作品包的原图校验失败。")
        settings = _read_json(unpacked / "workspace-settings.json") if "workspace-settings.json" in names else {}
        if not isinstance(settings, dict):
            _fail("作品包编辑参数无效。")
        edit = settings.get("edit")
        profile = edit.get("profile") if isinstance(edit, dict) else None
        categories = {"silhouette": CategoryId.PAPER_CUTTING, "textile": CategoryId.EMBROIDERY_BROCADE,
                      "artifact_photo": CategoryId.CERAMIC_ORNAMENT, "flat_color": CategoryId.FOLK_PAINTING}
        now = datetime.now(UTC)
        source_relative = "source/" + sources[0]["sha256"][:16] + original.suffix.lower()
        project_dir = unpacked / "project"
        _contained(project_dir, source_relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, _contained(project_dir, source_relative))
        project = ProjectRecord(id="project-" + uuid4().hex, name=manifest.get("project_name", "导入作品"),
                                category=categories.get(profile, CategoryId.PAPER_CUTTING),
                                provenance=ProvenanceClass(metadata.get("provenance")),
                                source=SourceRecord(original_filename=metadata.get("original_filename", original.name),
                                                    relative_path=source_relative, sha256=metadata["sha256"], byte_size=metadata["byte_size"]),
                                created_at=now, updated_at=now, profile=profile, confirmed_steps=[StepId.UPLOAD])
        web = {"rights": settings.get("rights") or {"creator": "作品包原作者", "license": "未核实", "source": "作品包导入"}}
        if isinstance(edit, dict):
            web["edit"] = _draft_data("extract", edit, now.isoformat())
        for index, item in enumerate(entries):
            if item.get("kind") not in {"extracted", "pattern"}:
                continue
            source = _contained(unpacked, item["path"])
            if source.suffix.lower() not in _IMAGE_SUFFIXES | {".svg"}:
                _fail("作品包包含不支持的图像。")
            if item["kind"] == "pattern":
                relative = f"patterns/import-{index}{source.suffix.lower()}"
                project.artifacts.recomposition.append(relative)
            else:
                if source.suffix.lower() == ".svg":
                    _fail("提取结果必须为位图。")
                with Image.open(source) as image:
                    mask = image.mode in {"1", "L"}
                relative = f"{'masks' if mask else 'extracted'}/import-{index}{source.suffix.lower()}"
                project.artifacts.extraction.append(relative)
            target = _contained(project_dir, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if _active_image(project, "result"):
            project.confirmed_steps.append(StepId.EXTRACTION)
        if _active_image(project, "pattern"):
            project.confirmed_steps.append(StepId.RECOMPOSITION)
        design = settings.get("design")
        if isinstance(design, dict) and _active_image(project, "pattern") and _active_image(project, "result"):
            web["design"] = {"settings": DesignSettings.model_validate(design.get("settings", {})).model_dump(mode="json"),
                             "source_artifact": _active_image(project, "result"), "artifact": _active_image(project, "pattern"),
                             "algorithm": design.get("algorithm", "imported")}
        project.processing_parameters["web_workspace"] = web
        return project, "作品包已转换为新项目；原包未保存的分类、分析和历史版本无法恢复。"

    def import_archive(self, source, name=None):
        stage = self.repository.workspace / (".import-" + uuid4().hex)
        stage.mkdir()
        export_stage = None
        export_final = None
        export_published = False
        published = False
        try:
            try:
                with ZipFile(source) as archive:
                    names = _unpack(archive, stage)
                if "manifest.json" not in names:
                    _fail("备份缺少文件清单。")
                project, notice = self._validate_bundle(stage, names)
                folder = stage / "project"
                indexed_artifacts = _references(project)
                snapshots = []
                versions = _contained(folder, f"{SIDECAR}/versions")
                if versions.exists():
                    for path in versions.iterdir():
                        if not path.is_file() or path.suffix != ".json" or not _VERSION_ID.fullmatch(path.stem):
                            _fail("历史版本文件名无效。")
                        snapshot = Snapshot.model_validate(_read_json(path))
                        if snapshot.id != path.stem or snapshot.project.id != project.id:
                            _fail("历史版本项目标识无效。")
                        snapshots.append((path, snapshot))
                        indexed_artifacts.update(_references(snapshot.project))
                _validate_layout(folder, indexed_artifacts=indexed_artifacts)
                _validate_export_layout(stage / "exports")
                _validate_project(project, folder, images=True)
                total_pixels = 0
                for relative, path in _files(stage):
                    if path.suffix.lower() in _IMAGE_SUFFIXES:
                        info = probe_image(path)
                        total_pixels += info.width * info.height
                        if total_pixels > MAX_TOTAL_IMAGE_PIXELS:
                            _fail("备份中的图像总量超出上限。", 413)
            except (BadZipFile, EOFError, RuntimeError, NotImplementedError, ValidationError, RecursionError) as error:
                _fail("备份格式无效或文件已损坏。")

            new_id = self.repository._new_project_id()
            now = datetime.now(UTC)
            old_revision = project.updated_at.isoformat()

            def remap(record):
                record.id = new_id
                web = dict(_web(record))
                web.pop("demo_id", None)  # A clone must open independently of bundled examples.
                for export in self.exports(record):
                    export["url"] = f"/api/projects/{new_id}/exports/{export['id']}"
                record.processing_parameters["web_workspace"] = web
                return record

            project = remap(project)
            project.created_at = now
            project.updated_at = now
            if name is not None:
                if not name.strip() or len(name) > 80:
                    _fail("项目名称需为 1 到 80 个字符。")
                project.name = name.strip()
            project = ProjectRecord.model_validate(_scrub(project.model_dump(mode="json")))
            for path, snapshot in snapshots:
                _validate_project(snapshot.project, folder)
                snapshot.project = remap(snapshot.project)
                _atomic(path, _json(_scrub(snapshot.model_dump(mode="json"))))
            drafts = _contained(folder, f"{SIDECAR}/drafts")
            if drafts.exists():
                for path in drafts.iterdir():
                    if path.name not in {"extract.json", "design.json"}:
                        _fail("草稿文件名无效。")
                    draft = _read_json(path)
                    parsed = DraftSave.model_validate({"base_revision": draft["base_revision"], "data": draft["data"]})
                    draft["data"] = _draft_data(path.stem, parsed.data, parsed.base_revision)
                    if draft["base_revision"] == old_revision:
                        draft["base_revision"] = now.isoformat()
                    _atomic(path, _json(_scrub(draft)))
            for relative, path in _files(folder):
                if path.suffix.lower() in {".json", ".txt", ".md", ".svg", ".csv"} and relative != "project.json":
                    _atomic(path, _metadata_bytes(relative, path))
            _atomic(folder / "project.json", _json(project.model_dump(mode="json")))
            _validate_project(project, folder)
            exports = stage / "exports"
            for record in self.exports(project):
                if not _contained(exports, record["id"] + "/" + record["filename"]).is_file():
                    _fail("备份缺少历史导出文件。")
            if exports.exists():
                self.export_root.mkdir(parents=True, exist_ok=True)
                export_stage = self.export_root / (".import-" + uuid4().hex)
                shutil.copytree(exports, export_stage)
                for relative, path in _files(export_stage):
                    if path.suffix.lower() in {".json", ".txt", ".md", ".svg", ".csv"}:
                        _atomic(path, _metadata_bytes(relative, path))
                export_final = _contained(self.export_root, new_id)
                if export_final.exists():
                    _fail("新项目导出目录冲突，请重试。", 409)
                os.replace(export_stage, export_final)
                export_published = True
            destination = self.repository.project_dir(new_id)
            if destination.exists():
                _fail("新项目目录冲突，请重试。", 409)
            os.replace(folder, destination)
            published = True
            return self.repository.load(new_id), notice
        except (ValidationError, KeyError, TypeError, ValueError) as error:
            _fail("备份项目参数无效。")
        finally:
            _clean(stage, self.repository.workspace)
            if export_stage is not None:
                _clean(export_stage, self.export_root)
            if not published and export_published and export_final is not None and export_final.exists():
                # This directory was created by this invocation for a fresh id.
                rollback = self.export_root / (".import-" + uuid4().hex)
                os.replace(export_final, rollback)
                _clean(rollback, self.export_root)


def register_project_routes(app, repository, lock, current, public, safe_artifact, export_root):
    """Attach routes and return ``auto_snapshot(project, label)`` for save hooks."""
    workspace = _Workspace(repository, export_root)

    def auto_snapshot(project, label):
        return _snapshot_summary(workspace.make_snapshot(project, label, automatic=True))

    @app.get("/api/projects/{project_id}/drafts/{kind}")
    def get_draft(project_id: str, kind: Literal["extract", "design"]):
        with lock:
            project = repository.load(project_id)
            path = workspace.path(project_id, f"{SIDECAR}/drafts/{kind}.json")
            draft = _read_json(path) if path.is_file() else None
            if draft is not None:
                draft["stale"] = draft["base_revision"] != project.updated_at.isoformat()
            return {"draft": draft, "revision": project.updated_at.isoformat()}

    @app.put("/api/projects/{project_id}/drafts/{kind}")
    def put_draft(project_id: str, kind: Literal["extract", "design"], data: DraftSave):
        with lock:
            project = current(project_id, data.base_revision)
            try:
                parsed = _draft_data(kind, data.data, data.base_revision)
            except ValidationError:
                _fail("草稿参数无效。")
            payload = {"kind": kind, "base_revision": data.base_revision, "data": parsed, "saved_at": datetime.now(UTC).isoformat()}
            serialized = _json(payload)
            if len(serialized) > MAX_METADATA_BYTES:
                _fail("草稿过大，请减少笔触后重试。", 413)
            _atomic(workspace.path(project_id, f"{SIDECAR}/drafts/{kind}.json"), serialized)
            return {"draft": {**payload, "stale": False}, "revision": project.updated_at.isoformat()}

    @app.delete("/api/projects/{project_id}/drafts/{kind}", status_code=204)
    def delete_draft(project_id: str, kind: Literal["extract", "design"]):
        with lock:
            repository.load(project_id)
            workspace.path(project_id, f"{SIDECAR}/drafts/{kind}.json").unlink(missing_ok=True)
        return Response(status_code=204)

    @app.get("/api/projects/{project_id}/versions")
    def list_versions(project_id: str):
        with lock:
            repository.load(project_id)
            return {"versions": [_snapshot_summary(value) for value in workspace.snapshots(project_id)]}

    @app.post("/api/projects/{project_id}/versions")
    def create_version(project_id: str, data: VersionCreate):
        with lock:
            project = current(project_id, data.revision)
            snapshot = workspace.make_snapshot(project, data.name)
            return {"version": _snapshot_summary(snapshot), "project": public(project, True)}

    @app.get("/api/projects/{project_id}/versions/{version_id}")
    def get_version(project_id: str, version_id: str):
        with lock:
            repository.load(project_id)
            snapshot = workspace.snapshot(project_id, version_id)
            return {"version": _snapshot_summary(snapshot), "project": snapshot.project.model_dump(mode="json")}

    @app.get("/api/projects/{project_id}/versions/{version_id}/image")
    def version_image(project_id: str, version_id: str, kind: Literal["result", "pattern"] = "pattern"):
        with lock:
            repository.load(project_id)
            snapshot = workspace.snapshot(project_id, version_id)
            relative = _active_image(snapshot.project, kind)
            if not relative:
                _fail("这个版本没有对应的图像。", 404)
            image = load_working_image(safe_artifact(snapshot.project, relative), max_edge=1200)
            stream = BytesIO()
            image.save(stream, format="PNG")
            return Response(stream.getvalue(), media_type="image/png")

    @app.post("/api/projects/{project_id}/versions/{version_id}/restore")
    def restore_version(project_id: str, version_id: str, data: Revision):
        with lock:
            project = current(project_id, data.revision)
            snapshot = workspace.snapshot(project_id, version_id)
            restored = snapshot.project.model_copy(deep=True)
            _validate_project(restored, repository.project_dir(project_id), images=True)
            if ((restored.source.relative_path, restored.source.sha256, restored.source.byte_size)
                    != (project.source.relative_path, project.source.sha256, project.source.byte_size)):
                _fail("历史版本的原始素材与当前项目不一致。")
            restored.source = project.source.model_copy(deep=True)
            before = workspace.make_snapshot(project, "恢复前自动备份", automatic=True)
            web = dict(_web(restored))
            newer_exports = list(workspace.exports(project))
            old_exports = list(workspace.exports(restored))
            web["exports"] = newer_exports + [item for item in old_exports if item["id"] not in {value["id"] for value in newer_exports}]
            restored.processing_parameters["web_workspace"] = web
            active = _references(restored) - set(restored.stale_artifacts)
            restored.stale_artifacts = sorted((_references(project) | set(restored.stale_artifacts)) - active - {project.source.relative_path})
            restored.created_at = project.created_at
            restored.updated_at = datetime.now(UTC)
            repository.save(restored)
            return {"project": public(restored, True), "version": _snapshot_summary(snapshot), "before_restore": _snapshot_summary(before)}

    @app.post("/api/projects/{project_id}/duplicate")
    def duplicate_project(project_id: str, data: Duplicate):
        with lock:
            project = current(project_id, data.revision)
            with workspace.bundle(project) as stream:
                duplicate, _ = workspace.import_archive(stream, data.name or (project.name[:76] + " 副本"))
            return public(duplicate, True)

    @app.get("/api/projects/{project_id}/backup")
    def backup_project(project_id: str):
        with lock:
            stream = workspace.bundle(repository.load(project_id))

        def chunks():
            try:
                while chunk := stream.read(1024 * 1024):
                    yield chunk
            finally:
                stream.close()
        return StreamingResponse(chunks(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{project_id}-backup.zip"'})

    @app.post("/api/projects/import")
    def import_project(file: UploadFile = File(...), name: str | None = Form(default=None, max_length=80)):
        try:
            file.file.seek(0, 2)
            if file.file.tell() > MAX_ARCHIVE_BYTES:
                _fail("备份压缩文件过大。", 413)
            file.file.seek(0)
            with lock:
                project, notice = workspace.import_archive(file.file, name)
                result = public(project, True)
                if notice:
                    result["import_notice"] = notice
                return result
        finally:
            file.file.close()

    @app.get("/api/recovery")
    def recovery_projects():
        with lock:
            values = []
            for path in repository.workspace.iterdir():
                if not ProjectRepository._PROJECT_ID_PATTERN.fullmatch(path.name) or not path.is_dir() or path.is_symlink():
                    continue
                try:
                    repository.load(path.name)
                except (ProjectCorruptError, ProjectNotFoundError):
                    versions = workspace.snapshots(path.name)
                    if versions:
                        values.append({"id": path.name, "name": versions[0].project.name,
                                       "versions": [_snapshot_summary(value) for value in versions]})
                except ProjectRepositoryError:
                    continue
            return {"projects": values}

    @app.post("/api/projects/{project_id}/recover")
    def recover_project(project_id: str, data: Recovery):
        with lock:
            try:
                repository.load(project_id)
            except (ProjectCorruptError, ProjectNotFoundError):
                pass
            else:
                _fail("项目可以正常打开，请使用历史版本恢复。", 409)
            snapshot = workspace.snapshot(project_id, data.version_id)
            project = snapshot.project.model_copy(deep=True)
            folder = repository.project_dir(project_id)
            _validate_project(project, folder, images=True)
            broken = workspace.path(project_id, "project.json")
            if broken.is_file():
                if broken.stat().st_size > MAX_METADATA_BYTES:
                    _fail("损坏的项目元数据过大，请先手工备份。", 413)
                _atomic(workspace.path(project_id, f"{SIDECAR}/recovery/{uuid4().hex}.txt"), _redact_secrets(broken.read_text(encoding="utf-8", errors="replace")).encode("utf-8"))
            project.updated_at = datetime.now(UTC)
            _atomic(broken, _json(project.model_dump(mode="json")))
            return public(repository.load(project_id), True)

    return auto_snapshot
