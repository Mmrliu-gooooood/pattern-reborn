# -*- coding: utf-8 -*-
"""Layout primitives shared by the studio steps."""

from __future__ import annotations

import ast
from pathlib import Path
import re

from streamlit.testing.v1 import AppTest

from pattern_reborn.ui import components as ui

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_ROOT = REPO_ROOT / "src" / "pattern_reborn" / "ui"

_CARD_KEY_PREFIXES = ("st-key-recent-card-", "st-key-category-card-", "st-key-demo-card-")
_PANEL_KEY_PREFIXES = ("st-key-workbench-", "st-key-controls-", "st-key-action-bar-")


def _script(body: str) -> AppTest:
    """Run an inline script through AppTest so Streamlit helpers work normally."""
    path = REPO_ROOT / ".cache" / "tmp" / "ui_components_script.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return AppTest.from_file(str(path), default_timeout=15)


def test_escape_handles_every_html_metacharacter() -> None:
    assert ui.escape("<b>&\"x\"</b>") == "&lt;b&gt;&amp;&quot;x&quot;&lt;/b&gt;"
    assert ui.escape(None) == "None"


def test_step_header_renders_one_h1_and_the_persisted_project_name() -> None:
    app = _script(
        "import streamlit as st\n"
        "from pattern_reborn.domain import StepId\n"
        "from pattern_reborn.ui import components as ui\n"
        "ui.render_step_header(StepId.EXTRACTION, '莲纹书签')\n"
    )
    app.run()
    assert not app.exception
    markdown = "\n".join(str(node.value) for node in app.markdown)
    assert markdown.count("<h1>") == 1
    assert "<h1>智能提取</h1>" in markdown
    assert "studio-header" in markdown
    assert "莲纹书签" in markdown


def test_step_header_escapes_a_hostile_project_name() -> None:
    app = _script(
        "import streamlit as st\n"
        "from pattern_reborn.domain import StepId\n"
        "from pattern_reborn.ui import components as ui\n"
        "ui.render_step_header(StepId.UPLOAD, '<img src=x onerror=alert(1)>')\n"
    )
    app.run()
    assert not app.exception
    markdown = "\n".join(str(node.value) for node in app.markdown)
    assert "<img src=x" not in markdown
    assert "&lt;img src=x" in markdown


def test_streamlit_never_emits_the_use_container_width_deprecation() -> None:
    """The deprecated width argument is replaced by the supported `width` API."""
    offenders: list[str] = []
    for path in UI_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "use_container_width" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_studio_panels_are_driven_by_container_keys() -> None:
    """HTML wrappers cannot contain widgets, so panels rely on `st.container(key=...)`."""
    home = (UI_ROOT / "home.py").read_text(encoding="utf-8")
    architecture = "\n".join(
        (UI_ROOT / name).read_text(encoding="utf-8")
        for name in ("components.py", "steps/source.py", "steps/generation.py")
    )
    for prefix in ("recent-card-", "category-card-", "demo-card-"):
        assert f"key=f\"{prefix}" in home, prefix
    assert 'f"workbench-{step_key}"' in architecture
    assert 'f"controls-{step_key}"' in architecture
    assert 'f"action-bar-{key}"' in architecture


_TAGS = (
    "div",
    "section",
    "dl",
    "dt",
    "dd",
    "p",
    "span",
    "table",
    "tr",
    "td",
    "ul",
    "li",
    "b",
    "strong",
)
_OPEN_TAG = re.compile(r"<\s*(" + "|".join(_TAGS) + r")\b[^>]*?(/?)>")
_CLOSE_TAG = re.compile(r"<\s*/\s*(" + "|".join(_TAGS) + r")\s*>")


def _literal_html(node: ast.expr) -> str | None:
    """Literal text of a (possibly f-)string argument, interpolations removed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal_html(node.left), _literal_html(node.right)
        return None if left is None or right is None else left + right
    return None


def test_no_markdown_block_emits_unbalanced_html() -> None:
    """Streamlit closes each markdown call in its own element container.

    An opening tag left unclosed in one call cannot wrap the widgets that follow
    it — the browser closes it at the end of that container — so the frame is
    silently lost and a stray tag is rendered. This caught the original demo
    cards, whose ``<div class="demo-card">`` wrapped nothing.
    """
    unbalanced: list[str] = []
    for path in sorted(UI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "attr", None) != "markdown":
                continue
            if not node.args:
                continue
            html = _literal_html(node.args[0])
            if not html:
                continue
            depth = sum(1 for match in _OPEN_TAG.finditer(html) if not match.group(2))
            depth -= len(_CLOSE_TAG.findall(html))
            if depth != 0:
                unbalanced.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} depth={depth}")
    assert unbalanced == []


def test_theme_draws_every_container_key_the_ui_uses() -> None:
    """A keyed container without a matching CSS rule silently loses its frame."""
    css = (UI_ROOT / "assets" / "theme.css").read_text(encoding="utf-8")
    for prefix in (*_CARD_KEY_PREFIXES, *_PANEL_KEY_PREFIXES):
        assert f'[class*="{prefix}"]' in css, prefix


def test_metric_grid_and_palette_render_escaped_markup() -> None:
    app = _script(
        "import streamlit as st\n"
        "from pattern_reborn.ui import components as ui\n"
        "ui.render_metric_grid([('轮廓数量', '2', '孔洞 1')])\n"
        "ui.render_palette([{'hex_value': '#B8282E', 'coverage': 0.5, 'pixel_count': 32}])\n"
        "ui.render_color_matches([{'hex_value': '#B8282E', 'traditional_name_zh': '朱砂', 'distance': 4.2}])\n"
    )
    app.run()
    assert not app.exception
    markdown = "\n".join(str(node.value) for node in app.markdown)
    assert "metric-grid" in markdown
    assert "轮廓数量" in markdown
    assert "swatch__chip" in markdown
    assert "#B8282E" in markdown
    assert "朱砂" in markdown


def test_action_bar_yields_a_note_column_and_an_action_column() -> None:
    app = _script(
        "import streamlit as st\n"
        "from pattern_reborn.ui import components as ui\n"
        "note, action = ui.action_bar('demo')\n"
        "with note:\n"
        "    ui.render_action_note('提示')\n"
        "with action:\n"
        "    st.button('继续', key='demo-next')\n"
    )
    app.run()
    assert not app.exception
    markdown = "\n".join(str(node.value) for node in app.markdown)
    assert "action-note" in markdown
    assert any(button.label == "继续" for button in app.button)


def test_flash_messages_survive_a_rerun() -> None:
    """st.success immediately before st.rerun is never seen; the queue is."""
    path = REPO_ROOT / ".cache" / "tmp" / "ui_flash_script.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import streamlit as st\n"
        "from pattern_reborn.ui import components as ui\n"
        "ui.render_flash()\n"
        "if st.button('go', key='go'):\n"
        "    ui.flash('已完成')\n"
        "    st.rerun()\n",
        encoding="utf-8",
    )
    app = AppTest.from_file(str(path), default_timeout=15)
    app.run()
    assert not app.success
    next(button for button in app.button if button.label == "go").click().run()
    assert not app.exception
    assert any("已完成" in str(node.value) for node in app.success)
    # Drained once: a later rerun must not repeat it.
    app.run()
    assert not app.success


def test_advanced_is_the_first_expander_and_starts_collapsed() -> None:
    app = _script(
        "import streamlit as st\n"
        "from pattern_reborn.ui import components as ui\n"
        "with ui.advanced():\n"
        "    st.caption('内部说明')\n"
    )
    app.run()
    assert not app.exception
    assert app.expander[0].label == "高级设置"
    assert app.expander[0].proto.expanded is False


def test_kicker_renders_a_bilingual_panel_label() -> None:
    app = _script(
        "from pattern_reborn.ui import components as ui\n"
        "ui.render_kicker('来源图像', 'SOURCE IMAGE')\n"
    )
    app.run()
    assert not app.exception
    markdown = "\n".join(str(node.value) for node in app.markdown)
    assert "panel-kicker" in markdown
    assert "来源图像" in markdown
    assert "SOURCE IMAGE" in markdown
