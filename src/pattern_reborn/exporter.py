# -*- coding: utf-8 -*-
"""Atomic provenance export packages with copied assets and reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from pattern_reborn.domain import GenerationRecord, ProjectRecord, ProvenanceClass


class ExportError(ValueError):
    """导出包无法安全写入。"""


_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_MOCKUP_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_SECRET_SHAPED = re.compile(
    r"(?i)(?:api[_-]?key|\bauthorization\b|\bbearer\b|\bbasic\s+\S+|sk-[A-Za-z0-9._-]+)"
)
_PROVENANCE_ZH = {
    ProvenanceClass.VERIFIED_ICH_SOURCE: "已核验的传统来源",
    ProvenanceClass.TRADITIONAL_REFERENCE: "传统参考",
    ProvenanceClass.USER_SUPPLIED_UNVERIFIED: "用户提供（未核验）",
}


class ExportSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    source: bool = False
    extracted: bool = False
    patterns: bool = False
    generations: bool = False
    mockups: bool = False
    svg: bool = False
    report: bool = False

    @classmethod
    def all_offline(cls) -> "ExportSelection":
        return cls(
            source=True,
            extracted=True,
            patterns=True,
            generations=True,
            mockups=True,
            svg=True,
            report=True,
        )


@dataclass(frozen=True, slots=True)
class _CopiedFile:
    path: str
    kind: str
    sha256: str
    ai_assisted: bool


class Exporter:
    def __init__(self, project_root: Path) -> None:
        self._project_root = Path(project_root).resolve()

    def export(
        self,
        project: ProjectRecord,
        selection: ExportSelection,
        destination_root: Path,
    ) -> Path:
        destination = Path(destination_root)
        try:
            destination.mkdir(parents=True, exist_ok=True)
            destination = destination.resolve()
        except OSError as error:
            raise ExportError("导出目录无法创建或访问。") from error

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        package_name = f"{stamp}_{_sanitize_filename(project.name)}"
        final_dir = _contained_path(destination / package_name, destination)
        temporary = _contained_path(destination / f".{package_name}.{uuid4().hex}.tmp", destination)
        try:
            temporary.mkdir(parents=False)
            copied = self._write_selected_assets(project, selection, temporary)
            _write_manifest(project, copied, temporary)
            _write_attribution(project, temporary)
            if selection.report:
                _write_provenance(project, copied, temporary)
            os.replace(temporary, final_dir)
        except ExportError:
            _discard_tree(temporary)
            raise
        except OSError as error:
            _discard_tree(temporary)
            raise ExportError("导出包写入失败，原目录未被替换。") from error
        return final_dir

    def _write_selected_assets(
        self,
        project: ProjectRecord,
        selection: ExportSelection,
        package: Path,
    ) -> list[_CopiedFile]:
        copied: list[_CopiedFile] = []
        if selection.source:
            copied.append(
                self._copy_asset(
                    project.source.relative_path,
                    package / "source" / _sanitize_filename(project.source.original_filename, "source.bin"),
                    "source",
                    ai_assisted=False,
                    package=package,
                )
            )
        if selection.extracted:
            used: set[str] = set()
            for index, relative in enumerate(project.artifacts.extraction, start=1):
                copied.append(
                    self._copy_asset(
                        relative,
                        package / "extracted" / _unique_name(relative, f"extracted-{index}", used),
                        "extracted",
                        ai_assisted=False,
                        package=package,
                    )
                )
        if selection.patterns:
            used = set()
            for index, relative in enumerate(project.artifacts.recomposition, start=1):
                copied.append(
                    self._copy_asset(
                        relative,
                        package / "patterns" / _unique_name(relative, f"pattern-{index}", used),
                        "pattern",
                        ai_assisted=False,
                        package=package,
                    )
                )
        if selection.generations:
            used = set()
            for index, generation in enumerate(_current_generations(project), start=1):
                copied.append(
                    self._copy_asset(
                        generation.artifact_path,
                        package / "generated" / _unique_name(generation.artifact_path, f"generated-{index}", used),
                        "generation",
                        ai_assisted=True,
                        package=package,
                    )
                )
        if selection.mockups:
            copied.extend(self._copy_mockup_assets(project, package))
        if selection.svg:
            used = set()
            for index, relative in enumerate(project.artifacts.recomposition, start=1):
                if Path(relative).suffix.lower() != ".svg":
                    continue
                copied.append(
                    self._copy_asset(
                        relative,
                        package / "svg" / _unique_name(relative, f"pattern-{index}", used),
                        "svg",
                        ai_assisted=False,
                        package=package,
                    )
                )
        return copied

    def _copy_mockup_assets(self, project: ProjectRecord, package: Path) -> list[_CopiedFile]:
        _ = project
        mockups_root = (self._project_root / "mockups").resolve()
        if not mockups_root.is_dir() or not mockups_root.is_relative_to(self._project_root):
            return []
        copied: list[_CopiedFile] = []
        used: set[str] = set()
        candidates = sorted(
            path
            for path in mockups_root.rglob("*")
            if path.is_file() and path.suffix.lower() in _MOCKUP_IMAGE_SUFFIXES
        )
        for index, source in enumerate(candidates, start=1):
            try:
                resolved = source.resolve()
            except OSError:
                continue
            if not resolved.is_file():
                continue
            if not resolved.is_relative_to(mockups_root):
                continue
            dest_name = _unique_name(resolved.name, f"mockup-{index}", used)
            relative_source = resolved.relative_to(self._project_root).as_posix()
            copied.append(
                self._copy_asset(
                    relative_source,
                    package / "mockups" / dest_name,
                    "mockup",
                    ai_assisted=_mockup_ai_assisted(resolved),
                    package=package,
                )
            )
        return copied

    def _copy_asset(
        self,
        source_ref: str,
        destination: Path,
        kind: str,
        *,
        ai_assisted: bool,
        package: Path,
    ) -> _CopiedFile:
        source = self._resolve_input(source_ref)
        target = _contained_path(destination, package)
        try:
            data = source.read_bytes()
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
            temporary.write_bytes(data)
            os.replace(temporary, target)
        except OSError as error:
            raise ExportError("导出文件复制失败。") from error
        relative = target.relative_to(package).as_posix()
        return _CopiedFile(
            path=relative,
            kind=kind,
            sha256=hashlib.sha256(data).hexdigest(),
            ai_assisted=ai_assisted,
        )

    def _resolve_input(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if not relative_path or candidate.is_absolute():
            raise ExportError("导出源路径超出项目目录。")
        try:
            resolved = (self._project_root / candidate).resolve()
        except OSError as error:
            raise ExportError("导出源文件不存在或无法读取。") from error
        if not resolved.is_relative_to(self._project_root):
            raise ExportError("导出源路径超出项目目录。")
        if not resolved.is_file():
            raise ExportError("导出源文件不存在或无法读取。")
        return resolved


def _write_manifest(project: ProjectRecord, copied: list[_CopiedFile], package: Path) -> None:
    payload = {
        "schema_version": 1,
        "project_id": project.id,
        "project_name": project.name,
        "exported_at": _iso(datetime.now(UTC)),
        "source": {
            "original_filename": project.source.original_filename,
            "sha256": project.source.sha256,
            "byte_size": project.source.byte_size,
            "provenance": project.provenance.value,
        },
        "files": [
            {
                "path": item.path,
                "kind": item.kind,
                "sha256": item.sha256,
                "ai_assisted": item.ai_assisted,
            }
            for item in copied
        ],
        "generations": [_generation_entry(item) for item in _current_generations(project)],
    }
    _write_utf8(
        package / "manifest.json",
        json.dumps(_redact_payload(payload), ensure_ascii=False, indent=2) + "\n",
    )


def _write_attribution(project: ProjectRecord, package: Path) -> None:
    lines = [
        "# 署名",
        "",
        "## 项目原创",
        "",
        "- 文化产品贴图模板由 Pattern Reborn team 绘制，许可为 project-original。",
        "",
        "## 源材料",
        "",
        f"- 原始文件名：{_redact_secrets(project.source.original_filename)}",
        f"- SHA-256：{_redact_secrets(project.source.sha256)}",
        f"- 来源分类：{_redact_secrets(_PROVENANCE_ZH[project.provenance])}（{_redact_secrets(project.provenance.value)}）",
        "",
    ]
    _write_utf8(package / "attribution.md", "\n".join(lines))


def _write_provenance(project: ProjectRecord, copied: list[_CopiedFile], package: Path) -> None:
    lines = [
        "# 出处报告",
        "",
        f"- 项目：{_redact_secrets(project.name)}",
        f"- 项目标识：{_redact_secrets(project.id)}",
        f"- 源文件 SHA-256：{_redact_secrets(project.source.sha256)}",
        f"- 原始文件名：{_redact_secrets(project.source.original_filename)}",
        f"- 来源分类：{_redact_secrets(_PROVENANCE_ZH[project.provenance])}（{_redact_secrets(project.provenance.value)}）",
        "",
    ]
    current_generations = _current_generations(project)
    has_ai = bool(current_generations) or any(item.ai_assisted for item in copied)
    if has_ai:
        lines.extend(
            [
                "## AI 辅助",
                "",
                "本导出包含生成式模型产出的衍生结果，下列记录已标注为 AI 辅助。",
                "",
            ]
        )
        for item in current_generations:
            lines.extend(
                [
                    f"- 标识：{_redact_secrets(item.id)}",
                    f"- 提供方：{_redact_secrets(item.provider)}",
                    f"- 模型：{_redact_secrets(item.model)}",
                    f"- 提示词：{_redact_secrets(item.prompt)}",
                    f"- 时间：{_redact_secrets(_iso(item.created_at))}",
                    "",
                ]
            )
    _write_utf8(package / "provenance.md", "\n".join(lines))


def _current_generations(project: ProjectRecord) -> list[GenerationRecord]:
    stale = set(project.stale_artifacts)
    return [item for item in project.generations if item.artifact_path not in stale]


def _mockup_ai_assisted(image_path: Path) -> bool:
    sidecar = image_path.with_suffix(".json")
    try:
        if not sidecar.is_file() or not sidecar.resolve().is_relative_to(image_path.parent.resolve()):
            return False
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("ai_assisted") is True


def _generation_entry(item: GenerationRecord) -> dict[str, object]:
    return {
        "id": _redact_secrets(item.id),
        "provider": _redact_secrets(item.provider),
        "model": _redact_secrets(item.model),
        "prompt": _redact_secrets(item.prompt),
        "created_at": _redact_secrets(_iso(item.created_at)),
        "ai_assisted": True,
    }


def _redact_secrets(text: str) -> str:
    if _SECRET_SHAPED.search(text):
        return "[REDACTED]"
    return text


def _redact_payload(value: object) -> object:
    if isinstance(value, str):
        return _redact_secrets(value)
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_payload(item) for key, item in value.items()}
    return value


def _is_windows_reserved_basename(name: str) -> bool:
    stem = Path(name).stem.upper()
    return stem in _WINDOWS_RESERVED_BASENAMES


def _sanitize_filename(name: str, fallback: str = "export") -> str:
    collapsed = name.replace("..", "")
    cleaned = _UNSAFE_FILENAME.sub("_", collapsed).strip(" .")
    cleaned = _redact_secrets(cleaned)
    if not cleaned or cleaned in {".", ".."}:
        return fallback
    if _is_windows_reserved_basename(cleaned):
        stem = Path(cleaned).stem
        suffix = Path(cleaned).suffix
        cleaned = f"_{stem}{suffix}"
    return cleaned[:80]


def _unique_name(source_ref: str, fallback: str, used: set[str]) -> str:
    original = Path(source_ref).name
    stem = Path(original).stem
    suffix = Path(original).suffix.lower()
    complete = _redact_secrets(f"{stem}{suffix}" if suffix else stem)
    stem = _sanitize_filename(Path(complete).stem, fallback)
    suffix = Path(complete).suffix.lower()
    if suffix and _UNSAFE_FILENAME.search(suffix):
        suffix = ""
    candidate = f"{stem}{suffix}" if suffix else stem
    taken = {name.lower() for name in used}
    if candidate.lower() not in taken:
        used.add(candidate)
        return candidate
    index = 2
    while True:
        name = f"{stem}-{index}{suffix}" if suffix else f"{stem}-{index}"
        if name.lower() not in taken:
            used.add(name)
            return name
        index += 1


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _write_utf8(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _contained_path(path: Path, root: Path) -> Path:
    try:
        resolved = path if path.is_absolute() else (root / path)
        resolved = resolved.resolve()
        container = root.resolve()
    except OSError as error:
        raise ExportError("导出路径无法解析。") from error
    if not resolved.is_relative_to(container):
        raise ExportError("导出路径超出允许的目标目录。")
    return resolved


def _discard_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
