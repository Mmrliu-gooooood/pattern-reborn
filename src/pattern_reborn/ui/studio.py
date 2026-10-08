# -*- coding: utf-8 -*-
"""Studio router: sidebar step rail, shared header, and step dispatch.

Each step lives in ``pattern_reborn.ui.steps``; this module owns only the shell,
the step/session-state contract, and the dispatch table.
"""

from __future__ import annotations

import streamlit as st

from pattern_reborn.capabilities import Capabilities
from pattern_reborn.config import ProviderConfig
from pattern_reborn.domain import ProjectRecord, StepId
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.ui import components as ui
from pattern_reborn.ui.canvas import hints_from_canvas_objects  # noqa: F401  (public re-export)
from pattern_reborn.ui.labels import (
    LABEL_BY_STEP,
    STEP_BY_LABEL,
    STEP_LABELS,
    current_step_of,
    step_label,
)
from pattern_reborn.ui.steps import (
    analysis as analysis_step,
    export as export_step,
    extraction as extraction_step,
    generation as generation_step,
    recomposition as recomposition_step,
    source as source_step,
)
from pattern_reborn.ui.steps.context import StudioContext
from pattern_reborn.ui.theme import render_sidebar_footer, render_step_rail
from pattern_reborn.workflow import PatternRebornService

STEP_RENDERERS = {
    StepId.UPLOAD: source_step.render,
    StepId.EXTRACTION: extraction_step.render,
    StepId.ANALYSIS: analysis_step.render,
    StepId.RECOMPOSITION: recomposition_step.render,
    StepId.GENERATION: generation_step.render,
    StepId.EXPORT: export_step.render,
}

# Session keys that belong to the active project and must not survive leaving it.
_CLEARED_ON_EXIT = (
    "project_id",
    "studio_step",
    "byok_secret",
    "gen_byok_input",
    "canvas_objects",
    "mask_strokes",
    "unsaved",
    "generation_confirm_pending",
)


def render_studio(
    service: PatternRebornService,
    knowledge: KnowledgeCatalog,
    capabilities: Capabilities,
    provider_config: ProviderConfig,
) -> None:
    project = _load_current_project(service)
    _ensure_step_state(project)

    with st.sidebar:
        render_step_rail(str(st.session_state.get("studio_step", STEP_LABELS[0])))
        render_sidebar_footer()
        if st.button("返回首页", key="return-home", width="stretch"):
            _exit_to_home()

    step = STEP_BY_LABEL.get(st.session_state.get("studio_step", STEP_LABELS[0]), StepId.UPLOAD)
    ui.render_step_header(step, project.name if project is not None else None)

    if project is not None:
        service.save_navigation_state(project.id, step)
    ui.render_flash()

    context = StudioContext(
        service=service,
        project=project,
        knowledge=knowledge,
        capabilities=capabilities,
        provider_config=provider_config,
    )
    STEP_RENDERERS[step](context)


def _exit_to_home() -> None:
    st.session_state["route"] = "home"
    for key in _CLEARED_ON_EXIT:
        st.session_state.pop(key, None)
    st.rerun()


def _ensure_step_state(project: ProjectRecord | None) -> None:
    """Seed the step radio from the persisted project, once per session."""
    if st.session_state.get("studio_step") in STEP_LABELS:
        return
    if project is not None:
        st.session_state["studio_step"] = step_label(current_step_of(project))
        return
    st.session_state["studio_step"] = STEP_LABELS[0]


def _load_current_project(service: PatternRebornService) -> ProjectRecord | None:
    project_id = st.session_state.get("project_id")
    if not project_id:
        return None
    try:
        return service.load_project(str(project_id))
    except Exception:
        st.session_state.pop("project_id", None)
        st.error("无法加载项目。")
        return None


__all__ = [
    "LABEL_BY_STEP",
    "STEP_BY_LABEL",
    "STEP_LABELS",
    "STEP_RENDERERS",
    "hints_from_canvas_objects",
    "render_studio",
]
