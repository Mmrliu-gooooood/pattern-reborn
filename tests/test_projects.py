from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re

import pytest

from pattern_reborn.domain import CategoryId, ProvenanceClass, StepId
import pattern_reborn.projects as projects_module
from pattern_reborn.projects import (
    ProjectCorruptError,
    ProjectPathError,
    ProjectRepository,
    ProjectRepositoryError,
    UnsupportedProjectSchemaError,
)


def make_project(tmp_path: Path) -> tuple[ProjectRepository, object]:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source-bytes")
    repository = ProjectRepository(tmp_path / "workspace")
    return repository, repository.create(
        "测试纹样",
        source,
        CategoryId.PAPER_CUTTING,
        ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
    )


def test_create_copies_and_hashes_source_without_mutating_it(tmp_path: Path) -> None:
    source = tmp_path / "lotus.png"
    source.write_bytes(b"immutable-source")
    repository = ProjectRepository(tmp_path / "workspace")

    project = repository.create(
        "莲纹实验",
        source,
        CategoryId.PAPER_CUTTING,
        ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
    )

    assert source.read_bytes() == b"immutable-source"
    assert project.source.sha256 == "945eb12166e6c63215d07c828c2f00d61c9f5190604161932bbdb802752be67b"
    copied_source = repository.project_dir(project.id) / project.source.relative_path
    assert copied_source.read_bytes() == b"immutable-source"
    assert project.created_at.tzinfo is UTC
    assert project.updated_at.tzinfo is UTC


def test_generated_project_id_is_safe_and_repository_relative(tmp_path: Path) -> None:
    repository, project = make_project(tmp_path)

    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{7,63}", project.id)
    assert repository.project_dir(project.id).is_relative_to((tmp_path / "workspace").resolve())
    with pytest.raises(ProjectPathError, match="项目"):
        repository.project_dir("../escaped-project")


def test_reconfirming_extraction_replaces_its_paths_and_marks_downstream_outputs_stale(
    tmp_path: Path,
) -> None:
    repository, project = make_project(tmp_path)
    project.confirmed_steps = [StepId.UPLOAD, StepId.EXTRACTION, StepId.ANALYSIS]
    project.artifacts.extraction = ["masks/v1.png"]
    project.artifacts.analysis = ["analysis/v1.json"]
    repository.save(project)

    updated = repository.confirm(project.id, StepId.EXTRACTION, ["masks/v2.png"])

    assert updated.confirmed_steps == [StepId.UPLOAD, StepId.EXTRACTION]
    assert updated.artifacts.extraction == ["masks/v2.png"]
    assert updated.artifacts.analysis == []
    assert updated.stale_artifacts == ["analysis/v1.json"]


def test_confirm_rejects_artifact_path_that_escapes_project_directory(tmp_path: Path) -> None:
    repository, project = make_project(tmp_path)

    with pytest.raises(ProjectPathError, match="路径"):
        repository.confirm(project.id, StepId.ANALYSIS, ["../outside.json"])

    assert repository.load(project.id).confirmed_steps == []


def test_list_recent_returns_projects_newest_first(tmp_path: Path) -> None:
    repository, first = make_project(tmp_path)
    second_source = tmp_path / "second.png"
    second_source.write_bytes(b"second")
    second = repository.create(
        "第二个项目",
        second_source,
        CategoryId.FOLK_PAINTING,
        ProvenanceClass.TRADITIONAL_REFERENCE,
    )
    first.updated_at = datetime.now(UTC) + timedelta(days=1)
    repository.save(first)

    recent = repository.list_recent()

    assert [project.id for project in recent] == [first.id, second.id]
    assert repository.list_recent(limit=1) == [first]


def test_load_rejects_unsupported_schema_without_overwriting_file(tmp_path: Path) -> None:
    repository, project = make_project(tmp_path)
    project_file = repository.project_dir(project.id) / "project.json"
    unsupported = '{"schema_version":2,"name":"保留"}'
    project_file.write_text(unsupported, encoding="utf-8")

    with pytest.raises(UnsupportedProjectSchemaError, match="不支持"):
        repository.load(project.id)

    assert project_file.read_text(encoding="utf-8") == unsupported


def test_load_reports_corrupt_json_without_overwriting_file(tmp_path: Path) -> None:
    repository, project = make_project(tmp_path)
    project_file = repository.project_dir(project.id) / "project.json"
    corrupt = "{无效 JSON"
    project_file.write_text(corrupt, encoding="utf-8")

    with pytest.raises(ProjectCorruptError, match="项目"):
        repository.load(project.id)

    assert project_file.read_text(encoding="utf-8") == corrupt


def test_load_rejects_unknown_top_level_field_without_overwriting_file(tmp_path: Path) -> None:
    repository, project = make_project(tmp_path)
    project_file = repository.project_dir(project.id) / "project.json"
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    payload["future_field"] = {"version": 2}
    original_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    project_file.write_bytes(original_bytes)

    with pytest.raises(ProjectCorruptError, match="项目"):
        repository.load(project.id)

    assert project_file.read_bytes() == original_bytes


def test_load_rejects_unknown_nested_field_without_overwriting_file(tmp_path: Path) -> None:
    repository, project = make_project(tmp_path)
    project_file = repository.project_dir(project.id) / "project.json"
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    payload["source"]["future_checksum"] = "unrecognized"
    original_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    project_file.write_bytes(original_bytes)

    with pytest.raises(ProjectCorruptError, match="项目"):
        repository.load(project.id)

    assert project_file.read_bytes() == original_bytes


def test_repository_rejects_workspace_path_that_is_a_file(tmp_path: Path) -> None:
    workspace_file = tmp_path / "workspace-file"
    workspace_file.write_bytes(b"not a directory")

    with pytest.raises(ProjectRepositoryError) as captured:
        ProjectRepository(workspace_file)

    assert "工作区" in str(captured.value)
    assert str(workspace_file) not in str(captured.value)


def test_save_hides_replace_permission_error_and_preserves_original_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, project = make_project(tmp_path)
    project_file = repository.project_dir(project.id) / "project.json"
    original_bytes = project_file.read_bytes()
    temporary_file = repository.project_dir(project.id) / "project.json.tmp"

    def reject_replace(source: object, destination: object) -> None:
        raise PermissionError(f"access denied: {source}")

    monkeypatch.setattr(projects_module.os, "replace", reject_replace)

    with pytest.raises(ProjectRepositoryError) as captured:
        repository.save(project)

    assert project_file.read_bytes() == original_bytes
    assert not temporary_file.exists()
    assert str(temporary_file) not in str(captured.value)
    assert "access denied" not in str(captured.value).lower()


def test_save_is_atomic_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    repository, project = make_project(tmp_path)

    repository.save(project)

    project_dir = repository.project_dir(project.id)
    assert (project_dir / "project.json").exists()
    assert not list(project_dir.glob("*.tmp"))
