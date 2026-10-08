# -*- coding: utf-8 -*-
"""Step 1 — creating a project from an uploaded source."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

from pattern_reborn.projects import ProjectRepository
from tests.ui.conftest import APP_PATH, all_text, session_get


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (16, 16), (180, 40, 46)).save(buffer, format="PNG")
    return buffer.getvalue()


def _open_upload(studio_workspace: Path) -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.session_state["route"] = "studio"
    app.session_state["studio_step"] = "上传与分类"
    app.run()
    return app


def _uploader(app: AppTest):
    return next(widget for widget in app.file_uploader if widget.label == "上传图像")


def test_uploading_a_source_creates_a_traceable_project(studio_workspace: Path) -> None:
    app = _open_upload(studio_workspace)
    assert not app.exception
    assert any(button.label == "创建项目" for button in app.button)

    _uploader(app).set_value(("莲纹.png", _png_bytes(), "image/png")).run()
    next(widget for widget in app.text_input if widget.label == "项目名称").set_value("莲纹书签").run()
    next(button for button in app.button if button.label == "创建项目").click().run()

    assert not app.exception
    project_id = session_get(app, "project_id")
    assert isinstance(project_id, str) and project_id
    project = ProjectRepository(studio_workspace).load(project_id)
    assert project.name == "莲纹书签"
    assert project.source.original_filename == "莲纹.png"
    assert len(project.source.sha256) == 64
    # The source bytes are copied into the project and the upload step is confirmed.
    assert (studio_workspace / project_id / project.source.relative_path).is_file()
    assert "upload" in [step.value for step in project.confirmed_steps]
    # A success message must be visible after the rerun, not swallowed by it.
    assert any("项目已创建" in str(node.value) for node in app.success)


def test_creating_without_a_source_reports_the_missing_field(studio_workspace: Path) -> None:
    app = _open_upload(studio_workspace)
    next(widget for widget in app.text_input if widget.label == "项目名称").set_value("只有名字").run()
    next(button for button in app.button if button.label == "创建项目").click().run()

    assert not app.exception
    assert session_get(app, "project_id") in (None, "")
    assert any("选择一张来源图像" in str(node.value) for node in app.error)


def test_creating_without_a_name_reports_the_missing_field(studio_workspace: Path) -> None:
    app = _open_upload(studio_workspace)
    _uploader(app).set_value(("莲纹.png", _png_bytes(), "image/png")).run()
    next(button for button in app.button if button.label == "创建项目").click().run()

    assert not app.exception
    assert session_get(app, "project_id") in (None, "")
    assert any("项目名称" in str(node.value) for node in app.error)


def test_create_form_hints_what_is_still_missing(studio_workspace: Path) -> None:
    app = _open_upload(studio_workspace)
    assert "请先选择一张来源图像" in all_text(app)

    _uploader(app).set_value(("莲纹.png", _png_bytes(), "image/png")).run()
    assert "项目名称" in all_text(app)


def test_selecting_a_category_preselects_it_on_the_create_form(studio_workspace: Path) -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.session_state["selected_category"] = "ceramic_ornament"
    app.session_state["studio_step"] = "上传与分类"
    app.session_state["route"] = "studio"
    app.run()

    assert not app.exception
    category = next(widget for widget in app.selectbox if widget.label == "品类")
    assert category.value == "陶瓷纹饰"
