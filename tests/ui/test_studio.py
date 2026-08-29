# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.ui.conftest import (
    APP_PATH,
    STEP_LABELS,
    all_text,
    radio_option_labels,
    session_get,
)


def test_sidebar_has_six_steps_and_advanced_settings_start_collapsed(studio_test) -> None:
    studio_test.run()
    assert not studio_test.exception
    assert radio_option_labels(studio_test.radio[0]) == STEP_LABELS
    assert studio_test.expander[0].label == "高级设置"
    assert studio_test.expander[0].proto.expanded is False


def test_new_creation_clears_stale_project_id(
    studio_workspace: Path, monkeypatch
) -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.session_state["project_id"] = "stale-project"
    app.session_state["selected_category"] = "paper_cutting"
    app.run()
    assert not app.exception
    next(button for button in app.button if button.label == "开始新创作").click().run()
    assert not app.exception
    assert session_get(app, "project_id") in (None, "")
    assert session_get(app, "selected_category") in (None, "")


def test_manual_box_and_click_inputs_when_canvas_absent(studio_at_extraction) -> None:
    studio_at_extraction.run()
    assert not studio_at_extraction.exception
    labels = [widget.label for widget in studio_at_extraction.number_input]
    for expected in ("框选左", "框选上", "框选右", "框选下", "提示点 X", "提示点 Y"):
        assert expected in labels
    text_labels = [widget.label for widget in studio_at_extraction.text_input]
    assert any("笔触" in label for label in text_labels)
    modes = [
        widget
        for widget in studio_at_extraction.radio
        if "保留" in radio_option_labels(widget) and "删除" in radio_option_labels(widget)
    ]
    assert modes, "keep/remove stroke controls must remain without a canvas"


def test_canvas_import_failure_warns_and_keeps_manual_inputs(
    studio_at_extraction, monkeypatch
) -> None:
    monkeypatch.setattr(
        "pattern_reborn.capabilities.find_spec",
        lambda name: object() if name == "streamlit_drawable_konva" else None,
    )
    studio_at_extraction.run()
    assert not studio_at_extraction.exception
    warning_text = "\n".join(str(node.value) for node in studio_at_extraction.warning)
    assert "画布" in warning_text
    labels = [widget.label for widget in studio_at_extraction.number_input]
    assert "框选左" in labels
    assert "提示点 X" in labels


def test_backward_navigation_keeps_unsaved_generation_prompt(studio_at_generation) -> None:
    studio_at_generation.run()
    assert not studio_at_generation.exception
    prompt = next(widget for widget in studio_at_generation.text_area if widget.label == "提示词")
    prompt.set_value("保持莲纹骨架，生成书签纹样").run()
    step = next(widget for widget in studio_at_generation.radio if "上传与分类" in widget.options)
    step.set_value("上传与分类").run()
    assert not studio_at_generation.exception
    step = next(widget for widget in studio_at_generation.radio if "上传与分类" in widget.options)
    step.set_value("AI 创意生成").run()
    assert not studio_at_generation.exception
    restored = next(
        widget for widget in studio_at_generation.text_area if widget.label == "提示词"
    )
    assert restored.value == "保持莲纹骨架，生成书签纹样"
