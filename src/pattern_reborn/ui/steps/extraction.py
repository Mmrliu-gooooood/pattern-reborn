# -*- coding: utf-8 -*-
"""Step 2 — 智能提取: bounded source/result workbench and extraction controls."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from pattern_reborn.domain import ProfileId
from pattern_reborn.segmentation import MaskEditMode, MaskStroke, SegmentHints
from pattern_reborn.ui import canvas as canvas_support
from pattern_reborn.ui import components as ui
from pattern_reborn.ui.presenters import (
    confirmed_extraction,
    confirmed_mask,
    pending_extraction,
    source_path,
)
from pattern_reborn.ui.steps.context import StudioContext
from pattern_reborn.workflow import ExtractCommand, SegmentationBackend, WorkflowError

_BACKEND_LABELS = {"OpenCV": SegmentationBackend.OPENCV, "MobileSAM": SegmentationBackend.MOBILE_SAM}
_STROKE_WIDTH_KEY = "extraction_stroke_width"


@dataclass(frozen=True, slots=True)
class _Controls:
    """Widget values needed to build an :class:`ExtractCommand`."""

    box: tuple[int, int, int, int] | None
    points: tuple
    profile: ProfileId
    backend: SegmentationBackend


def render(context: StudioContext) -> None:
    project = context.project
    if project is None:
        ui.render_empty_state("尚未建立项目", "请先在「上传与分类」中创建项目，再进行轮廓提取。")
        with ui.advanced():
            st.caption("提取默认使用品类对应的处理档案。")
        return

    project_dir = context.service.repository.project_dir(project.id)
    source = source_path(project_dir, project)
    pending = pending_extraction(project_dir, project)
    confirmed = confirmed_extraction(project_dir, project)
    canvas_active = context.capabilities.canvas.available

    workbench, controls = ui.two_panel_step("extraction")

    with workbench:
        if pending is not None:
            _render_comparison(source, pending[1], badge="待确认")
            ui.render_note("结果尚未确认。确认后才会写入项目记录，并作为分析与生成的输入。")
        else:
            if confirmed is not None:
                _render_comparison(
                    source,
                    confirmed[1],
                    badge="已确认",
                    mask=confirmed_mask(project_dir, project),
                )
                ui.render_note("该结果已确认并写入项目记录。重新提取会替换它，并使后续结果转为过期。")
            else:
                ui.render_kicker("源图与画布", "SOURCE WORKBENCH")
                if source is not None:
                    ui.render_image_panel(source, "原始来源")
                else:
                    ui.render_empty_state("来源图像不可用", "项目记录的源文件缺失或已被移动。")
            # The canvas stays available after confirmation so the result can be
            # refined without losing the confirmed artifact first.
            if canvas_active:
                ui.render_divider()
                canvas_support.render_canvas(context.capabilities, source)

    with controls:
        values = _render_controls(context, project, canvas_active)

    if pending is not None:
        _render_confirm_action(context, project, pending[0])
        return
    _render_extract_action(context, project, values)


def _render_comparison(source, result, badge: str, mask=None) -> None:
    """Side-by-side source/result panels with consistent aspect treatment.

    The binary mask joins as a third panel once it exists, because it is the
    only view that explains why a region was kept or dropped.
    """
    ui.render_kicker("提取结果对照", "SOURCE / RESULT")
    columns = st.columns(3 if mask is not None else 2, gap="medium")
    if source is None:
        with columns[0]:
            ui.render_empty_state("来源图像不可用", "项目记录的源文件缺失或已被移动。")
    else:
        with columns[0]:
            ui.render_image_panel(source, "原始来源")
    with columns[1]:
        ui.render_image_panel(result, "提取结果", badge=badge)
    if mask is not None:
        with columns[2]:
            ui.render_image_panel(mask, "提取蒙版", badge="黑白")


def _render_controls(context: StudioContext, project, canvas_active: bool) -> _Controls:
    ui.render_kicker("提取参数", "EXTRACTION CONTROLS")
    if canvas_active:
        ui.render_note("在左侧画布上点选、框选或涂抹；下方坐标可精确指定范围。")
    else:
        st.warning(canvas_support.CANVAS_FALLBACK_ZH)
        ui.render_note("请用下方坐标框选主体范围，或用提示点标记需要保留/删除的位置。")

    st.radio("笔触模式", ["保留", "删除"], key="stroke_mode", horizontal=True)
    stroke_row = st.columns([2.2, 1.0], gap="small")
    with stroke_row[0]:
        stroke_coords = st.text_input("笔触坐标", placeholder="x,y;x,y")
    with stroke_row[1]:
        # Aligns the button with the input, whose label occupies the row above.
        st.markdown('<div class="field-spacer"></div>', unsafe_allow_html=True)
        add_stroke = st.button("添加笔触", width="stretch")
    if add_stroke:
        if stroke_coords.strip():
            _add_stroke(stroke_coords)
        else:
            st.error("请先填写笔触坐标，例如 x,y;x,y。")
    stroke_count = len(st.session_state.get("mask_strokes") or [])
    if stroke_count:
        ui.render_note(f"已记录 {stroke_count} 条笔触，将在提取时一并应用。")

    ui.render_divider()
    ui.render_kicker("手动坐标", "MANUAL GEOMETRY")
    recorded = _recorded_region_note(project)
    if recorded:
        ui.render_note(recorded)
    box, points = _render_coordinate_inputs()

    profile_names = {profile.display_name_zh: profile.id for profile in context.knowledge.profiles}
    default_profile = context.knowledge.profile_for(project.category)
    profile_index = list(profile_names.values()).index(default_profile.id)
    profile_name = default_profile.display_name_zh
    backend = SegmentationBackend.OPENCV
    with ui.advanced():
        st.number_input("笔触宽度", min_value=1, value=3, step=1, key=_STROKE_WIDTH_KEY)
        profile_name = st.selectbox("处理档案", list(profile_names), index=profile_index)
        backend = _render_backend_selector(context)
        st.caption(
            f"当前档案 · {default_profile.display_name_zh}；"
            f"{_backend_caption(context)}档案决定阈值、形态学与调色板默认值。"
        )

    return _Controls(
        box=box,
        points=points,
        profile=profile_names[profile_name],
        backend=backend,
    )


def _recorded_region_note(project) -> str:
    """Say that a documented region will be used, so the result is never a surprise."""
    box = project.processing_parameters.get("hint_box")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return ""
    left, top, right, bottom = (float(value) for value in box)
    return (
        f"已载入本案例记录的提取区域（横向 {left:.0%}–{right:.0%}、"
        f"纵向 {top:.0%}–{bottom:.0%}）。填写下方坐标或在画布上框选即可覆盖它。"
    )


def _render_coordinate_inputs() -> tuple[tuple[int, int, int, int] | None, tuple]:
    """Manual geometry, grouped as start corner / end corner / hint point."""
    start = st.columns(2, gap="small")
    left = start[0].number_input("框选左", min_value=0, value=0, step=1)
    top = start[1].number_input("框选上", min_value=0, value=0, step=1)
    end = st.columns(2, gap="small")
    right = end[0].number_input("框选右", min_value=0, value=0, step=1)
    bottom = end[1].number_input("框选下", min_value=0, value=0, step=1)
    hint = st.columns(2, gap="small")
    point_x = hint[0].number_input("提示点 X", min_value=0, value=0, step=1)
    point_y = hint[1].number_input("提示点 Y", min_value=0, value=0, step=1)
    keep_point = st.checkbox("提示点保留", value=True)
    box = (int(left), int(top), int(right), int(bottom)) if right > left and bottom > top else None
    return box, canvas_support.manual_prompt_points(point_x, point_y, keep_point)


def _backend_caption(context: StudioContext) -> str:
    if context.capabilities.mobile_sam.available and context.service.has_mobile_sam_segmenter:
        return "分割后端可选 OpenCV 基线或 MobileSAM；未调用 MobileSAM 时不会加载其权重。"
    return "MobileSAM 当前不可用，已回退为 OpenCV 基线；框选与提示点仍可辅助提取。"


def _render_backend_selector(context: StudioContext) -> SegmentationBackend:
    if context.capabilities.mobile_sam.available and context.service.has_mobile_sam_segmenter:
        return _BACKEND_LABELS[st.selectbox("分割后端", list(_BACKEND_LABELS))]
    return SegmentationBackend.OPENCV


def _add_stroke(stroke_coords: str) -> None:
    try:
        parsed = canvas_support.parse_stroke_points(stroke_coords)
    except (ValueError, WorkflowError) as error:
        st.error(str(error))
        return
    mode = MaskEditMode.KEEP if st.session_state.get("stroke_mode") == "保留" else MaskEditMode.REMOVE
    width = int(st.session_state.get(_STROKE_WIDTH_KEY) or 3)
    strokes = list(st.session_state.get("mask_strokes") or [])
    strokes.append(MaskStroke(mode=mode, points=parsed, width=max(1, width)))
    st.session_state["mask_strokes"] = strokes
    st.success("已记录笔触。")


def _collect_hints(box: tuple[int, int, int, int] | None, points: tuple) -> tuple[SegmentHints, list[MaskStroke]]:
    canvas_hints, canvas_strokes = canvas_support.hints_from_canvas_objects(
        st.session_state.get("canvas_objects")
    )
    resolved_box = canvas_hints.box if canvas_hints.box is not None else box
    resolved_points = tuple(canvas_hints.points) + tuple(points)
    strokes = canvas_strokes + list(st.session_state.get("mask_strokes") or [])
    return SegmentHints(box=resolved_box, points=resolved_points), strokes


def _render_extract_action(context: StudioContext, project, values: _Controls) -> None:
    note_column, action_column = ui.action_bar("extraction")
    with note_column:
        ui.render_action_note("提取结果先进入待确认状态；确认后才写入项目记录并解锁后续步骤。")
    with action_column:
        triggered = st.button("提取", type="primary", width="stretch")
    if not triggered:
        return
    try:
        hints, strokes = _collect_hints(values.box, values.points)
        result = context.service.extract(
            project.id,
            ExtractCommand(
                profile=values.profile,
                backend=values.backend,
                hints=hints,
                strokes=strokes,
            ),
        )
    except (WorkflowError, ValueError) as error:
        st.error(str(error))
        return
    ui.flash(f"提取完成：{result.artifact_id}。请确认后进入下一步。")
    st.rerun()


def _render_confirm_action(context: StudioContext, project, artifact_id: str) -> None:
    note_column, action_column = ui.action_bar("extraction-confirm")
    with note_column:
        ui.render_action_note("确认后提取结果将写入项目记录，并解锁纹样分析。")
    with action_column:
        triggered = st.button("确认提取", type="primary", width="stretch")
    if not triggered:
        return
    try:
        context.service.confirm_extraction(project.id, artifact_id)
    except WorkflowError as error:
        st.error(str(error))
        return
    st.session_state.pop("mask_strokes", None)
    st.session_state.pop("canvas_objects", None)
    ui.flash("已确认提取结果。")
    st.rerun()
