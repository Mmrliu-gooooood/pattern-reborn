# -*- coding: utf-8 -*-
from __future__ import annotations

from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto

from tests.ui.conftest import all_text, radio_option_labels, widget_disabled

BYOK_SECRET = "byok-secret-value-never-display"


def _provider_radio(app):
    return next(widget for widget in app.radio if widget.label == "生图模型")


def _mode_radio(app):
    return next(
        widget
        for widget in app.radio
        if widget.label == "凭证方式"
        or set(radio_option_labels(widget)) >= {"平台默认", "自带密钥"}
    )


def test_generation_exposes_manual_seedream_and_qwen_switch(studio_at_generation) -> None:
    studio_at_generation.run()
    assert not studio_at_generation.exception
    provider = _provider_radio(studio_at_generation)
    assert provider.options == ["Seedream", "Qwen Image 3.0 Pro"]
    assert provider.value == "Seedream"


def test_generation_exposes_platform_default_and_byok_modes(studio_at_generation) -> None:
    studio_at_generation.run()
    assert not studio_at_generation.exception
    mode = _mode_radio(studio_at_generation)
    assert radio_option_labels(mode) == ["平台默认", "自带密钥"]
    assert mode.value == "平台默认"


def test_byok_key_input_is_password_and_never_echoed(studio_at_generation) -> None:
    studio_at_generation.run()
    _mode_radio(studio_at_generation).set_value("自带密钥").run()
    assert not studio_at_generation.exception
    key_input = next(
        widget
        for widget in studio_at_generation.text_input
        if "密钥" in widget.label
    )
    assert key_input.proto.type == TextInputProto.PASSWORD
    key_input.set_value(BYOK_SECRET).run()
    assert not studio_at_generation.exception
    visible = all_text(studio_at_generation)
    assert BYOK_SECRET not in visible
    assert BYOK_SECRET not in "".join(str(node.value) for node in studio_at_generation.markdown)


def test_generation_confirmation_summarizes_provider_model_size_and_count(
    studio_at_generation,
) -> None:
    studio_at_generation.run()
    prompt = next(widget for widget in studio_at_generation.text_area if widget.label == "提示词")
    prompt.set_value("保持莲纹骨架，生成书签纹样").run()
    next(button for button in studio_at_generation.button if button.label == "生成").click().run()
    assert not studio_at_generation.exception
    summary = all_text(studio_at_generation)
    assert "Seedream" in summary
    assert "doubao-seedream-4-0-250828" in summary
    assert "1024x1024" in summary
    assert "1" in summary
    assert any(button.label == "确认生成" for button in studio_at_generation.button)


def test_prompt_survives_fake_generation_failure(
    studio_at_generation, fake_adapters
) -> None:
    from pattern_reborn.generation.base import ProviderId

    fake_adapters[ProviderId.SEEDREAM].fail = True
    studio_at_generation.run()
    prompt = next(widget for widget in studio_at_generation.text_area if widget.label == "提示词")
    prompt.set_value("失败后仍应保留的提示词").run()
    next(button for button in studio_at_generation.button if button.label == "生成").click().run()
    next(button for button in studio_at_generation.button if button.label == "确认生成").click().run()
    assert not studio_at_generation.exception
    text = all_text(studio_at_generation)
    assert "超时" in text or "失败" in text
    restored = next(
        widget for widget in studio_at_generation.text_area if widget.label == "提示词"
    )
    assert restored.value == "失败后仍应保留的提示词"
    assert _provider_radio(studio_at_generation).value == "Seedream"
    assert fake_adapters[ProviderId.QWEN].calls == []


def test_switching_provider_keeps_neutral_generation_fields(studio_at_generation) -> None:
    studio_at_generation.run()
    prompt = next(widget for widget in studio_at_generation.text_area if widget.label == "提示词")
    prompt.set_value("切换模型后仍保留提示词").run()
    size = next(widget for widget in studio_at_generation.selectbox if widget.label == "输出尺寸")
    size.set_value("1024x1024").run()
    structure = next(
        widget for widget in studio_at_generation.selectbox if widget.label == "结构保留"
    )
    structure.set_value("高").run()
    target = next(
        widget for widget in studio_at_generation.selectbox if widget.label == "目标应用"
    )
    target.set_value("书签").run()
    _provider_radio(studio_at_generation).set_value("Qwen Image 3.0 Pro").run()
    assert not studio_at_generation.exception
    assert _provider_radio(studio_at_generation).value == "Qwen Image 3.0 Pro"
    assert (
        next(widget for widget in studio_at_generation.text_area if widget.label == "提示词").value
        == "切换模型后仍保留提示词"
    )
    assert (
        next(widget for widget in studio_at_generation.selectbox if widget.label == "输出尺寸").value
        == "1024x1024"
    )
    assert (
        next(widget for widget in studio_at_generation.selectbox if widget.label == "结构保留").value
        == "高"
    )
    assert (
        next(widget for widget in studio_at_generation.selectbox if widget.label == "目标应用").value
        == "书签"
    )


def test_generation_stays_enabled_when_cloudflare_probe_fails(
    studio_at_generation, monkeypatch
) -> None:
    monkeypatch.setattr("pattern_reborn.capabilities.probe_online", lambda: False)
    studio_at_generation.run()
    assert not studio_at_generation.exception
    generate = next(button for button in studio_at_generation.button if button.label == "生成")
    assert not widget_disabled(generate)
    prompt = next(widget for widget in studio_at_generation.text_area if widget.label == "提示词")
    prompt.set_value("离线探测失败仍应可生成").run()
    generate = next(button for button in studio_at_generation.button if button.label == "生成")
    generate.click().run()
    assert not studio_at_generation.exception
    confirm = next(button for button in studio_at_generation.button if button.label == "确认生成")
    assert not widget_disabled(confirm)


def test_switching_to_qwen_resets_unsupported_seedream_2k(studio_at_generation) -> None:
    studio_at_generation.run()
    size = next(widget for widget in studio_at_generation.selectbox if widget.label == "输出尺寸")
    size.set_value("2K").run()
    _provider_radio(studio_at_generation).set_value("Qwen Image 3.0 Pro").run()
    assert not studio_at_generation.exception
    size = next(widget for widget in studio_at_generation.selectbox if widget.label == "输出尺寸")
    option_labels = [getattr(item, "label", item) for item in size.options]
    assert size.value != "2K"
    assert "2K" not in option_labels
    assert size.value == option_labels[0]


def test_generation_prompt_sent_to_adapter_includes_constraints(
    studio_at_generation, fake_adapters
) -> None:
    from pattern_reborn.generation.base import ProviderId

    studio_at_generation.run()
    prompt = next(widget for widget in studio_at_generation.text_area if widget.label == "提示词")
    prompt.set_value("保持莲纹骨架").run()
    next(widget for widget in studio_at_generation.selectbox if widget.label == "结构保留").set_value(
        "高"
    ).run()
    next(widget for widget in studio_at_generation.selectbox if widget.label == "目标应用").set_value(
        "书签"
    ).run()
    colors = next(widget for widget in studio_at_generation.multiselect if widget.label == "传统色彩")
    first_color = colors.options[0]
    colors.set_value([first_color]).run()
    next(button for button in studio_at_generation.button if button.label == "生成").click().run()
    next(button for button in studio_at_generation.button if button.label == "确认生成").click().run()
    assert not studio_at_generation.exception
    assert fake_adapters[ProviderId.SEEDREAM].calls
    sent = fake_adapters[ProviderId.SEEDREAM].calls[-1].prompt
    assert "高" in sent or "high" in sent.lower()
    assert "书签" in sent or "bookmark" in sent.lower()
    color_label = str(getattr(first_color, "label", first_color))
    assert color_label in sent or any(
        token in sent for token in (color_label, "色彩", "color")
    )


def test_generated_results_show_visible_ai_labels(
    studio_at_generation, fake_adapters
) -> None:
    studio_at_generation.run()
    prompt = next(widget for widget in studio_at_generation.text_area if widget.label == "提示词")
    prompt.set_value("生成可见 AI 标记").run()
    next(button for button in studio_at_generation.button if button.label == "生成").click().run()
    next(button for button in studio_at_generation.button if button.label == "确认生成").click().run()
    assert not studio_at_generation.exception
    text = all_text(studio_at_generation)
    assert "AI 生成" in text
    step = next(widget for widget in studio_at_generation.radio if "导出与溯源" in widget.options)
    step.set_value("导出与溯源").run()
    artwork = next(
        widget for widget in studio_at_generation.selectbox if widget.label == "贴图纹样"
    )
    generated = next(
        option
        for option in artwork.options
        if "generated/" in str(getattr(option, "label", option))
        or "生成" in str(getattr(option, "label", option))
    )
    artwork.set_value(generated).run()
    next(button for button in studio_at_generation.button if button.label == "生成贴图").click().run()
    assert not studio_at_generation.exception
    export_text = all_text(studio_at_generation)
    assert "AI 辅助" in export_text or "AI 生成" in export_text
