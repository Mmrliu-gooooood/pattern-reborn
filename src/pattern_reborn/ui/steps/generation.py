# -*- coding: utf-8 -*-
"""Step 5 — AI 创意生成: provider/mode selection and a persisted result gallery."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from pydantic import SecretStr

from pattern_reborn.generation.base import CredentialMode, GenerationFailure, GenerationRequest
from pattern_reborn.ui import components as ui
from pattern_reborn.ui.labels import (
    MODE_LABELS,
    PROVIDER_LABELS,
    STRUCTURE_LABELS,
    TARGET_LABELS,
)
from pattern_reborn.ui.presenters import confirmed_extraction, current_generations
from pattern_reborn.ui.steps.context import StudioContext
from pattern_reborn.workflow import WorkflowError

_BYOK_KEY = "gen_byok_input"
_SAVED_KEYS = (
    "gen_prompt",
    "gen_size",
    "gen_structure",
    "gen_target",
    "gen_colors",
    "gen_negative",
    "gen_provider",
    "gen_mode",
)


def render(context: StudioContext) -> None:
    project = context.project
    if project is None:
        ui.render_empty_state("尚未建立项目", "请先创建项目并确认提取结果，再进行创意生成。")
        with ui.advanced():
            st.caption("生成需要已确认的提取参考图。")
        return

    _restore_draft()
    if context.capabilities.offline:
        st.info("当前离线探测未通过，仍可尝试生成；若接口不可达将在确认后提示。")

    project_dir = context.service.repository.project_dir(project.id)
    extracted = confirmed_extraction(project_dir, project)
    generations = current_generations(project_dir, project)

    workbench, controls = ui.two_panel_step("generation")

    with workbench:
        ui.render_kicker("参考图", "REFERENCE ARTWORK")
        if extracted is None:
            ui.render_empty_state("尚无可用的参考图", "请先在「智能提取」中确认提取结果。")
        else:
            ui.render_image_panel(extracted[1], "生成参考（已确认提取）", badge="已确认")
        if generations:
            ui.render_divider()
            ui.render_kicker("已生成结果", "GENERATED RESULTS")
            for record in generations:
                ui.render_image_panel(
                    record.path,
                    f"{record.provider} · {record.model}",
                    badge="AI 生成",
                )
                st.markdown(
                    f'<div class="result-caption">{ui.escape(record.prompt)} · '
                    f"{ui.escape(record.created_at)}</div>",
                    unsafe_allow_html=True,
                )

    with controls:
        values = _render_controls(context)
        pending = bool(st.session_state.get("generation_confirm_pending"))
        if pending:
            _render_confirmation_panel(values)
        label = "确认生成" if pending else "生成"
        if st.button(label, type="primary", width="stretch"):
            if pending:
                _dispatch(context, project, extracted[0] if extracted else None, values)
            elif extracted is None:
                st.error("请先确认提取结果后再生成。")
            else:
                st.session_state["generation_confirm_pending"] = True
                st.rerun()

    _capture_draft()


def _render_controls(context: StudioContext) -> dict:
    ui.render_kicker("生成参数", "GENERATION CONTROLS")
    provider_label = st.radio("生图模型", list(PROVIDER_LABELS), key="gen_provider")
    ui.render_note("两家提供商均保持可用，不会自动切换；切换后提示词等中性字段会保留。")

    mode_label = st.radio("凭证方式", list(MODE_LABELS), key="gen_mode", horizontal=True)
    if mode_label == "自带密钥":
        entered = st.text_input("访问密钥", type="password", key=_BYOK_KEY)
        if entered:
            st.session_state["byok_secret"] = SecretStr(entered)
        ui.render_note("自带密钥仅保存在本次会话内存中，不会写入项目记录或导出包。")

    st.text_area("提示词", key="gen_prompt", height=120)

    provider_id = PROVIDER_LABELS[str(provider_label)]
    settings = context.provider_config.provider(provider_id)
    size_options = list(settings.size_options)
    if "gen_size" not in st.session_state:
        st.session_state["gen_size"] = "1024x1024" if "1024x1024" in size_options else size_options[0]
    current_size = st.session_state.get("gen_size")
    if isinstance(current_size, str) and current_size not in size_options:
        st.session_state["gen_size"] = size_options[0]

    field_columns = st.columns(2, gap="small")
    with field_columns[0]:
        st.selectbox("输出尺寸", size_options, key="gen_size")
    with field_columns[1]:
        st.selectbox("结构保留", list(STRUCTURE_LABELS), key="gen_structure")
    st.selectbox("目标应用", list(TARGET_LABELS), key="gen_target")

    color_names = {color.name_zh: color.slug for color in context.knowledge.colors}
    with ui.advanced():
        st.multiselect("传统色彩", list(color_names), key="gen_colors")
        st.text_input("负面约束", key="gen_negative")
        st.caption(
            f"当前模型 · {settings.default_model}；"
            f"可选尺寸 {', '.join(size_options)}。"
        )

    return {
        "provider_label": str(provider_label),
        "provider_id": provider_id,
        "model": settings.default_model,
        "mode": MODE_LABELS[mode_label],
    }


def _render_confirmation_panel(values: dict) -> None:
    size = st.session_state.get("gen_size")
    st.markdown(
        '<div class="confirm-panel">'
        '<div class="confirm-panel__title">请确认本次生成（可能产生费用）</div>'
        "<dl>"
        f"<dt>提供商</dt><dd>{ui.escape(values['provider_label'])}</dd>"
        f"<dt>模型</dt><dd>{ui.escape(values['model'])}</dd>"
        f"<dt>尺寸</dt><dd>{ui.escape(size)}</dd>"
        "<dt>数量</dt><dd>1</dd>"
        "</dl></div>",
        unsafe_allow_html=True,
    )


def _dispatch(
    context: StudioContext,
    project,
    extracted_id: str | None,
    values: dict,
) -> None:
    prompt = str(st.session_state.get("gen_prompt") or "").strip()
    if not prompt:
        st.error("请填写提示词。")
        return
    if extracted_id is None:
        st.error("请先确认提取结果后再生成。")
        return
    color_names = {color.name_zh: color.slug for color in context.knowledge.colors}
    selected = st.session_state.get("gen_colors") or []
    slugs = [color_names[name] for name in selected if name in color_names]
    mode = values["mode"]
    byok = None
    if mode is CredentialMode.BYOK:
        stored = st.session_state.get("byok_secret")
        raw = st.session_state.get(_BYOK_KEY)
        if isinstance(stored, SecretStr):
            byok = stored
        elif isinstance(raw, str) and raw.strip():
            byok = SecretStr(raw)
    try:
        context.service.generate(
            project.id,
            GenerationRequest(
                prompt=prompt,
                reference_path=Path(extracted_id),
                model=values["model"],
                provider=values["provider_id"],
                size=str(st.session_state.get("gen_size") or "1024x1024"),
                count=1,
                structure_level=STRUCTURE_LABELS[str(st.session_state.get("gen_structure") or "中")],
                target_application=TARGET_LABELS[str(st.session_state.get("gen_target") or "书签")],
                colors=slugs,
                negative_constraints=str(st.session_state.get("gen_negative") or ""),
            ),
            mode,
            byok,
        )
    except (GenerationFailure, WorkflowError, ValueError) as error:
        message = getattr(error, "user_message_zh", str(error))
        st.error(message)
        return
    st.session_state["generation_confirm_pending"] = False
    ui.flash("生成完成，结果已标注为 AI 生成并写入项目记录。")
    st.rerun()


def _restore_draft() -> None:
    unsaved = st.session_state.get("unsaved")
    if not isinstance(unsaved, dict):
        return
    for key in _SAVED_KEYS:
        if key not in st.session_state and key in unsaved:
            st.session_state[key] = unsaved[key]


def _capture_draft() -> None:
    unsaved = st.session_state.setdefault("unsaved", {})
    for key in _SAVED_KEYS:
        if key in st.session_state:
            unsaved[key] = st.session_state[key]
