# -*- coding: utf-8 -*-
"""Step 3 — 纹样分析: palette, traditional-colour matches and shape metrics.

The report is read back from the confirmed ``analysis/vN.json`` artifact on
every rerun, so returning to this step never loses the previous result.
"""

from __future__ import annotations

import streamlit as st

from pattern_reborn.domain import StepId
from pattern_reborn.ui import components as ui
from pattern_reborn.ui.presenters import (
    AnalysisView,
    confirmed_extraction,
    confirmed_step,
    load_analysis,
)
from pattern_reborn.ui.steps.context import StudioContext
from pattern_reborn.workflow import WorkflowError


def render(context: StudioContext) -> None:
    project = context.project
    if project is None:
        ui.render_empty_state("尚未建立项目", "请先创建项目并确认提取结果，再进行纹样分析。")
        with ui.advanced():
            st.caption("分析使用确认后的提取结果。")
        return

    project_dir = context.service.repository.project_dir(project.id)
    view = load_analysis(project_dir, project)
    workbench, controls = ui.two_panel_step("analysis")

    with workbench:
        _render_result(workbench, context, view)

    with controls:
        ui.render_kicker("分析结果", "ANALYSIS REPORT")
        if view is None:
            ui.render_note("尚未生成分析结果。确认提取后点击下方按钮即可分析主色与轮廓特征。")
        else:
            _render_summary(view)
        with ui.advanced():
            st.caption(
                "调色板数量与阈值来自当前处理档案；分析使用固定随机种子，"
                "同一份提取结果会得到相同的配色划分。"
            )

    _render_action(context, project, view is not None, confirmed_step(project, StepId.EXTRACTION))


def _render_result(workbench, context: StudioContext, view: AnalysisView | None) -> None:
    project = context.project
    assert project is not None
    project_dir = context.service.repository.project_dir(project.id)
    extracted = confirmed_extraction(project_dir, project)
    ui.render_kicker("提取结果", "EXTRACTED ARTWORK")
    if extracted is None:
        ui.render_empty_state("尚无已确认的提取结果", "请先在「智能提取」中确认结果。")
        return
    ui.render_image_panel(extracted[1], "分析对象", badge="已确认")
    if view is not None:
        ui.render_note(
            "主色为 k-means 聚类中心，覆盖率为该色在全部不透明像素中的实测占比；"
            "传统色为 CIE-Lab 空间中的最近邻匹配。"
        )


def _render_summary(view: AnalysisView) -> None:
    contours = view.contours
    symmetry = view.symmetry
    ui.render_metric_grid(
        [
            (
                "轮廓数量",
                f"{int(contours.get('contour_count') or 0)}",
                f"孔洞 {int(contours.get('hole_count') or 0)} · 周长 {float(contours.get('total_perimeter') or 0):.0f}",
            ),
            (
                "前景占比",
                f"{float(contours.get('foreground_ratio') or 0):.1%}",
                f"前景像素 {int(contours.get('foreground_area') or 0)}",
            ),
            (
                "复杂度",
                f"{float(contours.get('complexity') or 0):.2f}",
                "周长平方与面积之比",
            ),
            (
                "垂直对称",
                f"{float(symmetry.get('vertical_score') or 0):.2f}",
                "左右镜像 IoU",
            ),
            (
                "水平对称",
                f"{float(symmetry.get('horizontal_score') or 0):.2f}",
                "上下镜像 IoU",
            ),
        ]
    )
    ui.render_kicker("主色板", "DOMINANT PALETTE")
    ui.render_palette(view.palette)
    ui.render_kicker("传统色匹配", "TRADITIONAL COLOUR MATCH")
    ui.render_color_matches(view.color_matches)
    rotations = symmetry.get("rotations") or []
    if isinstance(rotations, list) and rotations:
        best = max(
            (item for item in rotations if isinstance(item, dict)),
            key=lambda item: float(item.get("score") or 0),
            default=None,
        )
        if best is not None:
            ui.render_note(
                f"旋转对称最佳阶数 {int(best.get('order') or 0)}，"
                f"IoU {float(best.get('score') or 0):.2f}。"
            )


def _render_action(context: StudioContext, project, has_result: bool, ready: bool) -> None:
    note_column, action_column = ui.action_bar("analysis")
    with note_column:
        if has_result:
            ui.render_action_note("重新分析会覆盖当前记录，并使后续重组与生成结果转为过期。")
        elif ready:
            ui.render_action_note("分析将读取已确认的提取结果，并写入新的分析记录。")
        else:
            ui.render_action_note("分析需要已确认的提取结果，请先完成「智能提取」并确认。")
    with action_column:
        label = "重新分析" if has_result else "分析"
        triggered = st.button(label, type="primary", width="stretch")
    if not triggered:
        return
    try:
        context.service.analyze(project.id)
    except WorkflowError as error:
        st.error(str(error))
        return
    ui.flash("分析完成，结果已写入项目记录。")
    st.rerun()
