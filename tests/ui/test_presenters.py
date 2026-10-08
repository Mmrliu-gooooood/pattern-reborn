# -*- coding: utf-8 -*-
"""Readers that let each studio step rebuild its results from persisted state."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from PIL import Image
import pytest

from pattern_reborn.domain import (
    ArtifactIndex,
    CategoryId,
    GenerationRecord,
    ProfileId,
    ProjectRecord,
    ProvenanceClass,
    SourceRecord,
    StepId,
)
from pattern_reborn.ui.labels import artwork_label, is_ai_artwork, mockup_template_label
from pattern_reborn.ui.presenters import (
    AnalysisView,
    artifact_path,
    confirmed_extraction,
    current_artworks,
    current_generations,
    current_mockups,
    current_patterns,
    load_analysis,
    pending_extraction,
    source_path,
)


def _project(tmp_path: Path, **overrides) -> ProjectRecord:
    source = tmp_path / "source" / "abc.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(source)
    now = datetime(2026, 8, 30, tzinfo=UTC)
    defaults = dict(
        id="project-0123456789abcdef",
        name="测试项目",
        category=CategoryId.PAPER_CUTTING,
        provenance=ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
        source=SourceRecord(
            original_filename="abc.png",
            relative_path="source/abc.png",
            sha256="a" * 64,
            byte_size=source.stat().st_size,
        ),
        created_at=now,
        updated_at=now,
        profile=ProfileId.SILHOUETTE,
    )
    defaults.update(overrides)
    return ProjectRecord(**defaults)


def _write_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (200, 40, 40)).save(path)
    return path


def _write_analysis(path: Path, palette=None, matches=None, contours=None, symmetry=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "profile": "silhouette",
                "algorithm": "opencv-baseline-1.0",
                "palette": palette
                if palette is not None
                else [{"hex_value": "#B8282E", "coverage": 0.5, "pixel_count": 32, "rgb": [184, 40, 46]}],
                "color_matches": matches
                if matches is not None
                else [{"hex_value": "#B8282E", "traditional_name_zh": "朱砂", "distance": 4.2}],
                "contours": contours if contours is not None else {"contour_count": 2, "hole_count": 1},
                "symmetry": symmetry if symmetry is not None else {"vertical_score": 0.9, "horizontal_score": 0.4},
            }
        ),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------- paths


def test_artifact_path_rejects_traversal_and_absolute_ids(tmp_path: Path) -> None:
    _write_png(tmp_path / "extracted" / "v1.png")
    assert artifact_path(tmp_path, "extracted/v1.png") is not None
    assert artifact_path(tmp_path, "../outside.png") is None
    assert artifact_path(tmp_path, "/etc/passwd") is None
    assert artifact_path(tmp_path, "extracted/missing.png") is None
    assert artifact_path(tmp_path, None) is None
    assert artifact_path(tmp_path, "") is None


def test_source_path_reads_the_recorded_source(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert source_path(tmp_path, project) is not None
    project.source = project.source.model_copy(update={"relative_path": "source/gone.png"})
    assert source_path(tmp_path, project) is None


# ---------------------------------------------------------------- extraction


def test_pending_extraction_ignores_a_missing_artifact(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project.processing_parameters = {
        "pending_extraction": {"artifact_id": "extracted/v7.png", "mask": "masks/v7.png"}
    }
    assert pending_extraction(tmp_path, project) is None
    _write_png(tmp_path / "extracted" / "v7.png")
    assert pending_extraction(tmp_path, project) == ("extracted/v7.png", tmp_path / "extracted" / "v7.png")


def test_confirmed_extraction_skips_stale_and_mask_entries(tmp_path: Path) -> None:
    _write_png(tmp_path / "extracted" / "v1.png")
    _write_png(tmp_path / "masks" / "v1.png")
    project = _project(tmp_path)
    project.artifacts = ArtifactIndex(extraction=["masks/v1.png", "extracted/v1.png"])
    found = confirmed_extraction(tmp_path, project)
    assert found is not None and found[0] == "extracted/v1.png"

    project.stale_artifacts = ["extracted/v1.png"]
    assert confirmed_extraction(tmp_path, project) is None


# ------------------------------------------------------------------ analysis


def test_load_analysis_reads_the_confirmed_json(tmp_path: Path) -> None:
    _write_analysis(tmp_path / "analysis" / "v1.json")
    project = _project(tmp_path)
    project.artifacts = ArtifactIndex(analysis=["analysis/v1.json"])
    view = load_analysis(tmp_path, project)
    assert isinstance(view, AnalysisView)
    assert view is not None
    assert view.palette[0]["hex_value"] == "#B8282E"
    assert view.color_matches[0]["traditional_name_zh"] == "朱砂"
    assert view.contours["contour_count"] == 2
    assert view.symmetry["vertical_score"] == 0.9


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        "[]",
        '{"palette": [], "color_matches": [], "contours": []}',
        '{"palette": {}, "color_matches": [], "contours": {}, "symmetry": {}}',
    ],
)
def test_load_analysis_degrades_on_a_malformed_artifact(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "analysis" / "v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    project = _project(tmp_path)
    project.artifacts = ArtifactIndex(analysis=["analysis/v1.json"])
    assert load_analysis(tmp_path, project) is None


def test_load_analysis_prefers_the_newest_confirmed_artifact(tmp_path: Path) -> None:
    _write_analysis(tmp_path / "analysis" / "v1.json", contours={"contour_count": 1})
    _write_analysis(tmp_path / "analysis" / "v2.json", contours={"contour_count": 9})
    project = _project(tmp_path)
    project.artifacts = ArtifactIndex(analysis=["analysis/v1.json", "analysis/v2.json"])
    view = load_analysis(tmp_path, project)
    assert view is not None and view.contours["contour_count"] == 9

    project.stale_artifacts = ["analysis/v2.json"]
    fallback = load_analysis(tmp_path, project)
    assert fallback is not None and fallback.contours["contour_count"] == 1


# --------------------------------------------------------------- artworks


def _generated_project(tmp_path: Path) -> ProjectRecord:
    _write_png(tmp_path / "patterns" / "v1.png")
    _write_png(tmp_path / "generated" / "v2.png")
    _write_png(tmp_path / "generated" / "v3.png")
    project = _project(tmp_path)
    project.artifacts = ArtifactIndex(
        recomposition=["patterns/v1.png"],
        generation=["generated/v2.png", "generated/v3.png"],
    )
    project.generations = [
        GenerationRecord(
            id="gen-000000000001",
            provider="seedream",
            model="doubao-seedream-4-0-250828",
            prompt="莲纹",
            artifact_path="generated/v2.png",
            created_at=datetime(2026, 8, 30, 1, tzinfo=UTC),
        ),
        GenerationRecord(
            id="gen-000000000002",
            provider="qwen",
            model="qwen-image-3.0-pro",
            prompt="云纹",
            artifact_path="generated/v3.png",
            created_at=datetime(2026, 8, 30, 2, tzinfo=UTC),
        ),
    ]
    return project


def test_current_artworks_includes_confirmed_recomposition_and_generations(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    ids = [view.artifact_id for view in current_artworks(tmp_path, project)]
    assert ids == ["patterns/v1.png", "generated/v2.png", "generated/v3.png"]
    flags = {view.artifact_id: view.ai_assisted for view in current_artworks(tmp_path, project)}
    assert flags["patterns/v1.png"] is False
    assert flags["generated/v2.png"] is True


def test_current_artworks_excludes_stale_entries(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    project.stale_artifacts = ["generated/v2.png"]
    ids = [view.artifact_id for view in current_artworks(tmp_path, project)]
    assert ids == ["patterns/v1.png", "generated/v3.png"]


def test_current_patterns_only_returns_pattern_pngs(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    project.artifacts = ArtifactIndex(
        recomposition=["patterns/v1.png", "patterns/v1.svg", "patterns/missing.png"]
    )
    paths = current_patterns(tmp_path, project)
    assert paths == [tmp_path / "patterns" / "v1.png"]


def test_current_generations_is_newest_first_with_metadata(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    views = current_generations(tmp_path, project)
    assert [view.artifact_id for view in views] == ["generated/v3.png", "generated/v2.png"]
    assert views[0].provider == "qwen"
    assert views[0].model == "qwen-image-3.0-pro"
    assert views[0].prompt == "云纹"
    assert views[0].created_at.startswith("2026.08.30")


def test_current_mockups_reads_the_recorded_ids(tmp_path: Path) -> None:
    _write_png(tmp_path / "mockups" / "bookmark-v1.png")
    project = _project(tmp_path)
    project.processing_parameters = {"current_mockups": ["mockups/bookmark-v1.png", "mockups/gone.png"]}
    assert current_mockups(tmp_path, project) == [tmp_path / "mockups" / "bookmark-v1.png"]
    project.processing_parameters = {"current_mockups": "not-a-list"}
    assert current_mockups(tmp_path, project) == []


# ------------------------------------------------------------------- labels


def test_artwork_labels_flag_ai_outputs() -> None:
    assert artwork_label("patterns/v1.png") == "重组纹样 · patterns/v1.png"
    assert artwork_label("generated/v3.png") == "AI 生成 · generated/v3.png"
    assert is_ai_artwork("generated/v3.png") is True
    assert is_ai_artwork("patterns/v1.png") is False


def test_mockup_template_labels_fall_back_to_the_raw_id() -> None:
    assert mockup_template_label("bookmark") == "书签"
    assert mockup_template_label("unknown_template") == "unknown_template"


def test_confirmed_step_reports_recorded_steps(tmp_path: Path) -> None:
    from pattern_reborn.ui.presenters import confirmed_step

    project = _project(tmp_path, confirmed_steps=[StepId.UPLOAD, StepId.EXTRACTION])
    assert confirmed_step(project, StepId.UPLOAD) is True
    assert confirmed_step(project, StepId.ANALYSIS) is False
