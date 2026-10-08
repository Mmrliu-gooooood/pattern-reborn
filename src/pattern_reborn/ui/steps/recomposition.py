# -*- coding: utf-8 -*-
"""Step 4 — 参数化重组: layout choice, canvas size and the persisted pattern."""

from __future__ import annotations

import streamlit as st

from pattern_reborn.domain import StepId
from pattern_reborn.limits import MAX_CANVAS_EDGE
from pattern_reborn.patterns import PatternRequest
from pattern_reborn.ui import components as ui
from pattern_reborn.ui.labels import LAYOUT_LABELS, LAYOUT_NOTES
from pattern_reborn.ui.presenters import confirmed_extraction, confirmed_step, current_patterns
from pattern_reborn.ui.steps.context import StudioContext
from pattern_reborn.workflow import WorkflowError

# Upper bound offered in the UI. Deliberately at the domain limit so the field
# can never submit a value the service will reject.
_CANVAS_MAX = min(MAX_CANVAS_EDGE, 4096)


def render(context: StudioContext) -> None:
    project = context.project
    if project is None:
        ui.render_empty_state("尚未建立项目", "请先完成分析，再生成参数化重组纹样。")
        with ui.advanced():
            st.caption("重组使用确认后的提取结果。")
        return

    project_dir = context.service.repository.project_dir(project.id)
    patterns = current_patterns(project_dir, project)
    last_request = _last_request(project)

    workbench, controls = ui.two_panel_step("recomposition")

    with workbench:
        ui.render_kicker("重组结果", "RECOMPOSED PATTERN")
        if patterns:
            ui.render_image_panel(patterns[-1], "当前重组纹样", badge="已确认")
            if len(patterns) > 1:
                ui.render_note(f"项目中共有 {len(patterns)} 个重组版本，此处显示最新一版。")
        else:
            ui.render_empty_state("尚未生成重组纹样", "在右侧选择构图方式与画布尺寸后点击「重组」。")
            extracted = confirmed_extraction(project_dir, project)
            if extracted is not None:
                ui.render_divider()
                ui.render_image_panel(extracted[1], "重组单元（提取结果）", badge="已确认")

    with controls:
        ui.render_kicker("构图参数", "COMPOSITION")
        layout_name = st.selectbox(
            "构图方式",
            list(LAYOUT_LABELS),
            index=_layout_index(last_request),
        )
        ui.render_note(LAYOUT_NOTES.get(layout_name, ""))

        size_columns = st.columns(2, gap="small")
        width = size_columns[0].number_input(
            "画布宽度",
            min_value=32,
            max_value=_CANVAS_MAX,
            value=_canvas_value(last_request, 0, 256),
            step=16,
        )
        height = size_columns[1].number_input(
            "画布高度",
            min_value=32,
            max_value=_CANVAS_MAX,
            value=_canvas_value(last_request, 1, 256),
            step=16,
        )
        ui.render_note(
            f"画布上限 {_CANVAS_MAX}×{_CANVAS_MAX} 像素；超出会被服务端拒绝。"
        )

        with ui.advanced():
            seed = st.number_input("随机种子", value=_int_value(last_request, "seed", 7), step=1)
            spacing = st.number_input(
                "间距", min_value=0, value=_int_value(last_request, "spacing", 0), step=1
            )
            scale = st.number_input(
                "缩放",
                min_value=0.1,
                max_value=20.0,
                value=_float_value(last_request, "scale", 1.0),
                step=0.1,
            )
            angle = st.number_input(
                "角度",
                min_value=-360.0,
                max_value=360.0,
                value=_float_value(last_request, "angle", 0.0),
                step=1.0,
            )
            st.caption("相同参数与随机种子会得到完全相同的排列，便于复现与溯源。")

    _render_action(
        context,
        project,
        layout_name,
        int(width),
        int(height),
        int(seed),
        int(spacing),
        float(scale),
        float(angle),
        has_result=bool(patterns),
        ready=confirmed_step(project, StepId.ANALYSIS),
    )


def _last_request(project) -> dict | None:
    raw = project.processing_parameters.get("compose")
    return raw if isinstance(raw, dict) else None


def _layout_index(last_request: dict | None) -> int:
    if last_request is None:
        return 0
    raw = last_request.get("layout")
    for index, layout in enumerate(LAYOUT_LABELS.values()):
        if layout.value == raw:
            return index
    return 0


def _canvas_value(last_request: dict | None, index: int, fallback: int) -> int:
    if last_request is None:
        return fallback
    canvas = last_request.get("canvas")
    if isinstance(canvas, list) and len(canvas) == 2:
        try:
            return max(32, min(_CANVAS_MAX, int(canvas[index])))
        except (TypeError, ValueError):
            return fallback
    return fallback


def _int_value(last_request: dict | None, key: str, fallback: int) -> int:
    if last_request is None:
        return fallback
    try:
        return int(last_request.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def _float_value(last_request: dict | None, key: str, fallback: float) -> float:
    if last_request is None:
        return fallback
    try:
        return float(last_request.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def _render_action(
    context: StudioContext,
    project,
    layout_name: str,
    width: int,
    height: int,
    seed: int,
    spacing: int,
    scale: float,
    angle: float,
    *,
    has_result: bool,
    ready: bool,
) -> None:
    note_column, action_column = ui.action_bar("recomposition")
    with note_column:
        if has_result:
            ui.render_action_note("重新重组会新增一个版本，并使已确认的生成结果转为过期。")
        elif ready:
            ui.render_action_note(f"将以「{layout_name}」生成 {width}×{height} 的重组纹样。")
        else:
            ui.render_action_note("重组需要已确认的分析结果，请先完成「纹样分析」。")
    with action_column:
        triggered = st.button("重组", type="primary", width="stretch")
    if not triggered:
        return
    try:
        context.service.compose(
            project.id,
            PatternRequest(
                layout=LAYOUT_LABELS[layout_name],
                canvas=(width, height),
                seed=seed,
                spacing=spacing,
                scale=scale,
                angle=angle,
            ),
        )
    except (WorkflowError, ValueError) as error:
        st.error(str(error))
        return
    ui.flash("重组纹样已生成并写入项目记录。")
    st.rerun()
