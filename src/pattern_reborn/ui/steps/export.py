# -*- coding: utf-8 -*-
"""Step 6 — 导出与溯源: mockup gallery and the provenance export package."""

from __future__ import annotations

import streamlit as st

from pattern_reborn.exporter import ExportSelection
from pattern_reborn.ui import components as ui
from pattern_reborn.ui.labels import (
    artwork_label,
    mockup_template_label,
    mockup_templates,
)
from pattern_reborn.ui.presenters import current_artworks, current_generations, current_mockups
from pattern_reborn.ui.steps.context import StudioContext
from pattern_reborn.workflow import WorkflowError

_EXPORT_FIELDS = (
    ("source", "导出原图"),
    ("extracted", "导出提取"),
    ("patterns", "导出重组"),
    ("generations", "导出生成"),
    ("mockups", "导出贴图"),
    ("svg", "导出 SVG"),
    ("report", "导出报告"),
)


def render(context: StudioContext) -> None:
    project = context.project
    if project is None:
        ui.render_empty_state("尚未建立项目", "请先完成前面步骤，再导出溯源包。")
        with ui.advanced():
            st.caption("导出打包已确认的本地成果。")
        return

    project_dir = context.service.repository.project_dir(project.id)
    artworks = current_artworks(project_dir, project)
    generations = current_generations(project_dir, project)
    mockups = current_mockups(project_dir, project)

    workbench, controls = ui.two_panel_step("export")

    with workbench:
        ui.render_kicker("当前成果", "CURRENT ARTWORKS")
        if mockups:
            ui.render_image_panel(mockups[-1], "最新贴图", badge="已生成")
        if generations:
            for record in generations:
                ui.render_image_panel(record.path, f"{record.provider} · {record.model}", badge="AI 生成")
        if not artworks:
            ui.render_empty_state(
                "尚无可导出的纹样",
                "请先在「参数化重组」中生成纹样，或在「AI 创意生成」中得到结果。",
            )

    with controls:
        selection = _render_controls(context, project, artworks, generations)
    _render_action(context, project, selection)


def _render_controls(context: StudioContext, project, artworks, generations) -> ExportSelection:
    ui.render_kicker("贴图与导出", "MOCKUP & EXPORT")

    templates = mockup_templates()
    template_label = st.selectbox("贴图模板", list(templates)) if templates else None
    choices = {artwork_label(item.artifact_id): item for item in artworks}
    artwork_label_value = st.selectbox("贴图纹样", list(choices)) if choices else None

    mockup_row = st.columns([1.4, 1.0], gap="small")
    with mockup_row[0]:
        ui.render_note("贴图使用项目自带的模板资产，模板版权为 project-original。")
    with mockup_row[1]:
        mockup_ready = template_label is not None and artwork_label_value is not None
        if st.button("生成贴图", width="stretch", disabled=not mockup_ready):
            _make_mockup(context, project, templates[template_label], choices[artwork_label_value])

    if generations:
        ui.render_divider()
        ui.render_kicker("生成记录", "GENERATION HISTORY")
        for record in generations:
            ui.render_note(
                f"{record.provider} · {record.model} · {record.created_at} · {record.artifact_id}"
            )

    with ui.advanced():
        ui.render_note("选择要打包的内容；导出包始终包含清单与署名信息。")
        columns = st.columns(2, gap="small")
        flags: dict[str, bool] = {}
        for index, (field, label) in enumerate(_EXPORT_FIELDS):
            with columns[index % 2]:
                flags[field] = st.checkbox(label, value=True, key=f"export-{field}")
    return ExportSelection(**flags)


def _make_mockup(context: StudioContext, project, template_id: str, artwork) -> None:
    try:
        result = context.service.make_mockup(project.id, template_id, artwork.artifact_id)
    except WorkflowError as error:
        st.error(str(error))
        return
    badge = "AI 辅助" if artwork.ai_assisted else "贴图"
    ui.render_image_panel(result.path, f"新贴图 · {mockup_template_label(template_id)}", badge=badge)


def _render_action(context: StudioContext, project, selection: ExportSelection) -> None:
    note_column, action_column = ui.action_bar("export")
    with note_column:
        ui.render_action_note(
            "导出包写入 <b>outputs/</b> 下的时间戳目录，包含清单、署名与可选的溯源报告。"
        )
    with action_column:
        triggered = st.button("导出", type="primary", width="stretch")
    if not triggered:
        return
    try:
        package = context.service.export(project.id, selection)
    except WorkflowError as error:
        st.error(str(error))
        return
    ui.flash(f"已导出到 {package}")
    st.rerun()
