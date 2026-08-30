# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from pydantic import ValidationError
import pytest

import pattern_reborn.workflow as workflow
from pattern_reborn.domain import CategoryId, ProfileId, ProvenanceClass, StepId
from pattern_reborn.exporter import ExportSelection
from pattern_reborn.generation.base import (
    CredentialMode,
    GenerationFailure,
    ProviderId,
    StructureLevel,
    TargetApplication,
)
from pattern_reborn.patterns import LayoutKind, PatternRequest
from pattern_reborn.preprocess import PreprocessSettings, enhance
from pattern_reborn.segmentation import (
    MaskEditMode,
    MaskStroke,
    SegmentResult,
    extract_rgba,
)
from pattern_reborn.workflow import (
    CreateProjectCommand,
    ExtractCommand,
    PatternRebornService,
    WorkflowError,
)
from tests.test_generation_base import make_generation_request


def _create(app_service, source: Path, name: str = "工作流项目"):
    return app_service.create_project(
        CreateProjectCommand(
            name=name,
            source=source,
            category=CategoryId.PAPER_CUTTING,
            provenance=ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
        )
    )


def _extract_and_confirm(app_service, project_id: str):
    extraction = app_service.extract(project_id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    return app_service.confirm_extraction(project_id, extraction.artifact_id), extraction


class RecordingSegmenter:
    def __init__(self, algorithm_version: str) -> None:
        self.algorithm_version = algorithm_version
        self.calls = 0
        self.last_image: np.ndarray | None = None

    def segment(self, image, profile, hints) -> SegmentResult:
        self.calls += 1
        self.last_image = image.copy()
        mask = np.full(image.shape[:2], 255, dtype=np.uint8)
        return SegmentResult(
            mask=mask,
            rgba=extract_rgba(image, mask),
            profile=profile,
            parameters={"recording_segmenter": self.algorithm_version},
            hints=hints,
            algorithm_version=self.algorithm_version,
        )


class UnavailableMobileSamSegmenter:
    def validate_available(self) -> None:
        raise RuntimeError("checkpoint is unavailable")

    def segment(self, image, profile, hints) -> SegmentResult:
        raise AssertionError("unavailable MobileSAM must not segment")


def test_workflow_module_does_not_import_streamlit() -> None:
    import pattern_reborn.workflow as workflow

    source = Path(workflow.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert "streamlit" not in imported
    assert "streamlit" not in source


def test_create_project_does_not_mutate_source_bytes(app_service, source_fixture: Path) -> None:
    original = source_fixture.read_bytes()
    project = _create(app_service, source_fixture)
    assert source_fixture.read_bytes() == original
    assert StepId.UPLOAD in project.confirmed_steps
    copied = app_service.repository.project_dir(project.id) / project.source.relative_path
    assert copied.read_bytes() == original


def test_navigation_state_persists_on_project_record(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture, name="导航测试")
    saved = app_service.save_navigation_state(
        project.id,
        StepId.ANALYSIS,
        {"unsaved_note": "待确认"},
    )
    reloaded = app_service.load_project(project.id)
    assert saved.processing_parameters["current_step"] == StepId.ANALYSIS.value
    assert reloaded.processing_parameters["current_step"] == StepId.ANALYSIS.value
    assert reloaded.processing_parameters["draft"]["unsaved_note"] == "待确认"


def test_extract_applies_preprocess_before_segmenting(
    app_service,
    source_fixture: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create(app_service, source_fixture)
    settings = PreprocessSettings(
        white_balance_strength=0.75,
        denoise_strength=0,
        clahe_clip_limit=2.0,
        clahe_tile_grid_size=(4, 4),
    )
    with Image.open(source_fixture) as image:
        original = np.asarray(image.convert("RGB"), dtype=np.uint8)
    expected = enhance(original, settings)
    received: list[np.ndarray] = []
    segmenter = app_service._segmenter
    real_segment = segmenter.segment

    def record_segment_input(image, profile, hints):
        received.append(image.copy())
        return real_segment(image, profile, hints)

    monkeypatch.setattr(segmenter, "segment", record_segment_input)

    app_service.extract(
        project.id,
        ExtractCommand(profile=ProfileId.FLAT_COLOR, preprocess=settings),
    )

    assert len(received) == 1
    assert np.array_equal(received[0], expected)
    assert not np.array_equal(received[0], original)


def test_extract_persists_preprocess_settings(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture)
    settings = PreprocessSettings(
        white_balance_strength=0.75,
        denoise_strength=0,
        clahe_clip_limit=2.0,
        clahe_tile_grid_size=(4, 4),
    )

    app_service.extract(
        project.id,
        ExtractCommand(profile=ProfileId.FLAT_COLOR, preprocess=settings),
    )

    pending = app_service.load_project(project.id).processing_parameters["pending_extraction"]
    assert pending["parameters"]["preprocess"] == {
        "white_balance_strength": 0.75,
        "denoise_strength": 0,
        "clahe_clip_limit": 2.0,
        "clahe_tile_grid_size": [4, 4],
    }


def test_extract_routes_to_requested_mobile_sam_and_persists_backend(
    app_service,
    source_fixture: Path,
    tmp_path: Path,
) -> None:
    opencv = RecordingSegmenter("opencv-recording-1.0")
    mobile = RecordingSegmenter("mobile-sam-recording-1.0")
    service = PatternRebornService(
        app_service.repository,
        knowledge=app_service._knowledge,
        export_root=tmp_path / "outputs",
        segmenter=opencv,
        mobile_sam_segmenter=mobile,
    )
    project = _create(service, source_fixture)

    service.extract(
        project.id,
        ExtractCommand(
            profile=ProfileId.FLAT_COLOR,
            backend="mobile_sam",
        ),
    )

    assert mobile.calls == 1
    assert opencv.calls == 0
    pending = service.load_project(project.id).processing_parameters["pending_extraction"]
    assert pending["backend"] == "mobile_sam"
    assert pending["algorithm_version"] == "mobile-sam-recording-1.0"


def test_extract_rejects_unavailable_mobile_sam_without_importing_optional_model(
    app_service,
    source_fixture: Path,
) -> None:
    project = _create(app_service, source_fixture)
    before = set(sys.modules)

    with pytest.raises(WorkflowError, match="^MobileSAM 当前不可用，请改用 OpenCV。$"):
        app_service.extract(
            project.id,
            ExtractCommand(profile=ProfileId.FLAT_COLOR, backend="mobile_sam"),
        )

    imported = set(sys.modules) - before
    assert imported.isdisjoint({"torch", "mobile_sam"})


def test_extract_validates_mobile_sam_before_source_decode_or_preprocess(
    app_service,
    source_fixture: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PatternRebornService(
        app_service.repository,
        knowledge=app_service._knowledge,
        export_root=tmp_path / "outputs",
        mobile_sam_segmenter=UnavailableMobileSamSegmenter(),
    )
    project = _create(service, source_fixture)

    def source_decode_must_not_run(*args, **kwargs):
        raise AssertionError("source decode was reached")

    def preprocess_must_not_run(*args, **kwargs):
        raise AssertionError("preprocess was reached")

    monkeypatch.setattr(workflow, "load_working_image", source_decode_must_not_run)
    monkeypatch.setattr(workflow, "enhance", preprocess_must_not_run)

    with pytest.raises(WorkflowError, match="^MobileSAM 当前不可用，请改用 OpenCV。$"):
        service.extract(
            project.id,
            ExtractCommand(profile=ProfileId.FLAT_COLOR, backend="mobile_sam"),
        )


def test_extract_never_restores_pixels_hidden_by_source_alpha(
    app_service,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "transparent-source.png"
    image = Image.new("RGBA", (8, 8), (25, 50, 75, 255))
    image.putpixel((0, 0), (125, 150, 175, 0))
    image.save(source)
    project = _create(app_service, source)

    def return_empty_mask(image, profile, hints):
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        return SegmentResult(
            mask=mask,
            rgba=extract_rgba(image, mask),
            profile=profile,
            parameters={},
            hints=hints,
        )

    monkeypatch.setattr(app_service._segmenter, "segment", return_empty_mask)

    extraction = app_service.extract(
        project.id,
        ExtractCommand(
            profile=ProfileId.SILHOUETTE,
            strokes=[MaskStroke(MaskEditMode.KEEP, [(0, 0)], 3)],
        ),
    )

    with Image.open(extraction.path) as extracted:
        assert extracted.convert("RGBA").getchannel("A").getpixel((0, 0)) == 0
        assert extracted.convert("RGBA").getpixel((0, 0))[:3] == (125, 150, 175)
    pending = app_service.load_project(project.id).processing_parameters["pending_extraction"]
    mask_path = app_service.repository.project_dir(project.id) / pending["mask"]
    with Image.open(mask_path) as saved_mask:
        assert saved_mask.convert("L").getpixel((0, 0)) == 0


@pytest.mark.parametrize("size", [(1, 2), (2, 1), (1, 1)])
def test_extract_rejects_images_smaller_than_two_by_two(
    app_service,
    tmp_path: Path,
    size: tuple[int, int],
) -> None:
    source = tmp_path / f"tiny-{size[0]}x{size[1]}.png"
    Image.new("RGB", size, (200, 100, 50)).save(source)
    project = _create(app_service, source)

    with pytest.raises(WorkflowError, match="至少需要 2×2"):
        app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))


@pytest.mark.parametrize(
    "preprocess",
    [
        {"white_balance_strength": "0.1"},
        {"white_balance_strength": True},
        {"denoise_strength": "3"},
        {"denoise_strength": False},
        {"clahe_clip_limit": "1.25"},
        {"clahe_clip_limit": True},
        {"clahe_tile_grid_size": ("8", 8)},
        {"clahe_tile_grid_size": (True, 8)},
    ],
)
def test_extract_command_rejects_preprocess_field_coercion(
    preprocess: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ExtractCommand(profile=ProfileId.FLAT_COLOR, preprocess=preprocess)  # type: ignore[arg-type]


def test_extract_command_accepts_json_style_grid_list() -> None:
    command = ExtractCommand(
        profile=ProfileId.FLAT_COLOR,
        preprocess={"clahe_tile_grid_size": [4, 6]},  # type: ignore[arg-type]
    )

    assert command.preprocess.clahe_tile_grid_size == (4, 6)


def test_extract_command_accepts_grid_array_from_json() -> None:
    command = ExtractCommand.model_validate_json(
        json.dumps(
            {
                "profile": ProfileId.FLAT_COLOR.value,
                "preprocess": {"clahe_tile_grid_size": [4, 6]},
            }
        )
    )

    assert command.preprocess.clahe_tile_grid_size == (4, 6)


def test_extract_command_defaults_to_opencv_and_serializes_backend() -> None:
    command = ExtractCommand(profile=ProfileId.FLAT_COLOR)

    assert command.backend is workflow.SegmentationBackend.OPENCV
    assert command.model_dump(mode="json")["backend"] == "opencv"


def test_extract_command_accepts_mobile_sam_at_python_and_json_boundaries() -> None:
    command = ExtractCommand(profile=ProfileId.FLAT_COLOR, backend="mobile_sam")
    restored = ExtractCommand.model_validate_json(command.model_dump_json())

    assert command.backend is workflow.SegmentationBackend.MOBILE_SAM
    assert restored.backend is workflow.SegmentationBackend.MOBILE_SAM


@pytest.mark.parametrize(
    "backend",
    ["MobileSAM", "MOBILE_SAM", "mobile-sam", "", 1, True, None],
)
def test_extract_command_rejects_invalid_backend_values(backend: object) -> None:
    with pytest.raises(ValidationError):
        ExtractCommand(profile=ProfileId.FLAT_COLOR, backend=backend)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "grid",
    [
        [True, 8],
        [8.0, 8],
        ["8", 8],
        [8],
        [8, 8, 8],
        [0, 8],
        [17, 8],
    ],
)
def test_extract_command_rejects_invalid_grid_arrays_from_json(grid: list[object]) -> None:
    payload = json.dumps(
        {
            "profile": ProfileId.FLAT_COLOR.value,
            "preprocess": {"clahe_tile_grid_size": grid},
        }
    )

    with pytest.raises(ValidationError):
        ExtractCommand.model_validate_json(payload)


def test_confirm_extraction_clears_pending_extraction(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture)
    extraction = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    pending = app_service.load_project(project.id).processing_parameters.get("pending_extraction")
    assert isinstance(pending, dict) and pending.get("artifact_id") == extraction.artifact_id
    confirmed = app_service.confirm_extraction(project.id, extraction.artifact_id)
    assert confirmed.processing_parameters.get("pending_extraction") in (None, {})
    with pytest.raises(WorkflowError, match="提取"):
        app_service.confirm_extraction(project.id, extraction.artifact_id)


def test_confirm_rejects_missing_extraction(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture)
    with pytest.raises(WorkflowError, match="提取"):
        app_service.confirm_extraction(project.id, "extracted/v1.png")


def test_analyze_rejects_unconfirmed_extraction(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture)
    app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    with pytest.raises(WorkflowError, match="确认"):
        app_service.analyze(project.id)


def test_compose_rejects_without_analysis(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture)
    _extract_and_confirm(app_service, project.id)
    with pytest.raises(WorkflowError, match="分析"):
        app_service.compose(
            project.id,
            PatternRequest(layout=LayoutKind.RADIAL, canvas=(128, 128), seed=7),
        )


def test_reconfirm_extraction_invalidates_downstream(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture)
    _extract_and_confirm(app_service, project.id)
    analysis = app_service.analyze(project.id)
    pattern = app_service.compose(
        project.id,
        PatternRequest(layout=LayoutKind.RADIAL, canvas=(128, 128), seed=7),
    )
    assert analysis.palette
    second = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    updated = app_service.confirm_extraction(project.id, second.artifact_id)
    assert StepId.ANALYSIS not in updated.confirmed_steps
    assert StepId.RECOMPOSITION not in updated.confirmed_steps
    assert pattern.artifact_id in updated.stale_artifacts
    with pytest.raises(WorkflowError, match="分析"):
        app_service.compose(
            project.id,
            PatternRequest(layout=LayoutKind.RADIAL, canvas=(128, 128), seed=7),
        )


def test_generation_failure_preserves_prompt_and_settings(
    app_service,
    source_fixture: Path,
    generation_adapters: dict[ProviderId, object],
) -> None:
    project = _create(app_service, source_fixture)
    confirmed, extraction = _extract_and_confirm(app_service, project.id)
    _ = confirmed
    project_dir = app_service.repository.project_dir(project.id)
    reference = project_dir / extraction.artifact_id
    request = make_generation_request(
        reference,
        prompt="保持莲纹骨架，生成书签纹样",
        structure_level=StructureLevel.HIGH,
        target_application=TargetApplication.BOOKMARK,
    )
    original = request.model_dump()
    generation_adapters[ProviderId.SEEDREAM].fail = True
    with pytest.raises(GenerationFailure):
        app_service.generate(project.id, request, CredentialMode.PLATFORM, None)
    assert request.model_dump() == original
    reloaded = app_service.load_project(project.id)
    stored = reloaded.processing_parameters["generation"]
    assert stored["prompt"] == request.prompt
    assert stored["provider"] == ProviderId.SEEDREAM.value
    assert stored["model"] == request.model
    assert "secret" not in str(reloaded.processing_parameters).lower()
    assert "api_key" not in str(reloaded.processing_parameters).lower()


def test_artifact_path_escape_is_rejected(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture)
    extraction = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    app_service.confirm_extraction(project.id, extraction.artifact_id)
    with pytest.raises(WorkflowError, match="路径"):
        app_service.make_mockup(project.id, "bookmark", "../outside.png")


def test_reconfirm_extraction_does_not_export_stale_generations(
    app_service,
    source_fixture: Path,
) -> None:
    project = _create(app_service, source_fixture)
    _confirmed, extraction = _extract_and_confirm(app_service, project.id)
    app_service.analyze(project.id)
    app_service.compose(
        project.id,
        PatternRequest(layout=LayoutKind.RADIAL, canvas=(128, 128), seed=7),
    )
    project_dir = app_service.repository.project_dir(project.id)
    request = make_generation_request(project_dir / extraction.artifact_id)
    result = app_service.generate(project.id, request, CredentialMode.PLATFORM, None)
    generated = Path(result.local_files[0])
    generated_bytes = generated.read_bytes()
    generated_id = generated.relative_to(project_dir).as_posix()

    second = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    updated = app_service.confirm_extraction(project.id, second.artifact_id)
    assert generated_id in updated.stale_artifacts
    assert all(record.artifact_path not in updated.stale_artifacts for record in updated.generations)
    assert generated.exists()
    assert generated.read_bytes() == generated_bytes

    package = app_service.export(
        project.id,
        ExportSelection(generations=True, report=True),
    )
    generated_dir = package / "generated"
    exported = list(generated_dir.glob("*.png")) if generated_dir.exists() else []
    assert exported == []


def test_make_mockup_rejects_stale_pattern_after_invalidation(app_service, source_fixture: Path) -> None:
    project = _create(app_service, source_fixture)
    _extract_and_confirm(app_service, project.id)
    app_service.analyze(project.id)
    pattern = app_service.compose(
        project.id,
        PatternRequest(layout=LayoutKind.RADIAL, canvas=(128, 128), seed=7),
    )
    assert pattern.path.exists()
    second = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    app_service.confirm_extraction(project.id, second.artifact_id)
    with pytest.raises(WorkflowError, match="贴图"):
        app_service.make_mockup(project.id, "bookmark", pattern.artifact_id)


def test_reconfirm_extraction_does_not_export_stale_mockups(
    app_service, source_fixture: Path
) -> None:
    project = _create(app_service, source_fixture)
    _extract_and_confirm(app_service, project.id)
    app_service.analyze(project.id)
    pattern = app_service.compose(
        project.id,
        PatternRequest(layout=LayoutKind.RADIAL, canvas=(128, 128), seed=7),
    )
    mockup = app_service.make_mockup(project.id, "bookmark", pattern.artifact_id)
    mockup_bytes = mockup.path.read_bytes()
    recorded = app_service.load_project(project.id)
    assert mockup.artifact_id in recorded.processing_parameters.get("current_mockups", [])

    second = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    updated = app_service.confirm_extraction(project.id, second.artifact_id)
    current = updated.processing_parameters.get("current_mockups")
    assert mockup.artifact_id not in (current or [])
    assert mockup.path.exists()
    assert mockup.path.read_bytes() == mockup_bytes

    package = app_service.export(
        project.id,
        ExportSelection(mockups=True, report=True),
    )
    mockups_dir = package / "mockups"
    exported = list(mockups_dir.glob("*.png")) if mockups_dir.exists() else []
    assert exported == []
    assert not any(path.read_bytes() == mockup_bytes for path in package.rglob("*.png"))
    if mockups_dir.exists():
        assert not any(path.suffix.lower() == ".json" for path in mockups_dir.rglob("*"))
