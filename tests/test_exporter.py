# -*- coding: utf-8 -*-
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re

import pytest

from pattern_reborn.domain import CategoryId, GenerationRecord, ProvenanceClass
from pattern_reborn.exporter import ExportError, Exporter, ExportSelection
from pattern_reborn.projects import ProjectRepository
from tests.fixtures.images import write_image
from tests.test_projects import make_project


_SECRET_MARKERS = ("api_key", "Bearer", "authorization", "sk-secret-value")


@pytest.fixture
def project(tmp_path: Path):
    repository, record = make_project(tmp_path)
    project_dir = repository.project_dir(record.id)
    (project_dir / "patterns").mkdir()
    (project_dir / "generated").mkdir()
    write_image(project_dir / "patterns" / "repeat.png", image_format="PNG", size=(10, 8))
    write_image(project_dir / "generated" / "seedream.png", image_format="PNG", size=(10, 8))
    record.artifacts.recomposition = ["patterns/repeat.png"]
    record.processing_parameters = {
        "api_key": "sk-secret-value",
        "authorization": "Bearer sk-secret-value",
        "layout": "radial",
    }
    record.generations = [
        GenerationRecord(
            id="gen-seedream-1",
            provider="seedream",
            model="seedream-4.5",
            prompt="莲纹书签",
            artifact_path="generated/seedream.png",
            created_at=datetime(2026, 8, 29, 10, 15, tzinfo=UTC),
        )
    ]
    return record


def _project_dir(tmp_path: Path, project) -> Path:
    return (tmp_path / "workspace" / project.id).resolve()


def _exporter(tmp_path: Path, project) -> Exporter:
    return Exporter(_project_dir(tmp_path, project))


def _write_mockup_with_provenance(path: Path, *, ai_assisted: bool) -> Path:
    written = write_image(path, image_format="PNG", size=(12, 8))
    path.with_suffix(".json").write_text(
        json.dumps({"ai_assisted": ai_assisted}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return written


def _package_text(package: Path) -> str:
    chunks: list[str] = []
    for path in package.rglob("*"):
        if not path.is_file():
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    return "\n".join(chunks)


def test_export_contains_manifest_report_and_selected_assets(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    assert (package / "manifest.json").exists()
    report = (package / "provenance.md").read_text(encoding="utf-8")
    assert project.source.sha256 in report
    assert "AI 辅助" in report
    assert (package / "attribution.md").exists()
    copied = list((package / "patterns").glob("*.png"))
    assert copied
    assert copied[0].read_bytes() == (project_dir / project.artifacts.recomposition[0]).read_bytes()


def test_export_paths_stay_under_destination_root(project, tmp_path) -> None:
    destination = tmp_path / "exports"
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), destination
    )
    root = destination.resolve()
    assert package.resolve().is_relative_to(root)
    for path in package.rglob("*"):
        assert path.resolve().is_relative_to(root)


def test_export_rejects_path_outside_project_root(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    outside = write_image(tmp_path / "outside-secret.png", image_format="PNG", size=(8, 8))
    secret_bytes = outside.read_bytes()
    destination = tmp_path / "exports"
    destination.mkdir()

    project.artifacts.recomposition = [str(outside.resolve())]
    with pytest.raises(ExportError):
        Exporter(project_dir).export(project, ExportSelection(patterns=True), destination)

    relative_escape = Path(os.path.relpath(outside, project_dir)).as_posix()
    project.artifacts.recomposition = [relative_escape]
    with pytest.raises(ExportError):
        Exporter(project_dir).export(project, ExportSelection(patterns=True), destination)

    leaked = [path for path in destination.rglob("*") if path.is_file()]
    assert leaked == []
    assert all(path.read_bytes() != secret_bytes for path in leaked)


def test_export_omits_secret_shaped_fields(project, tmp_path) -> None:
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    blob = _package_text(package)
    for marker in _SECRET_MARKERS:
        assert marker not in blob
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    dumped = json.dumps(manifest)
    for marker in _SECRET_MARKERS:
        assert marker not in dumped


def test_attribution_names_team_templates_and_source(project, tmp_path) -> None:
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    attribution = (package / "attribution.md").read_text(encoding="utf-8")
    assert "Pattern Reborn team" in attribution
    assert "project-original" in attribution
    assert project.source.original_filename in attribution or project.source.sha256 in attribution


def test_unsafe_names_are_sanitized_and_contained(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source-bytes")
    repository = ProjectRepository(tmp_path / "workspace")
    record = repository.create(
        "..\\evil:name*",
        source,
        CategoryId.PAPER_CUTTING,
        ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
    )
    project_dir = repository.project_dir(record.id)
    (project_dir / "patterns").mkdir()
    write_image(
        project_dir / "patterns" / "ok.png",
        image_format="PNG",
        size=(8, 8),
    )
    record.artifacts.recomposition = ["patterns/ok.png"]
    destination = tmp_path / "out"
    package = Exporter(project_dir).export(record, ExportSelection(patterns=True, report=True), destination)

    assert package.parent.resolve() == destination.resolve()
    assert ".." not in package.name
    assert not re.search(r'[<>:"/\\|?*]', package.name)
    for path in package.rglob("*"):
        assert path.resolve().is_relative_to(destination.resolve())
        if path.is_file():
            assert not re.search(r'[<>:"/\\|?*]', path.name)


def test_manifest_schema_is_versioned_and_stable(project, tmp_path) -> None:
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert set(manifest) >= {
        "schema_version",
        "project_id",
        "project_name",
        "exported_at",
        "source",
        "files",
        "generations",
    }
    assert manifest["project_id"] == project.id
    assert manifest["source"]["sha256"] == project.source.sha256
    assert isinstance(manifest["files"], list)
    assert manifest["files"]
    for entry in manifest["files"]:
        assert set(entry) >= {"path", "kind", "sha256", "ai_assisted"}
        assert ".." not in entry["path"]
    assert isinstance(manifest["generations"], list)
    generation = manifest["generations"][0]
    assert set(generation) >= {"id", "provider", "model", "prompt", "created_at", "ai_assisted"}
    assert generation["ai_assisted"] is True
    assert generation["provider"] == "seedream"
    assert generation["model"] == "seedream-4.5"
    assert generation["prompt"] == "莲纹书签"
    report = (package / "provenance.md").read_text(encoding="utf-8")
    assert "seedream" in report
    assert "seedream-4.5" in report
    assert "莲纹书签" in report


def test_export_copies_only_listed_current_mockup_paths(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    project.generations = []
    mockups_dir = project_dir / "mockups"
    mockups_dir.mkdir()
    current = _write_mockup_with_provenance(mockups_dir / "bookmark.png", ai_assisted=False)
    obsolete = write_image(mockups_dir / "obsolete.png", image_format="PNG", size=(16, 10))
    project.processing_parameters["current_mockups"] = ["mockups/bookmark.png"]
    package = Exporter(project_dir).export(
        project,
        ExportSelection(mockups=True, report=True),
        tmp_path / "exports",
    )

    copied = list((package / "mockups").rglob("*.png"))
    assert len(copied) == 1
    assert copied[0].read_bytes() == current.read_bytes()
    assert copied[0].name == "bookmark.png"
    assert not any(path.name == "obsolete.png" for path in package.rglob("*"))
    assert not any(path.read_bytes() == obsolete.read_bytes() for path in package.rglob("*.png"))
    assert not any(path.suffix.lower() == ".json" for path in (package / "mockups").rglob("*"))


def test_export_copies_contained_mockup_png_as_ai_assisted(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    project.generations = []
    mockups_dir = project_dir / "mockups"
    mockups_dir.mkdir()
    mockup = _write_mockup_with_provenance(mockups_dir / "bookmark.png", ai_assisted=True)
    outside = write_image(project_dir / "outside.png", image_format="PNG", size=(8, 8))
    project.processing_parameters["current_mockups"] = ["mockups/bookmark.png"]
    destination = tmp_path / "exports"
    package = Exporter(project_dir).export(
        project,
        ExportSelection(mockups=True, report=True),
        destination,
    )

    copied = list((package / "mockups").rglob("*.png"))
    assert len(copied) == 1
    assert copied[0].read_bytes() == mockup.read_bytes()
    assert copied[0].resolve().is_relative_to(destination.resolve())
    assert not any(path.read_bytes() == outside.read_bytes() for path in package.rglob("*.png"))
    assert not any(path.suffix.lower() == ".json" for path in (package / "mockups").rglob("*"))
    for path in package.rglob("*"):
        assert path.resolve().is_relative_to(destination.resolve())
        assert ".." not in path.relative_to(destination).as_posix()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    mockup_entries = [item for item in manifest["files"] if item["kind"] == "mockup"]
    assert len(mockup_entries) == 1
    assert mockup_entries[0]["ai_assisted"] is True
    assert mockup_entries[0]["path"].startswith("mockups/")
    assert ".." not in mockup_entries[0]["path"]


def test_export_non_ai_mockup_not_assisted_when_generation_exists(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    assert project.generations
    mockups_dir = project_dir / "mockups"
    mockups_dir.mkdir()
    mockup = _write_mockup_with_provenance(mockups_dir / "tote_bag.png", ai_assisted=False)
    project.processing_parameters["current_mockups"] = ["mockups/tote_bag.png"]
    package = Exporter(project_dir).export(
        project,
        ExportSelection(mockups=True, report=True),
        tmp_path / "exports",
    )

    copied = list((package / "mockups").rglob("*.png"))
    assert len(copied) == 1
    assert copied[0].read_bytes() == mockup.read_bytes()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    mockup_entries = [item for item in manifest["files"] if item["kind"] == "mockup"]
    assert len(mockup_entries) == 1
    assert mockup_entries[0]["ai_assisted"] is False


def test_export_generated_copies_remain_ai_assisted(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    mockups_dir = project_dir / "mockups"
    mockups_dir.mkdir()
    _write_mockup_with_provenance(mockups_dir / "bookmark.png", ai_assisted=False)
    project.processing_parameters["current_mockups"] = ["mockups/bookmark.png"]
    package = Exporter(project_dir).export(
        project,
        ExportSelection(generations=True, mockups=True, report=True),
        tmp_path / "exports",
    )
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    generated = [item for item in manifest["files"] if item["kind"] == "generation"]
    mockups = [item for item in manifest["files"] if item["kind"] == "mockup"]
    assert generated
    assert all(item["ai_assisted"] is True for item in generated)
    assert mockups
    assert all(item["ai_assisted"] is False for item in mockups)


def test_export_omits_mockups_when_not_selected(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    mockups_dir = project_dir / "mockups"
    mockups_dir.mkdir()
    write_image(mockups_dir / "bookmark.png", image_format="PNG", size=(12, 8))
    package = Exporter(project_dir).export(
        project,
        ExportSelection(patterns=True, mockups=False, report=True),
        tmp_path,
    )
    assert not (package / "mockups").exists()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert all(item["kind"] != "mockup" for item in manifest["files"])


def test_export_redacts_secret_shaped_prompt_text(project, tmp_path) -> None:
    project.generations[0].prompt = "莲纹 Bearer sk-secret-value api_key=sk-secret-value"
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    blob = _package_text(package)
    for marker in ("Bearer", "sk-secret-value", "api_key"):
        assert marker not in blob
    report = (package / "provenance.md").read_text(encoding="utf-8")
    assert "seedream" in report
    assert "seedream-4.5" in report
    assert "2026-08-29T10:15:00Z" in report
    assert "AI 辅助" in report


def test_export_redacts_prompt_secrets_before_json_dumps(project, tmp_path) -> None:
    project.generations[0].prompt = "keep-me authorization=abc"
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    raw = (package / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(raw)
    prompt = manifest["generations"][0]["prompt"]
    assert prompt == "[REDACTED]"
    assert "authorization" not in prompt.lower()
    assert "abc" not in prompt
    assert manifest["schema_version"] == 1
    assert manifest["generations"][0]["id"] == project.generations[0].id
    assert "authorization" not in raw.lower()
    assert "abc" not in raw


def test_export_redacts_authorization_bearer_token(project, tmp_path) -> None:
    project.generations[0].prompt = "keep-me Authorization: Bearer secret-value"
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["generations"][0]["prompt"] == "[REDACTED]"
    for path in package.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert "secret-value" not in text


def test_export_redacts_entire_basic_credential_string(project, tmp_path) -> None:
    secret = "Authorization: Basic abc123"
    project.name = secret
    project.generations[0].prompt = secret
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    assert "abc123" not in package.name
    for path in package.rglob("*"):
        assert "abc123" not in path.name
        assert "abc123" not in path.relative_to(package).as_posix()
    blob = _package_text(package)
    assert "abc123" not in blob
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    dumped = json.dumps(manifest)
    assert "abc123" not in dumped
    assert manifest["schema_version"] == 1
    assert manifest["project_name"] == "[REDACTED]"
    assert manifest["generations"][0]["prompt"] == "[REDACTED]"


def test_export_redacts_project_name_and_source_filename_secrets(project, tmp_path) -> None:
    project.name = "Demo Authorization: Bearer leaked-name-token"
    project.source.original_filename = "lotus api_key=leaked-file-token.jpg"
    project.generations[0].id = "gen Authorization: Bearer leaked-id-token"
    project.generations[0].provider = "seedream api_key=leaked-provider-token"
    project.generations[0].model = "seedream-4.5 Bearer leaked-model-token"
    package = _exporter(tmp_path, project).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    leaked = (
        "leaked-name-token",
        "leaked-file-token",
        "leaked-id-token",
        "leaked-provider-token",
        "leaked-model-token",
    )
    blob = _package_text(package)
    for token in leaked:
        assert token not in blob
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    dumped = json.dumps(manifest)
    for token in leaked:
        assert token not in dumped
    report = (package / "provenance.md").read_text(encoding="utf-8")
    assert project.source.sha256 in report


def test_provenance_discloses_ai_mockup_without_generations(project, tmp_path) -> None:
    project.generations = []
    project_dir = _project_dir(tmp_path, project)
    mockups_dir = project_dir / "mockups"
    mockups_dir.mkdir()
    _write_mockup_with_provenance(mockups_dir / "bookmark.png", ai_assisted=True)
    project.processing_parameters["current_mockups"] = ["mockups/bookmark.png"]
    package = Exporter(project_dir).export(
        project,
        ExportSelection(mockups=True, report=True),
        tmp_path / "exports",
    )
    report = (package / "provenance.md").read_text(encoding="utf-8")
    assert "AI 辅助" in report
    assert project.source.sha256 in report


def test_sanitized_pattern_basename_collisions_stay_unique(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    patterns_dir = project_dir / "patterns"
    first = write_image(patterns_dir / "ok.png", image_format="PNG", size=(10, 8))
    second = write_image(patterns_dir / "ok..png", image_format="PNG", size=(12, 8))
    project.artifacts.recomposition = ["patterns/ok.png", "patterns/ok..png"]
    package = Exporter(project_dir).export(project, ExportSelection(patterns=True, report=True), tmp_path)

    copied = sorted((package / "patterns").glob("*.png"))
    assert len(copied) == 2
    assert copied[0].name != copied[1].name
    exported_bytes = {path.read_bytes() for path in copied}
    assert first.read_bytes() in exported_bytes
    assert second.read_bytes() in exported_bytes
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    paths = [item["path"] for item in manifest["files"] if item["kind"] == "pattern"]
    assert len(paths) == 2
    assert len(set(paths)) == 2


def test_case_insensitive_pattern_names_stay_unique(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    patterns_dir = project_dir / "patterns"
    nested = patterns_dir / "nested"
    nested.mkdir()
    first = write_image(patterns_dir / "A.png", image_format="PNG", size=(10, 8))
    second = write_image(nested / "a.png", image_format="PNG", size=(12, 8))
    project.artifacts.recomposition = ["patterns/A.png", "patterns/nested/a.png"]
    package = Exporter(project_dir).export(project, ExportSelection(patterns=True, report=True), tmp_path)

    copied = list((package / "patterns").glob("*.png"))
    assert len(copied) == 2
    assert len({path.name.lower() for path in copied}) == 2
    exported_bytes = {path.read_bytes() for path in copied}
    assert first.read_bytes() in exported_bytes
    assert second.read_bytes() in exported_bytes
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    paths = [item["path"] for item in manifest["files"] if item["kind"] == "pattern"]
    assert len(paths) == 2
    assert len(set(paths)) == 2
    assert len({path.lower() for path in paths}) == 2


def test_export_redacts_secret_in_filename_suffix(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    token = "leaked-suffix-token"
    source_name = f"tile.Bearer {token}"
    relative = f"patterns/{source_name}"
    (project_dir / "patterns" / source_name).write_bytes(b"pattern-bytes")
    project.artifacts.recomposition = [relative]
    package = Exporter(project_dir).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )

    for path in package.rglob("*"):
        assert token not in path.name
        assert token not in path.relative_to(package).as_posix()
    assert token not in _package_text(package)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    dumped = json.dumps(manifest)
    assert token not in dumped
    for entry in manifest["files"]:
        assert (package / entry["path"]).is_file()


_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _assert_not_windows_reserved(filename: str) -> None:
    assert Path(filename).stem.upper() not in _WINDOWS_RESERVED_NAMES


def test_windows_reserved_source_filename_is_sanitized(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    project.source.original_filename = "CON.png"
    package = Exporter(project_dir).export(
        project,
        ExportSelection(source=True, patterns=True, report=True),
        tmp_path,
    )
    exported = list((package / "source").glob("*"))
    assert exported
    _assert_not_windows_reserved(exported[0].name)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["source"]["original_filename"] == "CON.png"


def test_windows_reserved_pattern_filename_is_sanitized(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    patterns_dir = project_dir / "patterns"
    pattern = write_image(patterns_dir / "NUL.png", image_format="PNG", size=(10, 8))
    project.artifacts.recomposition = ["patterns/NUL.png"]
    package = Exporter(project_dir).export(
        project, ExportSelection(patterns=True, report=True), tmp_path
    )
    copied = list((package / "patterns").glob("*.png"))
    assert len(copied) == 1
    _assert_not_windows_reserved(copied[0].name)
    assert copied[0].read_bytes() == pattern.read_bytes()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    paths = [item["path"] for item in manifest["files"] if item["kind"] == "pattern"]
    assert len(paths) == 1
    _assert_not_windows_reserved(Path(paths[0]).name)


def test_source_bytes_stay_identical_after_export(project, tmp_path) -> None:
    project_dir = _project_dir(tmp_path, project)
    original = (project_dir / project.source.relative_path).read_bytes()
    package = _exporter(tmp_path, project).export(
        project,
        ExportSelection(source=True, patterns=True, report=True),
        tmp_path,
    )
    assert (project_dir / project.source.relative_path).read_bytes() == original
    exported_sources = list((package / "source").glob("*"))
    assert exported_sources
    assert exported_sources[0].read_bytes() == original
