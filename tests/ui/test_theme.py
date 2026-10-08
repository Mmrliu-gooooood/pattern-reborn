# -*- coding: utf-8 -*-
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS_PATH = REPO_ROOT / "src" / "pattern_reborn" / "ui" / "assets" / "theme.css"
SVG_PATH = REPO_ROOT / "src" / "pattern_reborn" / "ui" / "assets" / "ruyi_cloud.svg"


def test_theme_has_no_diagonal_or_remote_background_assets() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "repeating-linear-gradient" not in css
    assert "http://" not in css and "https://" not in css
    assert "--ink-green" in css and "--vermilion" in css and "--gilded-gold" in css


def test_theme_uses_two_non_directional_radial_gradients() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    assert css.count("radial-gradient") == 2
    assert "repeating-radial-gradient" not in css
    assert "linear-gradient" not in css


def test_theme_neutralises_streamlit_markdown_container_margin() -> None:
    """Panels here are raw HTML, so Streamlit's negative markdown margin must go.

    Streamlit ends every markdown block with ``margin-bottom: -1rem`` to cancel a
    trailing ``<p>`` margin. Blocks composed from ``<div>``s have no such margin,
    so the negative value silently shortened the container by 16px and the next
    element (a card image, a card button) was painted over the text.
    """
    css = CSS_PATH.read_text(encoding="utf-8")
    container_rule = css.split('[data-testid="stMarkdownContainer"] {', 1)[1].split("}", 1)[0]
    assert "margin-bottom: 0 !important" in container_rule
    trailing_paragraph = css.split(
        '[data-testid="stMarkdownContainer"] > p:last-child {', 1
    )[1].split("}", 1)[0]
    assert "margin-bottom: 0 !important" in trailing_paragraph


def test_sidebar_rail_targets_the_markup_streamlit_actually_renders() -> None:
    """Streamlit 1.62 emits no `role="radio"`, so the rail styling is lost.

    Each option is `label[data-testid="stRadioOption"]` with `data-selected` on
    the active one. A rule keyed on `[role="radio"]` matches nothing and the
    active dot silently keeps the theme's gold instead of cinnabar.
    """
    css = CSS_PATH.read_text(encoding="utf-8")
    rail = css.split("/* Step rail:", 1)[1].split("/* -------------------------------------------------------- 3.", 1)[0]
    assert '[role="radio"]' not in rail
    assert '[data-testid="stRadioOption"]' in rail
    assert '[data-selected="true"]' in rail
    assert "var(--vermilion)" in rail


def test_ruyi_cloud_svg_is_original_project_asset() -> None:
    svg = SVG_PATH.read_text(encoding="utf-8")
    assert "Pattern Reborn original asset" in svg
    assert "<path" in svg
    assert "https://" not in svg
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert svg.count("http://") == 1
