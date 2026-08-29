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


def test_ruyi_cloud_svg_is_original_project_asset() -> None:
    svg = SVG_PATH.read_text(encoding="utf-8")
    assert "Pattern Reborn original asset" in svg
    assert "<path" in svg
    assert "https://" not in svg
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert svg.count("http://") == 1
