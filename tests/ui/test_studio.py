# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys

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


def test_extraction_fallback_hides_backend_selector_and_submits_opencv(
    studio_at_extraction,
    studio_workspace: Path,
) -> None:
    from pattern_reborn.projects import ProjectRepository

    studio_at_extraction.run()

    assert not studio_at_extraction.exception
    assert not any(widget.label == "分割后端" for widget in studio_at_extraction.selectbox)
    text = all_text(studio_at_extraction)
    assert "OpenCV" in text
    assert "回退" in text

    next(button for button in studio_at_extraction.button if button.label == "提取").click().run()
    assert not studio_at_extraction.exception
    project = ProjectRepository(studio_workspace).load(
        studio_at_extraction.session_state["project_id"]
    )
    pending = project.processing_parameters.get("pending_extraction")
    assert isinstance(pending, dict)
    assert pending["backend"] == "opencv"


def test_extraction_shows_backend_selector_without_eager_optional_imports(
    studio_at_extraction,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "pattern_reborn.capabilities.find_spec",
        lambda name: object() if name == "mobile_sam" else None,
    )
    assert "torch" not in sys.modules
    assert "mobile_sam" not in sys.modules

    studio_at_extraction.run()

    assert not studio_at_extraction.exception
    backend = next(
        widget for widget in studio_at_extraction.selectbox if widget.label == "分割后端"
    )
    assert list(backend.options) == ["OpenCV", "MobileSAM"]
    assert "torch" not in sys.modules
    assert "mobile_sam" not in sys.modules


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


def test_analysis_renders_contour_metrics_without_an_internal_error(studio_at_extraction) -> None:
    """The analysis step must use the public contour metric field name."""
    studio_at_extraction.run()
    step = next(widget for widget in studio_at_extraction.radio if "纹样分析" in widget.options)
    step.set_value("纹样分析").run()

    next(button for button in studio_at_extraction.button if button.label == "分析").click().run()

    assert not studio_at_extraction.exception
    assert "轮廓" in all_text(studio_at_extraction)


def test_recomposition_renders_canvas_size_controls(studio_at_extraction) -> None:
    """Parameterised recomposition must remain available after layout changes."""
    studio_at_extraction.run()
    step = next(widget for widget in studio_at_extraction.radio if "参数化重组" in widget.options)
    step.set_value("参数化重组").run()

    assert not studio_at_extraction.exception
    labels = [widget.label for widget in studio_at_extraction.number_input]
    assert "画布宽度" in labels
    assert "画布高度" in labels


def test_existing_project_upload_step_shows_summary_not_create_form(studio_at_extraction) -> None:
    """Existing projects keep their source record instead of reopening creation."""
    studio_at_extraction.run()
    step = next(widget for widget in studio_at_extraction.radio if "上传与分类" in widget.options)
    step.set_value("上传与分类").run()

    assert not studio_at_extraction.exception
    labels = [button.label for button in studio_at_extraction.button]
    assert "创建项目" not in labels
    assert "新建项目" in labels
    # The read-only summary states the recorded classification and rights in Chinese.
    text = all_text(studio_at_extraction)
    assert "品类 · 剪纸" in text
    assert "来源权利 ·" in text
    assert "paper_cutting" not in text


def test_new_project_from_summary_clears_the_active_project(studio_at_extraction) -> None:
    studio_at_extraction.run()
    step = next(widget for widget in studio_at_extraction.radio if "上传与分类" in widget.options)
    step.set_value("上传与分类").run()
    next(button for button in studio_at_extraction.button if button.label == "新建项目").click().run()
    assert not studio_at_extraction.exception
    assert session_get(studio_at_extraction, "project_id") in (None, "")
    assert any(button.label == "创建项目" for button in studio_at_extraction.button)


def _goto(app, label: str):
    step = next(widget for widget in app.radio if "上传与分类" in widget.options)
    step.set_value(label).run()
    assert not app.exception


def _roundtrip_through_upload(app, label: str) -> None:
    """Leave the step and come back, proving the result came from disk."""
    _goto(app, "上传与分类")
    _goto(app, label)


def test_analysis_result_is_restored_from_the_project_after_a_rerun(studio_at_extraction) -> None:
    """Rendering analysis only inside the button branch loses it on every rerun."""
    studio_at_extraction.run()
    _goto(studio_at_extraction, "纹样分析")
    next(button for button in studio_at_extraction.button if button.label == "分析").click().run()
    assert not studio_at_extraction.exception
    assert "主色板" in all_text(studio_at_extraction)
    assert "传统色匹配" in all_text(studio_at_extraction)

    _roundtrip_through_upload(studio_at_extraction, "纹样分析")

    restored = all_text(studio_at_extraction)
    assert "主色板" in restored
    assert "轮廓数量" in restored
    assert any(button.label == "重新分析" for button in studio_at_extraction.button)


def test_recomposition_result_is_restored_from_the_project_after_a_rerun(
    studio_at_extraction,
) -> None:
    studio_at_extraction.run()
    _goto(studio_at_extraction, "纹样分析")
    next(button for button in studio_at_extraction.button if button.label == "分析").click().run()
    _goto(studio_at_extraction, "参数化重组")
    next(button for button in studio_at_extraction.button if button.label == "重组").click().run()
    assert not studio_at_extraction.exception
    assert "当前重组纹样" in all_text(studio_at_extraction)

    _roundtrip_through_upload(studio_at_extraction, "参数化重组")

    assert "当前重组纹样" in all_text(studio_at_extraction)


def test_mutating_steps_report_success_after_the_rerun(studio_at_extraction) -> None:
    """A st.success immediately before st.rerun is never seen; use the flash queue."""
    studio_at_extraction.run()
    next(button for button in studio_at_extraction.button if button.label == "提取").click().run()
    assert not studio_at_extraction.exception
    successes = [str(node.value) for node in studio_at_extraction.success]
    assert any("提取完成" in value for value in successes), successes
    assert any(button.label == "确认提取" for button in studio_at_extraction.button)


def test_confirmed_extraction_is_redisplayed_after_it_is_confirmed(studio_at_extraction) -> None:
    studio_at_extraction.run()
    next(button for button in studio_at_extraction.button if button.label == "提取").click().run()
    next(button for button in studio_at_extraction.button if button.label == "确认提取").click().run()
    assert not studio_at_extraction.exception
    assert "已确认" in all_text(studio_at_extraction)
    assert "提取结果" in all_text(studio_at_extraction)


def test_every_studio_step_renders_exactly_one_h1(studio_at_extraction) -> None:
    studio_at_extraction.run()
    for label in STEP_LABELS:
        _goto(studio_at_extraction, label)
        markdown = "\n".join(str(node.value) for node in studio_at_extraction.markdown)
        assert markdown.count("<h1>") == 1, label
        assert "studio-header" in markdown, label
