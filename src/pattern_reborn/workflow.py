# -*- coding: utf-8 -*-
"""Framework-independent six-step application service for local pattern projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from pattern_reborn.analysis import (
    AnalysisError,
    ColorMatch,
    ContourReport,
    PaletteColor,
    SymmetryReport,
    analyze_contours,
    analyze_palette,
    analyze_symmetry,
    match_traditional_colors,
)
from pattern_reborn.domain import (
    ArtifactKind,
    CategoryId,
    GenerationRecord,
    ProfileId,
    ProjectRecord,
    ProvenanceClass,
    StepId,
)
from pattern_reborn.exporter import Exporter, ExportSelection
from pattern_reborn.generation.base import CredentialMode, GenerationRequest
from pattern_reborn.generation.service import GenerationResult, GenerationService
from pattern_reborn.images import load_working_image, save_png_atomic
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.mockups import ArtworkRef, compose_mockup, load_mockup_catalog, save_composed_mockup
from pattern_reborn.patterns import PatternRequest, compose_pattern
from pattern_reborn.projects import ProjectRepository
from pattern_reborn.segmentation import (
    MaskStroke,
    OpenCvSegmenter,
    SegmentHints,
    apply_mask_strokes,
    extract_rgba,
)
from pattern_reborn.vectorize import Vectorizer

_PALETTE_SEED = 20260829


class WorkflowError(ValueError):
    """工作流步骤无法安全完成。"""


class CreateProjectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str
    source: Path
    category: CategoryId
    provenance: ProvenanceClass
    subject: str | None = None


class ExtractCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True, validate_assignment=True)

    profile: ProfileId
    hints: SegmentHints | None = None
    strokes: list[MaskStroke] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    kind: ArtifactKind
    path: Path


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    palette: list[PaletteColor]
    color_matches: list[ColorMatch]
    contours: ContourReport
    symmetry: SymmetryReport


class PatternRebornService:
    def __init__(
        self,
        repository: ProjectRepository,
        *,
        knowledge: KnowledgeCatalog,
        generation: GenerationService | None = None,
        export_root: Path,
        mockup_catalog: dict | None = None,
        vectorizer: Vectorizer | None = None,
        segmenter: OpenCvSegmenter | None = None,
    ) -> None:
        self.repository = repository
        self._knowledge = knowledge
        self._generation = generation
        self._export_root = Path(export_root)
        self._mockups = mockup_catalog if mockup_catalog is not None else load_mockup_catalog()
        self._vectorizer = vectorizer if vectorizer is not None else Vectorizer()
        self._segmenter = segmenter if segmenter is not None else OpenCvSegmenter()

    def create_project(self, command: CreateProjectCommand) -> ProjectRecord:
        project = self.repository.create(
            command.name,
            command.source,
            command.category,
            command.provenance,
        )
        if command.subject is not None:
            project.subject = command.subject
            project.updated_at = datetime.now(UTC)
            self.repository.save(project)
        project = self.repository.confirm(
            project.id, StepId.UPLOAD, [project.source.relative_path]
        )
        return self.save_navigation_state(project.id, StepId.UPLOAD)

    def load_project(self, project_id: str) -> ProjectRecord:
        return self.repository.load(project_id)

    def save_navigation_state(
        self,
        project_id: str,
        step: StepId,
        draft: dict[str, object] | None = None,
    ) -> ProjectRecord:
        project = self.repository.load(project_id)
        parameters = dict(project.processing_parameters)
        parameters["current_step"] = step.value
        if draft is not None:
            parameters["draft"] = draft
        project.processing_parameters = parameters
        project.updated_at = datetime.now(UTC)
        self.repository.save(project)
        return self.repository.load(project_id)

    def extract(self, project_id: str, command: ExtractCommand) -> ArtifactRef:
        project = self.repository.load(project_id)
        self._require_step(project, StepId.UPLOAD, "请先创建项目并完成上传。")
        project_dir = self.repository.project_dir(project.id)
        source_path = self._resolve_artifact(project_dir, project.source.relative_path)
        working = load_working_image(source_path)
        rgb = np.ascontiguousarray(np.asarray(working.convert("RGB")), dtype=np.uint8)
        hints = command.hints if command.hints is not None else SegmentHints()
        result = self._segmenter.segment(rgb, command.profile, hints)
        mask = result.mask
        if command.strokes:
            mask = apply_mask_strokes(mask, command.strokes)
        rgba = extract_rgba(rgb, mask)
        version = _next_version(project_dir / "extracted")
        extracted_id = f"extracted/v{version}.png"
        mask_id = f"masks/v{version}.png"
        extracted_path = self._resolve_artifact(project_dir, extracted_id)
        mask_path = self._resolve_artifact(project_dir, mask_id)
        save_png_atomic(rgba, extracted_path)
        save_png_atomic(Image.fromarray(mask).convert("L"), mask_path)
        parameters = dict(project.processing_parameters)
        parameters["current_step"] = StepId.EXTRACTION.value
        parameters["profile"] = command.profile.value
        parameters["pending_extraction"] = {
            "artifact_id": extracted_id,
            "mask": mask_id,
            "algorithm_version": result.algorithm_version,
            "parameters": result.parameters,
            "hints": result.hints.record(),
            "warnings": list(result.warnings),
        }
        project.processing_parameters = parameters
        project.profile = command.profile
        project.updated_at = datetime.now(UTC)
        self.repository.save(project)
        return ArtifactRef(artifact_id=extracted_id, kind=ArtifactKind.EXTRACTED, path=extracted_path)

    def confirm_extraction(self, project_id: str, artifact_id: str) -> ProjectRecord:
        project = self.repository.load(project_id)
        pending = project.processing_parameters.get("pending_extraction")
        if not isinstance(pending, dict) or pending.get("artifact_id") != artifact_id:
            raise WorkflowError("请先完成提取后再确认结果。")
        project_dir = self.repository.project_dir(project.id)
        extracted_path = self._resolve_artifact(project_dir, artifact_id)
        if not extracted_path.is_file():
            raise WorkflowError("提取结果不存在，无法确认。")
        paths = [artifact_id]
        mask_id = pending.get("mask")
        if isinstance(mask_id, str):
            mask_path = self._resolve_artifact(project_dir, mask_id)
            if mask_path.is_file():
                paths.append(mask_id)
        self.repository.confirm(project.id, StepId.EXTRACTION, paths)
        return self.save_navigation_state(project.id, StepId.EXTRACTION)

    def analyze(self, project_id: str) -> AnalysisReport:
        project = self.repository.load(project_id)
        self._require_step(project, StepId.EXTRACTION, "请先确认提取结果后再进行分析。")
        project_dir = self.repository.project_dir(project.id)
        extracted_id, mask_id = self._confirmed_extraction_paths(project)
        extracted_path = self._resolve_artifact(project_dir, extracted_id)
        with Image.open(extracted_path) as image:
            rgba = image.convert("RGBA").copy()
        mask = (
            _load_mask(self._resolve_artifact(project_dir, mask_id))
            if mask_id is not None
            else _mask_from_alpha(rgba)
        )
        profile = self._resolve_profile(project)
        count = _palette_count(rgba, profile.parameters.palette_size)
        try:
            palette = analyze_palette(rgba, count, _PALETTE_SEED)
            color_matches = match_traditional_colors(palette, self._knowledge.colors)
            contours = analyze_contours(mask)
            symmetry = analyze_symmetry(mask)
        except AnalysisError as error:
            raise WorkflowError(str(error)) from error
        report = AnalysisReport(
            palette=palette,
            color_matches=color_matches,
            contours=contours,
            symmetry=symmetry,
        )
        version = _next_version(project_dir / "analysis", suffix=".json")
        analysis_id = f"analysis/v{version}.json"
        analysis_path = self._resolve_artifact(project_dir, analysis_id)
        _write_json_atomic(analysis_path, _analysis_payload(report, profile.id))
        parameters = dict(project.processing_parameters)
        parameters["current_step"] = StepId.ANALYSIS.value
        parameters["analysis"] = {
            "artifact_id": analysis_id,
            "palette_size": count,
            "seed": _PALETTE_SEED,
            "algorithm": "opencv-baseline-1.0",
        }
        project.processing_parameters = parameters
        project.updated_at = datetime.now(UTC)
        self.repository.save(project)
        self.repository.confirm(project.id, StepId.ANALYSIS, [analysis_id])
        return report

    def compose(self, project_id: str, request: PatternRequest) -> ArtifactRef:
        project = self.repository.load(project_id)
        self._require_step(project, StepId.ANALYSIS, "请先完成分析后再重组纹样。")
        project_dir = self.repository.project_dir(project.id)
        extracted_id, _mask_id = self._confirmed_extraction_paths(project)
        extracted_path = self._resolve_artifact(project_dir, extracted_id)
        with Image.open(extracted_path) as image:
            motif = image.convert("RGBA").copy()
        composed = compose_pattern(motif, request)
        version = _next_version(project_dir / "patterns")
        pattern_id = f"patterns/v{version}.png"
        pattern_path = self._resolve_artifact(project_dir, pattern_id)
        save_png_atomic(composed, pattern_path)
        artifact_ids = [pattern_id]
        svg_id = f"patterns/v{version}.svg"
        vector = self._vectorizer.vectorize(pattern_path, self._resolve_artifact(project_dir, svg_id))
        if vector.available and vector.destination is not None:
            artifact_ids.append(svg_id)
        parameters = dict(project.processing_parameters)
        parameters["current_step"] = StepId.RECOMPOSITION.value
        parameters["compose"] = request.model_dump(mode="json")
        project.processing_parameters = parameters
        project.updated_at = datetime.now(UTC)
        self.repository.save(project)
        self.repository.confirm(project.id, StepId.RECOMPOSITION, artifact_ids)
        return ArtifactRef(artifact_id=pattern_id, kind=ArtifactKind.PATTERN, path=pattern_path)

    def generate(
        self,
        project_id: str,
        request: GenerationRequest,
        mode: CredentialMode,
        byok: SecretStr | None,
    ) -> GenerationResult:
        if self._generation is None:
            raise WorkflowError("生成服务未配置。")
        project = self.repository.load(project_id)
        self._require_step(project, StepId.EXTRACTION, "请先确认提取结果后再生成。")
        project_dir = self.repository.project_dir(project.id)
        parameters = dict(project.processing_parameters)
        parameters["current_step"] = StepId.GENERATION.value
        parameters["generation"] = {
            "prompt": request.prompt,
            "provider": request.provider.value,
            "model": request.model,
            "size": request.size,
            "count": request.count,
            "structure_level": request.structure_level.value,
            "target_application": request.target_application.value,
            "mode": mode.value,
        }
        project.processing_parameters = parameters
        project.updated_at = datetime.now(UTC)
        self.repository.save(project)
        dispatched = request.model_copy(
            update={"reference_path": self._resolve_reference(project_dir, request.reference_path)}
        )
        result = self._generation.generate(dispatched, mode, byok)
        stored_files: list[Path] = []
        stored_ids: list[str] = []
        project = self.repository.load(project_id)
        for source in result.local_files:
            version = _next_version(project_dir / "generated")
            artifact_id = f"generated/v{version}.png"
            destination = self._resolve_artifact(project_dir, artifact_id)
            with Image.open(source) as image:
                save_png_atomic(image.copy(), destination)
            stored_files.append(destination)
            stored_ids.append(artifact_id)
            project.generations.append(
                GenerationRecord(
                    id=f"gen-{uuid4().hex[:12]}",
                    provider=result.provider.value,
                    model=result.model,
                    prompt=result.prompt,
                    artifact_path=artifact_id,
                    created_at=datetime.now(UTC),
                )
            )
        project.updated_at = datetime.now(UTC)
        self.repository.save(project)
        self.repository.confirm(project.id, StepId.GENERATION, stored_ids)
        return result.model_copy(update={"local_files": stored_files})

    def make_mockup(self, project_id: str, template_id: str, artwork_id: str) -> ArtifactRef:
        project = self.repository.load(project_id)
        project_dir = self.repository.project_dir(project.id)
        artwork_path = self._resolve_artifact(project_dir, artwork_id)
        if not artwork_path.is_file():
            raise WorkflowError("贴图纹样不存在。")
        template = self._mockups.get(template_id)
        if template is None:
            raise WorkflowError("贴图模板不存在。")
        ai_assisted = artwork_id.startswith("generated/") or any(
            record.artifact_path == artwork_id for record in project.generations
        )
        composed = compose_mockup(template, ArtworkRef(path=artwork_path, ai_assisted=ai_assisted))
        version = _next_prefixed_version(project_dir / "mockups", template_id)
        mockup_id = f"mockups/{template_id}-v{version}.png"
        mockup_path = self._resolve_artifact(project_dir, mockup_id)
        save_composed_mockup(composed, mockup_path)
        parameters = dict(project.processing_parameters)
        parameters["current_step"] = StepId.EXPORT.value
        parameters["mockup"] = {"template_id": template_id, "artwork_id": artwork_id, "artifact_id": mockup_id}
        project.processing_parameters = parameters
        project.updated_at = datetime.now(UTC)
        self.repository.save(project)
        return ArtifactRef(artifact_id=mockup_id, kind=ArtifactKind.MOCKUP, path=mockup_path)

    def export(self, project_id: str, selection: ExportSelection) -> Path:
        project = self.repository.load(project_id)
        project_dir = self.repository.project_dir(project.id)
        try:
            self._export_root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise WorkflowError("导出目录无法创建或访问。") from error
        package = Exporter(project_dir).export(project, selection, self._export_root)
        self.repository.confirm(project.id, StepId.EXPORT, [])
        self.save_navigation_state(project.id, StepId.EXPORT)
        return package

    def _require_step(self, project: ProjectRecord, step: StepId, message: str) -> None:
        if step not in project.confirmed_steps:
            raise WorkflowError(message)

    def _resolve_profile(self, project: ProjectRecord):
        if project.profile is not None:
            for profile in self._knowledge.profiles:
                if profile.id is project.profile:
                    return profile
        return self._knowledge.profile_for(project.category)

    def _confirmed_extraction_paths(self, project: ProjectRecord) -> tuple[str, str | None]:
        extracted = [
            path
            for path in project.artifacts.extraction
            if path.startswith("extracted/") and path.lower().endswith(".png")
        ]
        masks = [path for path in project.artifacts.extraction if path.startswith("masks/")]
        if not extracted:
            raise WorkflowError("确认的提取结果不存在。")
        return extracted[0], masks[0] if masks else None

    def _resolve_reference(self, project_dir: Path, reference: Path) -> Path:
        if not reference.is_absolute():
            return self._resolve_artifact(project_dir, reference.as_posix())
        try:
            resolved = reference.resolve()
            root = project_dir.resolve()
        except OSError as error:
            raise WorkflowError("项目路径无法解析。") from error
        if not resolved.is_relative_to(root):
            raise WorkflowError("项目路径超出允许的工作区。")
        return resolved

    def _resolve_artifact(self, project_dir: Path, artifact_id: str) -> Path:
        if not artifact_id or Path(artifact_id).is_absolute() or ".." in Path(artifact_id).parts:
            raise WorkflowError("项目路径超出允许的工作区。")
        try:
            resolved = (project_dir / artifact_id).resolve()
            root = project_dir.resolve()
        except OSError as error:
            raise WorkflowError("项目路径无法解析。") from error
        if not resolved.is_relative_to(root):
            raise WorkflowError("项目路径超出允许的工作区。")
        return resolved


def _next_version(folder: Path, suffix: str = ".png") -> int:
    folder.mkdir(parents=True, exist_ok=True)
    highest = 0
    for path in folder.iterdir():
        if path.suffix.lower() != suffix.lower():
            continue
        stem = path.stem
        if stem.startswith("v") and stem[1:].isdigit():
            highest = max(highest, int(stem[1:]))
    return highest + 1


def _next_prefixed_version(folder: Path, prefix: str) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    marker = f"{prefix}-v"
    highest = 0
    for path in folder.iterdir():
        stem = path.stem
        if stem.startswith(marker) and stem[len(marker) :].isdigit():
            highest = max(highest, int(stem[len(marker) :]))
    return highest + 1


def _load_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        loaded = np.asarray(image.convert("L"))
    return np.where(loaded > 0, 255, 0).astype(np.uint8)


def _mask_from_alpha(image: Image.Image) -> np.ndarray:
    pixels = np.asarray(image.convert("RGBA"))
    return np.where(pixels[..., 3] > 0, 255, 0).astype(np.uint8)


def _palette_count(image: Image.Image, requested: int) -> int:
    pixels = np.asarray(image.convert("RGBA"))
    opaque = pixels[pixels[..., 3] != 0, :3]
    if len(opaque) == 0:
        raise WorkflowError("提取结果不包含可分析的不透明像素。")
    unique = int(np.unique(opaque, axis=0).shape[0])
    return max(1, min(requested, unique))


def _analysis_payload(report: AnalysisReport, profile: ProfileId) -> dict[str, object]:
    return {
        "profile": profile.value,
        "algorithm": "opencv-baseline-1.0",
        "palette": [
            {
                "rgb": list(color.rgb),
                "pixel_count": color.pixel_count,
                "coverage": color.coverage,
                "hex_value": color.hex_value,
            }
            for color in report.palette
        ],
        "color_matches": [
            {
                "hex_value": match.palette_color.hex_value,
                "traditional_slug": match.traditional_color.slug,
                "traditional_name_zh": match.traditional_color.name_zh,
                "distance": match.distance,
            }
            for match in report.color_matches
        ],
        "contours": asdict(report.contours),
        "symmetry": {
            "vertical_score": report.symmetry.vertical_score,
            "horizontal_score": report.symmetry.horizontal_score,
            "rotations": [asdict(candidate) for candidate in report.symmetry.rotations],
        },
    }


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise WorkflowError("分析结果保存失败。") from error
