# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pattern_reborn.domain import CategoryId, ProfileId, ProvenanceClass, StepId
from pattern_reborn.generation.base import (
    CredentialMode,
    GenerationFailure,
    ProviderId,
    StructureLevel,
    TargetApplication,
)
from pattern_reborn.patterns import LayoutKind, PatternRequest
from pattern_reborn.workflow import CreateProjectCommand, ExtractCommand, WorkflowError
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
