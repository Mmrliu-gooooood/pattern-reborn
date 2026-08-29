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
    app.session_state["studio_step"] = "AI 创意生成"
    app.session_state["byok_secret"] = "stale-byok"
    app.run()
    assert not app.exception
    next(button for button in app.button if button.label == "开始新创作").click().run()
    assert not app.exception
    assert session_get(app, "project_id") in (None, "")
    assert session_get(app, "selected_category") in (None, "")
    assert session_get(app, "studio_step") != "AI 创意生成"
    assert session_get(app, "byok_secret") in (None, "")


def test_return_home_clears_studio_step_and_byok(studio_at_generation) -> None:
    studio_at_generation.session_state["byok_secret"] = "stale-byok"
    studio_at_generation.run()
    assert not studio_at_generation.exception
    next(button for button in studio_at_generation.button if button.label == "返回首页").click().run()
    assert not studio_at_generation.exception
    assert session_get(studio_at_generation, "studio_step") in (None, "")
    assert session_get(studio_at_generation, "byok_secret") in (None, "")
    assert session_get(studio_at_generation, "project_id") in (None, "")


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


def test_extract_without_user_points_does_not_include_origin_keep(
    studio_at_extraction, studio_workspace: Path
) -> None:
    from pattern_reborn.projects import ProjectRepository

    studio_at_extraction.run()
    next(button for button in studio_at_extraction.button if button.label == "提取").click().run()
    assert not studio_at_extraction.exception
    project = ProjectRepository(studio_workspace).load(studio_at_extraction.session_state["project_id"])
    pending = project.processing_parameters.get("pending_extraction")
    assert isinstance(pending, dict)
    points = pending.get("hints", {}).get("points")
    assert points == []
    assert {"x": 0, "y": 0, "keep": True} not in (points or [])


def test_confirm_extraction_clears_pending_and_hides_button(
    studio_at_extraction, studio_workspace: Path
) -> None:
    from pattern_reborn.projects import ProjectRepository

    studio_at_extraction.run()
    next(button for button in studio_at_extraction.button if button.label == "提取").click().run()
    assert not studio_at_extraction.exception
    assert any(button.label == "确认提取" for button in studio_at_extraction.button)
    next(button for button in studio_at_extraction.button if button.label == "确认提取").click().run()
    assert not studio_at_extraction.exception
    assert not any(button.label == "确认提取" for button in studio_at_extraction.button)
    project = ProjectRepository(studio_workspace).load(studio_at_extraction.session_state["project_id"])
    assert project.processing_parameters.get("pending_extraction") in (None, {})


def test_canvas_objects_map_rect_and_points_into_hints() -> None:
    from pattern_reborn.segmentation import PromptPoint
    from pattern_reborn.ui.studio import hints_from_canvas_objects

    hints, strokes = hints_from_canvas_objects(
        {
            "objects": [
                {"type": "rect", "x": 10, "y": 20, "width": 30, "height": 40},
                {"type": "circle", "x": 15, "y": 25},
            ]
        }
    )
    assert hints.box == (10, 20, 40, 60)
    assert PromptPoint(15, 25, True) in hints.points
    assert strokes == []


def test_extraction_advanced_notes_opencv_baseline_not_mobilesam(
    studio_at_extraction,
) -> None:
    studio_at_extraction.run()
    assert not studio_at_extraction.exception
    text = all_text(studio_at_extraction)
    assert "OpenCV" in text
    assert "未调用 MobileSAM" in text or "OpenCV 基线" in text


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
