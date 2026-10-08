# -*- coding: utf-8 -*-
"""Step 1 — 上传与分类: create a project, or summarise the existing one."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import streamlit as st

from pattern_reborn.ui import components as ui
from pattern_reborn.domain import CategoryId, StepId
from pattern_reborn.ui.labels import (
    PROVENANCE_LABELS,
    category_label,
    current_step_of,
    profile_label,
    provenance_label,
    step_short_label,
)
from pattern_reborn.ui.presenters import source_path
from pattern_reborn.ui.steps.context import StudioContext
from pattern_reborn.workflow import CreateProjectCommand, WorkflowError

_UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"]
_ALLOWED_SUFFIXES = frozenset(f".{extension}" for extension in _UPLOAD_TYPES)


def render(context: StudioContext) -> None:
    if context.project is not None:
        _render_existing(context)
        return
    _render_create(context)


def _category_names(context: StudioContext) -> dict[str, CategoryId]:
    return {category.display_name_zh: category.id for category in context.knowledge.categories}


def _default_category_index(names: dict[str, CategoryId]) -> int:
    preselected = st.session_state.get("selected_category")
    if isinstance(preselected, str):
        for index, category_id in enumerate(names.values()):
            if category_id.value == preselected:
                return index
    return 0


def _render_create(context: StudioContext) -> None:
    names = _category_names(context)
    workbench, controls = ui.two_panel_step("source")

    with workbench:
        ui.render_kicker("来源图像", "SOURCE IMAGE")
        ui.render_note(
            "先建立一份可追溯的本地项目。原始文件会被复制进项目目录并记录 SHA-256，"
            "后续所有结果都可回溯到它。"
        )
        uploaded = st.file_uploader("上传图像", type=_UPLOAD_TYPES)

    with controls:
        ui.render_kicker("项目信息", "PROJECT RECORD")
        name = st.text_input("项目名称")
        category_name = st.selectbox("品类", list(names), index=_default_category_index(names))
        provenance_name = st.selectbox("来源与权利", list(PROVENANCE_LABELS))
        with ui.advanced():
            subject = st.text_input("题材")
            st.caption("题材为可选项，确认后写入项目记录；算法参数在后续步骤中设置。")

    note_column, action_column = ui.action_bar("source")
    with note_column:
        if uploaded is None:
            ui.render_action_note("请先选择一张来源图像，并填写项目名称。")
        elif not name.strip():
            ui.render_action_note("已选择图像，还需填写<b>项目名称</b>。")
        else:
            ui.render_action_note(f"将创建项目 <b>{name.strip()}</b>，并记录来源权利。")
    with action_column:
        if st.button("创建项目", type="primary", width="stretch"):
            _create(context, uploaded, name, names.get(category_name), PROVENANCE_LABELS[provenance_name], subject)


def _create(
    context: StudioContext,
    uploaded,
    name: str,
    category: CategoryId | None,
    provenance,
    subject: str,
) -> None:
    if uploaded is None:
        st.error("请先选择一张来源图像。")
        return
    if not name.strip():
        st.error("请填写项目名称。")
        return
    if category is None:
        st.error("请选择一个品类。")
        return
    staged: Path | None = None
    try:
        staged = _store_upload(context, uploaded)
        created = context.service.create_project(
            CreateProjectCommand(
                name=name.strip(),
                source=staged,
                category=category,
                provenance=provenance,
                subject=subject.strip() or None,
            )
        )
    except (WorkflowError, OSError) as error:
        st.error(str(error))
        return
    finally:
        _discard_staged_upload(staged)
    st.session_state["project_id"] = created.id
    st.session_state.pop("studio_step", None)
    ui.flash("项目已创建，来源图像已记录。")
    st.rerun()


def _store_upload(context: StudioContext, uploaded) -> Path:
    """Stage the upload under its original name so provenance keeps it.

    The repository records ``SourceRecord.original_filename`` from the staged
    file's name, so writing a bare UUID here would replace the user's filename
    with a hash in the project record. Each upload gets its own directory so two
    uploads of the same filename cannot collide.
    """
    incoming = context.service.repository.workspace / ".incoming" / uuid4().hex
    incoming.mkdir(parents=True, exist_ok=True)
    destination = incoming / _safe_upload_name(getattr(uploaded, "name", None))
    destination.write_bytes(uploaded.getvalue())
    return destination


def _discard_staged_upload(staged: Path | None) -> None:
    """Best-effort cleanup of the staging directory; never fails the create."""
    if staged is None:
        return
    try:
        staged.unlink(missing_ok=True)
        staged.parent.rmdir()
    except OSError:
        pass


def _safe_upload_name(raw_name: object) -> str:
    """Reduce an uploaded filename to a safe basename, keeping its extension.

    Only the basename survives, and only alphanumerics plus ``-``/``_`` in the
    stem, so a crafted name cannot traverse or smuggle separators into the
    staged path. The extension is restricted to the uploader's own allow-list so
    an unexpected suffix stays out of the provenance record, and anything else
    falls back to ``.png``.
    """
    name = Path(str(raw_name or "source.png")).name
    stem = "".join(char for char in Path(name).stem if char.isalnum() or char in "-_")[:60]
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        suffix = ".png"
    return f"{stem or 'source'}{suffix}"


def _render_existing(context: StudioContext) -> None:
    project = context.project
    assert project is not None
    project_dir = context.service.repository.project_dir(project.id)
    workbench, controls = ui.two_panel_step("source")

    with workbench:
        ui.render_kicker("已存来源", "RECORDED SOURCE")
        path = source_path(project_dir, project)
        if path is not None:
            ui.render_image_panel(path, project.source.original_filename, badge="原始图像")
        else:
            ui.render_empty_state("来源图像不可用", "项目记录的源文件缺失或已被移动。")
        ui.render_note("该来源已与当前项目绑定。替换图片会建立一个新项目，原有溯源记录不会被覆盖。")

    with controls:
        ui.render_kicker("项目记录", "PROJECT RECORD")
        st.markdown(
            f'<div class="project-card__name">{ui.escape(project.name)}</div>'
            f'<div class="project-card__meta">品类 · {ui.escape(category_label(project.category))}<br>'
            f"来源权利 · {ui.escape(provenance_label(project.provenance))}<br>"
            f"文件 · {ui.escape(project.source.original_filename)}<br>"
            f"SHA-256 · {ui.escape(project.source.sha256[:16])}…<br>"
            f"大小 · {_format_size(project.source.byte_size)}<br>"
            f"创建 · {project.created_at.strftime('%Y.%m.%d %H:%M')}</div>",
            unsafe_allow_html=True,
        )
        if project.subject:
            st.markdown(
                f'<div class="project-card__meta">题材 · {ui.escape(project.subject)}</div>',
                unsafe_allow_html=True,
            )
        step = current_step_of(project)
        st.markdown(
            f'<div class="project-card__meta">处理档案 · '
            f"{ui.escape(profile_label(project.profile) if project.profile else '待选择')}<br>"
            f"当前步骤 · {ui.escape(step_short_label(step))}</div>",
            unsafe_allow_html=True,
        )
        with ui.advanced():
            st.caption(
                "来源图像字节在项目目录中原样保留；任何处理都不会改写它。"
                "算法参数在后续步骤中设置。"
            )

    note_column, action_column = ui.action_bar("source")
    with note_column:
        ui.render_action_note(
            "新建项目不会删除现有项目记录；已确认的提取、分析与重组结果会转为过期状态。"
        )
    with action_column:
        if st.button("新建项目", key="new-project-from-summary", type="primary", width="stretch"):
            _clear_active_project()
            st.rerun()


def _format_size(byte_size: int) -> str:
    if byte_size < 1024:
        return f"{byte_size} B"
    if byte_size < 1024 * 1024:
        return f"{byte_size / 1024:.1f} KB"
    return f"{byte_size / (1024 * 1024):.2f} MB"


def _clear_active_project() -> None:
    """Leave the project behind but keep it on disk; only session state is dropped."""
    for key in (
        "project_id",
        "selected_category",
        "studio_step",
        "canvas_objects",
        "mask_strokes",
        "unsaved",
        "generation_confirm_pending",
    ):
        st.session_state.pop(key, None)


def next_step_available(project) -> bool:
    """The source step is complete once the project exists."""
    return project is not None


def step_id() -> StepId:
    return StepId.UPLOAD
