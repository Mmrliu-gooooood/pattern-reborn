# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

from pattern_reborn.domain import CategoryId, ProfileId, ProvenanceClass, StepId
from pattern_reborn.exporter import ExportSelection
from pattern_reborn.generation.base import CredentialMode, GenerationFailure, ProviderId
from pattern_reborn.patterns import LayoutKind, PatternRequest
from pattern_reborn.workflow import CreateProjectCommand, ExtractCommand
from tests.test_generation_base import make_generation_request
from tests.workflow_fixtures import DEMO_ROOT, competition_case_ids, load_demo_fixture

COMPETITION_CASE_IDS = competition_case_ids()


def test_every_bundled_demo_case_is_available() -> None:
    assert COMPETITION_CASE_IDS == [
        "lotus-paper-cut",
        "fish-lotus-blue-calico",
        "peony-embroidery",
        "scrolling-lotus-ceramic",
        "new-year-picture-detail",
        "architectural-cloud",
    ]


@pytest.mark.parametrize("case_id", COMPETITION_CASE_IDS)
def test_each_demo_reaches_traceable_export_offline(app_service, case_id: str) -> None:
    """A judge must complete the whole offline flow from any bundled case.

    The case is opened through the same loader the home page uses, extracted
    with the shipped default profile (the service applies the case's recorded
    region), analysed, recomposed on the studio's default canvas, and exported.
    """
    fixture = load_demo_fixture(DEMO_ROOT, case_id)

    project = app_service.create_project(
        CreateProjectCommand(
            name=fixture.title,
            source=fixture.source,
            category=fixture.category,
            provenance=fixture.provenance,
            hint_box=fixture.hint_box,
        )
    )
    extraction = app_service.extract(project.id, ExtractCommand(profile=fixture.profile))
    app_service.confirm_extraction(project.id, extraction.artifact_id)
    analysis = app_service.analyze(project.id)
    pattern = app_service.compose(project.id, fixture.pattern_request)
    package = app_service.export(project.id, ExportSelection.all_offline())
    reopened = app_service.load_project(project.id)

    assert analysis.palette, case_id
    with Image.open(pattern.path) as composed:
        assert composed.size == (256, 256)
    assert package.is_dir()
    assert (package / "manifest.json").is_file()
    assert (package / "provenance.md").is_file()
    assert StepId.EXPORT in reopened.confirmed_steps
    assert reopened.processing_parameters["current_step"] == StepId.EXPORT.value


def test_offline_pipeline_reaches_export_without_generation(app_service, source_fixture: Path) -> None:
    original = source_fixture.read_bytes()
    project = app_service.create_project(
        CreateProjectCommand(
            name="剪纸书签",
            source=source_fixture,
            category=CategoryId.PAPER_CUTTING,
            provenance=ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
        )
    )
    extraction = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    app_service.confirm_extraction(project.id, extraction.artifact_id)
    analysis = app_service.analyze(project.id)
    pattern = app_service.compose(
        project.id,
        PatternRequest(layout=LayoutKind.RADIAL, canvas=(128, 128), seed=7),
    )
    mockup = app_service.make_mockup(project.id, "bookmark", pattern.artifact_id)
    package = app_service.export(project.id, ExportSelection.all_offline())
    assert package.exists()
    assert (package / "manifest.json").exists()
    assert (package / "provenance.md").exists()
    assert analysis.palette
    assert mockup.path.exists()
    assert mockup.path.is_relative_to(app_service.repository.project_dir(project.id) / "mockups")
    exported_mockups = list((package / "mockups").glob("*.png"))
    assert len(exported_mockups) == 1
    assert exported_mockups[0].read_bytes() == mockup.path.read_bytes()
    assert not any(path.suffix.lower() == ".json" for path in (package / "mockups").rglob("*"))
    assert source_fixture.read_bytes() == original
    copied_source = app_service.repository.project_dir(project.id) / project.source.relative_path
    assert copied_source.read_bytes() == original


def test_cached_generated_assets_remain_exportable_offline(
    app_service,
    source_fixture: Path,
    generation_adapters: dict[ProviderId, object],
) -> None:
    project = app_service.create_project(
        CreateProjectCommand(
            name="缓存生成",
            source=source_fixture,
            category=CategoryId.PAPER_CUTTING,
            provenance=ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
        )
    )
    extraction = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    app_service.confirm_extraction(project.id, extraction.artifact_id)
    app_service.analyze(project.id)
    pattern = app_service.compose(
        project.id,
        PatternRequest(layout=LayoutKind.RADIAL, canvas=(128, 128), seed=7),
    )
    project_dir = app_service.repository.project_dir(project.id)
    request = make_generation_request(project_dir / extraction.artifact_id)
    result = app_service.generate(project.id, request, CredentialMode.PLATFORM, None)
    assert result.local_files
    generated = Path(result.local_files[0])
    assert generated.exists()
    assert generated.is_relative_to(project_dir)
    generated_bytes = generated.read_bytes()

    generation_adapters[ProviderId.SEEDREAM].fail = True
    with pytest.raises(GenerationFailure):
        app_service.generate(project.id, request, CredentialMode.PLATFORM, None)
    assert generated.read_bytes() == generated_bytes
    assert request.prompt == "保持莲纹骨架，生成书签纹样"

    package = app_service.export(project.id, ExportSelection.all_offline())
    assert package.exists()
    exported = list((package / "generated").glob("*.png"))
    assert exported
    assert exported[0].read_bytes() == generated_bytes
    assert (project_dir / "mockups").exists() or pattern.path.exists()
