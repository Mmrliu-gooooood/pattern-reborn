# -*- coding: utf-8 -*-
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).resolve().parent / "assets"


def load_theme_css() -> str:
    return (_ASSETS / "theme.css").read_text(encoding="utf-8")


def load_ruyi_cloud_svg() -> str:
    return (_ASSETS / "ruyi_cloud.svg").read_text(encoding="utf-8")


def apply_theme() -> None:
    st.markdown(f"<style>{load_theme_css()}</style>", unsafe_allow_html=True)


def render_shell_chrome() -> None:
    apply_theme()
    with st.sidebar:
        st.markdown(
            f'<div class="ruyi-ornament">{load_ruyi_cloud_svg()}</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="heritage-seal">非遗纹启</div>', unsafe_allow_html=True)
        st.markdown("纹启新生")
