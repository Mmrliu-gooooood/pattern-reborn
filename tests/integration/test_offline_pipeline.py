# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from pattern_reborn.domain import CategoryId, ProfileId, ProvenanceClass
from pattern_reborn.exporter import ExportSelection
from pattern_reborn.generation.base import CredentialMode, GenerationFailure, ProviderId
from pattern_reborn.patterns import LayoutKind, PatternRequest
from pattern_reborn.workflow import CreateProjectCommand, ExtractCommand
from tests.test_generation_base import make_generation_request


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
