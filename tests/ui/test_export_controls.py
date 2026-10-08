# -*- coding: utf-8 -*-
"""Step 6 — mockup generation and the provenance export package."""

from __future__ import annotations

from pathlib import Path

from tests.ui.conftest import all_text, widget_disabled


def _goto(app, label: str) -> None:
    step = next(widget for widget in app.radio if "上传与分类" in widget.options)
    step.set_value(label).run()
    assert not app.exception


def _compose_a_pattern(app) -> None:
    _goto(app, "纹样分析")
    next(button for button in app.button if button.label == "分析").click().run()
    _goto(app, "参数化重组")
    next(button for button in app.button if button.label == "重组").click().run()
    assert not app.exception


def test_export_step_lists_current_artwork_and_export_fields(studio_at_extraction) -> None:
    studio_at_extraction.run()
    _compose_a_pattern(studio_at_extraction)
    _goto(studio_at_extraction, "导出与溯源")

    assert not studio_at_extraction.exception
    labels = [widget.label for widget in studio_at_extraction.selectbox]
    assert "贴图模板" in labels
    assert "贴图纹样" in labels
    artwork = next(widget for widget in studio_at_extraction.selectbox if widget.label == "贴图纹样")
    assert any("patterns/" in str(option) for option in artwork.options)
    assert any("重组纹样" in str(option) for option in artwork.options)
    export_fields = [widget for widget in studio_at_extraction.checkbox if widget.label.startswith("导出")]
    assert len(export_fields) == 7


def test_mockup_is_disabled_until_an_artwork_exists(studio_at_extraction) -> None:
    studio_at_extraction.run()
    _goto(studio_at_extraction, "导出与溯源")
    assert not studio_at_extraction.exception
    mockup = next(button for button in studio_at_extraction.button if button.label == "生成贴图")
    assert widget_disabled(mockup)


def test_mockup_generation_renders_a_captioned_result(studio_at_extraction) -> None:
    studio_at_extraction.run()
    _compose_a_pattern(studio_at_extraction)
    _goto(studio_at_extraction, "导出与溯源")
    next(button for button in studio_at_extraction.button if button.label == "生成贴图").click().run()

    assert not studio_at_extraction.exception
    assert "新贴图" in all_text(studio_at_extraction)


def test_export_reports_the_package_after_the_rerun(
    studio_at_extraction, studio_workspace: Path
) -> None:
    studio_at_extraction.run()
    _compose_a_pattern(studio_at_extraction)
    _goto(studio_at_extraction, "导出与溯源")
    next(button for button in studio_at_extraction.button if button.label == "导出").click().run()

    assert not studio_at_extraction.exception
    successes = [str(node.value) for node in studio_at_extraction.success]
    assert any("已导出到" in value for value in successes), successes
    outputs = studio_workspace.parent / "outputs"
    assert outputs.is_dir(), "the export must be isolated to the test outputs directory"
    packages = [entry for entry in outputs.iterdir() if entry.is_dir()]
    assert packages, "export must publish a package directory"
    assert any((package / "manifest.json").is_file() for package in packages)
