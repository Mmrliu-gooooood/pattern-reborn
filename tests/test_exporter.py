# -*- coding: utf-8 -*-
from datetime import UTC, datetime
import json
from pathlib import Path
import re

import pytest

from pattern_reborn.domain import CategoryId, GenerationRecord, ProvenanceClass
from pattern_reborn.exporter import Exporter, ExportSelection
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
    pattern = write_image(project_dir / "patterns" / "repeat.png", image_format="PNG", size=(10, 8))
    generated = write_image(project_dir / "generated" / "seedream.png", image_format="PNG", size=(10, 8))
    record.source.relative_path = str((project_dir / record.source.relative_path).resolve())
    record.artifacts.recomposition = [str(pattern.resolve())]
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
            artifact_path=str(generated.resolve()),
            created_at=datetime(2026, 8, 29, 10, 15, tzinfo=UTC),
        )
    ]
    return record


def _project_dir(project) -> Path:
    return Path(project.source.relative_path).resolve().parent.parent


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
    package = Exporter().export(project, ExportSelection(patterns=True, report=True), tmp_path)
    assert (package / "manifest.json").exists()
    report = (package / "provenance.md").read_text(encoding="utf-8")
    assert project.source.sha256 in report
    assert "AI 辅助" in report
    assert (package / "attribution.md").exists()
    copied = list((package / "patterns").glob("*.png"))
    assert copied
    assert copied[0].read_bytes() == Path(project.artifacts.recomposition[0]).read_bytes()


def test_export_paths_stay_under_destination_root(project, tmp_path) -> None:
    destination = tmp_path / "exports"
    package = Exporter().export(project, ExportSelection(patterns=True, report=True), destination)
    root = destination.resolve()
    assert package.resolve().is_relative_to(root)
    for path in package.rglob("*"):
        assert path.resolve().is_relative_to(root)


def test_export_omits_secret_shaped_fields(project, tmp_path) -> None:
    package = Exporter().export(project, ExportSelection(patterns=True, report=True), tmp_path)
    blob = _package_text(package)
    for marker in _SECRET_MARKERS:
        assert marker not in blob
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    dumped = json.dumps(manifest)
    for marker in _SECRET_MARKERS:
        assert marker not in dumped


def test_attribution_names_team_templates_and_source(project, tmp_path) -> None:
    package = Exporter().export(project, ExportSelection(patterns=True, report=True), tmp_path)
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
    unsafe_pattern = write_image(
        project_dir / "patterns" / "ok.png",
        image_format="PNG",
        size=(8, 8),
    )
    record.source.relative_path = str((project_dir / record.source.relative_path).resolve())
    record.artifacts.recomposition = [str(unsafe_pattern.resolve())]
    destination = tmp_path / "out"
    package = Exporter().export(record, ExportSelection(patterns=True, report=True), destination)

    assert package.parent.resolve() == destination.resolve()
    assert ".." not in package.name
    assert not re.search(r'[<>:"/\\|?*]', package.name)
    for path in package.rglob("*"):
        assert path.resolve().is_relative_to(destination.resolve())
        if path.is_file():
            assert not re.search(r'[<>:"/\\|?*]', path.name)


def test_manifest_schema_is_versioned_and_stable(project, tmp_path) -> None:
    package = Exporter().export(project, ExportSelection(patterns=True, report=True), tmp_path)
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


def test_export_copies_contained_mockup_png_as_ai_assisted(project, tmp_path) -> None:
    project_dir = _project_dir(project)
    mockups_dir = project_dir / "mockups"
    mockups_dir.mkdir()
    mockup = write_image(mockups_dir / "bookmark.png", image_format="PNG", size=(12, 8))
    outside = write_image(project_dir / "outside.png", image_format="PNG", size=(8, 8))
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
    for path in package.rglob("*"):
        assert path.resolve().is_relative_to(destination.resolve())
        assert ".." not in path.relative_to(destination).as_posix()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    mockup_entries = [item for item in manifest["files"] if item["kind"] == "mockup"]
    assert len(mockup_entries) == 1
    assert mockup_entries[0]["ai_assisted"] is True
    assert mockup_entries[0]["path"].startswith("mockups/")
    assert ".." not in mockup_entries[0]["path"]


def test_export_omits_mockups_when_not_selected(project, tmp_path) -> None:
    project_dir = _project_dir(project)
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
    package = Exporter().export(project, ExportSelection(patterns=True, report=True), tmp_path)
    blob = _package_text(package)
    for marker in ("Bearer", "sk-secret-value", "api_key"):
        assert marker not in blob
    report = (package / "provenance.md").read_text(encoding="utf-8")
    assert "seedream" in report
    assert "seedream-4.5" in report
    assert "2026-08-29T10:15:00Z" in report
    assert "AI 辅助" in report


def test_sanitized_pattern_basename_collisions_stay_unique(project, tmp_path) -> None:
    project_dir = _project_dir(project)
    patterns_dir = project_dir / "patterns"
    first = write_image(patterns_dir / "ok.png", image_format="PNG", size=(10, 8))
    second = write_image(patterns_dir / "ok..png", image_format="PNG", size=(12, 8))
    project.artifacts.recomposition = [str(first.resolve()), str(second.resolve())]
    package = Exporter().export(project, ExportSelection(patterns=True, report=True), tmp_path)

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


def test_source_bytes_stay_identical_after_export(project, tmp_path) -> None:
    original = Path(project.source.relative_path).read_bytes()
    package = Exporter().export(
        project,
        ExportSelection(source=True, patterns=True, report=True),
        tmp_path,
    )
    assert Path(project.source.relative_path).read_bytes() == original
    exported_sources = list((package / "source").glob("*"))
    assert exported_sources
    assert exported_sources[0].read_bytes() == original
