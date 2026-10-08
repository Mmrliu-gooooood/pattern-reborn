# -*- coding: utf-8 -*-
"""Read-only views over persisted project state.

Streamlit reruns the whole script on every interaction, so a result rendered
only inside a button branch disappears as soon as anything else is touched.
These helpers let each step rebuild its result panels from the project record on
*every* rerun, independently of which button fired.

Deliberately free of Streamlit imports so the readers stay unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from pattern_reborn.domain import ProjectRecord, StepId
from pattern_reborn.ui.labels import is_ai_artwork


@dataclass(frozen=True, slots=True)
class AnalysisView:
    """Validated contents of a confirmed ``analysis/vN.json`` artifact."""

    palette: list[dict[str, object]]
    color_matches: list[dict[str, object]]
    contours: dict[str, object]
    symmetry: dict[str, object]
    algorithm: str
    profile: str


@dataclass(frozen=True, slots=True)
class ArtworkView:
    """One selectable recomposition or AI-generated artifact."""

    artifact_id: str
    path: Path
    ai_assisted: bool


@dataclass(frozen=True, slots=True)
class GenerationView:
    """A confirmed, non-stale generation record with usable provider metadata."""

    artifact_id: str
    path: Path
    provider: str
    model: str
    prompt: str
    created_at: str


def artifact_path(project_dir: Path, artifact_id: object) -> Path | None:
    """Resolve a project-relative artifact id, rejecting traversal and misses."""
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        return None
    relative = Path(artifact_id)
    if relative.is_absolute():
        return None
    try:
        resolved = (project_dir / relative).resolve()
        root = project_dir.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root) or not resolved.is_file():
        return None
    return resolved


def source_path(project_dir: Path, project: ProjectRecord) -> Path | None:
    return artifact_path(project_dir, project.source.relative_path)


def pending_extraction(project_dir: Path, project: ProjectRecord) -> tuple[str, Path] | None:
    """Unconfirmed extraction waiting for the user's explicit confirmation."""
    pending = project.processing_parameters.get("pending_extraction")
    if not isinstance(pending, dict):
        return None
    artifact_id = pending.get("artifact_id")
    path = artifact_path(project_dir, artifact_id)
    if path is None:
        return None
    return str(artifact_id), path


def confirmed_extraction(project_dir: Path, project: ProjectRecord) -> tuple[str, Path] | None:
    """Confirmed extracted artwork, ignoring anything marked stale."""
    stale = set(project.stale_artifacts)
    for artifact_id in project.artifacts.extraction:
        if artifact_id in stale or not artifact_id.startswith("extracted/"):
            continue
        if not artifact_id.lower().endswith(".png"):
            continue
        path = artifact_path(project_dir, artifact_id)
        if path is not None:
            return artifact_id, path
    return None


def confirmed_mask(project_dir: Path, project: ProjectRecord) -> Path | None:
    stale = set(project.stale_artifacts)
    for artifact_id in project.artifacts.extraction:
        if artifact_id in stale or not artifact_id.startswith("masks/"):
            continue
        path = artifact_path(project_dir, artifact_id)
        if path is not None:
            return path
    return None


def load_analysis(project_dir: Path, project: ProjectRecord) -> AnalysisView | None:
    """Read the newest confirmed analysis artifact, or ``None`` if unusable.

    A malformed or missing artifact degrades to the empty state instead of
    raising, because this runs on every rerun of the analysis step.
    """
    stale = set(project.stale_artifacts)
    for artifact_id in reversed(list(project.artifacts.analysis)):
        if artifact_id in stale:
            continue
        path = artifact_path(project_dir, artifact_id)
        if path is None:
            continue
        view = _read_analysis(path)
        if view is not None:
            return view
    return None


def _read_analysis(path: Path) -> AnalysisView | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    palette, matches = payload.get("palette"), payload.get("color_matches")
    contours, symmetry = payload.get("contours"), payload.get("symmetry")
    if not isinstance(palette, list) or not isinstance(matches, list):
        return None
    if not isinstance(contours, dict) or not isinstance(symmetry, dict):
        return None
    return AnalysisView(
        palette=[item for item in palette if isinstance(item, dict)],
        color_matches=[item for item in matches if isinstance(item, dict)],
        contours=dict(contours),
        symmetry=dict(symmetry),
        algorithm=str(payload.get("algorithm") or ""),
        profile=str(payload.get("profile") or ""),
    )


def current_artworks(project_dir: Path, project: ProjectRecord) -> list[ArtworkView]:
    """Confirmed, non-stale recomposition and generation outputs, newest last.

    This is the single eligibility rule shared by the mockup and export steps;
    it mirrors ``workflow._current_mockup_artwork_ids``.
    """
    stale = set(project.stale_artifacts)
    ordered: list[str] = []
    for artifact_id in (*project.artifacts.recomposition, *project.artifacts.generation):
        if artifact_id not in stale and artifact_id not in ordered:
            ordered.append(artifact_id)
    for record in project.generations:
        if record.artifact_path not in stale and record.artifact_path not in ordered:
            ordered.append(record.artifact_path)
    views: list[ArtworkView] = []
    for artifact_id in ordered:
        path = artifact_path(project_dir, artifact_id)
        if path is None:
            continue
        views.append(
            ArtworkView(
                artifact_id=artifact_id,
                path=path,
                ai_assisted=is_ai_artwork(artifact_id),
            )
        )
    return views


def current_patterns(project_dir: Path, project: ProjectRecord) -> list[Path]:
    stale = set(project.stale_artifacts)
    paths: list[Path] = []
    for artifact_id in project.artifacts.recomposition:
        if artifact_id in stale or not artifact_id.startswith("patterns/"):
            continue
        if not artifact_id.lower().endswith(".png"):
            continue
        path = artifact_path(project_dir, artifact_id)
        if path is not None:
            paths.append(path)
    return paths


def current_generations(project_dir: Path, project: ProjectRecord) -> list[GenerationView]:
    """Newest-first confirmed generations, with the metadata shown to the user."""
    stale = set(project.stale_artifacts)
    views: list[GenerationView] = []
    for record in reversed(project.generations):
        if record.artifact_path in stale:
            continue
        path = artifact_path(project_dir, record.artifact_path)
        if path is None:
            continue
        views.append(
            GenerationView(
                artifact_id=record.artifact_path,
                path=path,
                provider=str(getattr(record.provider, "value", record.provider)),
                model=record.model,
                prompt=record.prompt,
                created_at=record.created_at.strftime("%Y.%m.%d %H:%M"),
            )
        )
    return views


def current_mockups(project_dir: Path, project: ProjectRecord) -> list[Path]:
    """Mockup PNGs published since the last export confirmation."""
    raw = project.processing_parameters.get("current_mockups")
    if not isinstance(raw, list):
        return []
    stale = set(project.stale_artifacts)
    paths: list[Path] = []
    for artifact_id in raw:
        if not isinstance(artifact_id, str) or artifact_id in stale:
            continue
        path = artifact_path(project_dir, artifact_id)
        if path is not None:
            paths.append(path)
    return paths


def confirmed_step(project: ProjectRecord, step: StepId) -> bool:
    return step in project.confirmed_steps
