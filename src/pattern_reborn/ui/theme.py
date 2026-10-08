# -*- coding: utf-8 -*-
"""Sidebar shell and injected stylesheet.

The brand block is composed in one place so the home and studio routes show the
same chrome; only the step rail is studio-specific.
"""

from pathlib import Path

import streamlit as st

from pattern_reborn.ui.labels import STEP_LABELS

_ASSETS = Path(__file__).resolve().parent / "assets"

_BRAND_LOCKUP = (
    '<div class="brand-lockup">'
    '<div class="brand-seal">纹</div>'
    '<div><div class="brand-title">纹启新生</div>'
    '<div class="brand-english">PATTERN REBORN</div></div>'
    "</div>"
)


def load_theme_css() -> str:
    return (_ASSETS / "theme.css").read_text(encoding="utf-8")


def load_ruyi_cloud_svg() -> str:
    return (_ASSETS / "ruyi_cloud.svg").read_text(encoding="utf-8")


def apply_theme() -> None:
    st.markdown(f"<style>{load_theme_css()}</style>", unsafe_allow_html=True)


def render_shell_chrome() -> None:
    """Brand block shared by every route. Called once from ``app.main``."""
    apply_theme()
    with st.sidebar:
        st.markdown(_BRAND_LOCKUP, unsafe_allow_html=True)
        st.markdown(
            f'<div class="ruyi-ornament">{load_ruyi_cloud_svg()}</div>'
            '<div class="heritage-seal">非遗纹启</div>',
            unsafe_allow_html=True,
        )


def render_step_rail(active_label: str) -> None:
    """Gilded progress rail with one dot per studio step."""
    position = STEP_LABELS.index(active_label) + 1 if active_label in STEP_LABELS else 1
    st.markdown(
        f'<div class="progress-label">创作进度 · <b>{position:02d} / {len(STEP_LABELS):02d}</b></div>',
        unsafe_allow_html=True,
    )
    st.radio(
        "创作步骤",
        STEP_LABELS,
        key="studio_step",
        label_visibility="collapsed",
    )


def render_sidebar_footer() -> None:
    """Closing note rendered on every route so the sidebar never looks truncated."""
    with st.sidebar:
        st.markdown(
            '<div class="side-footer">▣ 本地项目与溯源导出<br>▣ 除付费生成外均可离线完成</div>',
            unsafe_allow_html=True,
        )
