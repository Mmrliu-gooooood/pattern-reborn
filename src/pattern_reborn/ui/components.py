# -*- coding: utf-8 -*-
"""Reusable layout primitives for the studio screens.

Layout rules live here so individual steps cannot drift apart:

* every step is a ``workbench`` (bounded images) beside a ``controls`` panel,
  created at the same ratio by :func:`two_panel_step`;
* every step opens with a semantic ``<section class="studio-header">`` H1;
* algorithm parameters live in a collapsed ``高级设置`` expander that is always
  the **first** expander on the page;
* every step ends with the same action bar, rendered through a keyed container
  so Streamlit's element containers can actually wrap it in a bordered strip.

The ``workbench``/``controls``/``action-bar`` surfaces are keyed containers
rather than hand-written HTML wrappers, because Streamlit closes every
``st.markdown`` call inside its own element container, so an HTML ``<div>`` can
never wrap a widget. See ``assets/theme.css`` for the matching selectors.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import streamlit as st

from pattern_reborn.domain import StepId
from pattern_reborn.ui.labels import STEP_GOALS, step_eyebrow, step_label

# Standard workbench / control-panel ratio. Every step uses this pair so the
# image column keeps the same width as the user walks through the workflow.
WORKBENCH_RATIO = (1.25, 0.95)


def escape(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def two_panel_step(step_key: str, ratio: tuple[float, float] = WORKBENCH_RATIO):
    """Return the ``(workbench, controls)`` containers for one step.

    Both are keyed containers so the stylesheet can draw a bordered surface that
    genuinely encloses the widgets placed inside them.
    """
    workbench_column, controls_column = st.columns(list(ratio), gap="large")
    with workbench_column:
        workbench = st.container(key=f"workbench-{step_key}")
    with controls_column:
        controls = st.container(key=f"controls-{step_key}")
    return workbench, controls


def render_step_header(step: StepId, project_name: str | None) -> None:
    context = f"创作工坊 · {escape(step_eyebrow(step))}"
    if project_name:
        context = f"{context} · {escape(project_name)}"
    st.markdown(
        f'<section class="studio-header"><div class="studio-header__step">{context}</div>'
        f"<h1>{escape(step_label(step))}</h1>"
        f"<p>{escape(STEP_GOALS.get(step, ''))}</p></section>",
        unsafe_allow_html=True,
    )


def render_kicker(title_zh: str, title_en: str = "") -> None:
    english = f'<span class="panel-kicker__en">{escape(title_en)}</span>' if title_en else ""
    st.markdown(
        f'<div class="panel-kicker"><span>{escape(title_zh)}</span>{english}</div>',
        unsafe_allow_html=True,
    )


def render_divider() -> None:
    st.markdown('<div class="panel-divider"></div>', unsafe_allow_html=True)


def render_note(text: str) -> None:
    st.markdown(f'<p class="panel-note">{escape(text)}</p>', unsafe_allow_html=True)


@contextmanager
def advanced(expanded: bool = False) -> Iterator[None]:
    """Collapsed algorithm settings. Always the first expander on a step."""
    with st.expander("高级设置", expanded=expanded):
        yield


def action_bar(key: str, note_ratio: float = 2.6):
    """Standard bottom bar, drawn as one bordered strip.

    Returns ``(note_column, action_column)`` at a fixed ratio so every step's
    primary action sits in the same place. Callers nest their own buttons
    inside ``action_column``.
    """
    container = st.container(key=f"action-bar-{key}")
    with container:
        note_column, action_column = st.columns([note_ratio, 1.0], gap="medium")
    return note_column, action_column


def render_action_note(text: str) -> None:
    st.markdown(f'<div class="action-note">{text}</div>', unsafe_allow_html=True)


def render_flash() -> None:
    """Drain queued post-rerun messages.

    ``st.success`` immediately before ``st.rerun`` is never seen, so mutating
    steps queue a message instead and it is drained at the top of the next run.
    """
    for message in st.session_state.pop("flash_messages", []):
        kind = str(message.get("kind", "success"))
        renderer = getattr(st, kind, st.success)
        renderer(str(message.get("text", "")))


def flash(text: str, kind: str = "success") -> None:
    st.session_state.setdefault("flash_messages", []).append({"text": text, "kind": kind})


def render_image_panel(path: Path, caption: str, badge: str | None = None) -> None:
    """Bounded, captioned image with an optional cinnabar badge such as ``AI 生成``."""
    st.image(str(path), width="stretch")
    badge_html = f'<span class="ai-badge">{escape(badge)}</span>' if badge else ""
    st.markdown(
        f'<div class="result-caption"><b>{escape(caption)}</b>{badge_html}</div>',
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, note: str) -> None:
    st.markdown(
        f'<div class="empty-state"><b>{escape(title)}</b>{escape(note)}</div>',
        unsafe_allow_html=True,
    )


def _metric_cell(label: str, value: str, note: str) -> str:
    note_html = f'<div class="metric-card__note">{escape(note)}</div>' if note else ""
    return (
        f'<div class="metric-card"><div class="metric-card__label">{escape(label)}</div>'
        f'<div class="metric-card__value">{escape(value)}</div>{note_html}</div>'
    )


def render_metric_grid(cards: list[tuple[str, str, str]]) -> None:
    """One grid for every metric so cards cannot reflow between reruns."""
    if not cards:
        return
    cells = "".join(_metric_cell(label, value, note) for label, value, note in cards)
    st.markdown(f'<div class="metric-grid">{cells}</div>', unsafe_allow_html=True)


def render_palette(colors: list[dict[str, object]]) -> None:
    """Swatch grid for k-means palette entries (``hex_value``/``coverage``/``pixel_count``)."""
    if not colors:
        return
    cells = "".join(
        '<div class="swatch">'
        f'<div class="swatch__chip" style="background:{escape(color["hex_value"])}"></div>'
        f'<div><div class="swatch__hex">{escape(color["hex_value"])}</div>'
        f'<div class="swatch__meta">覆盖 {float(color["coverage"]):.1%} · {int(color["pixel_count"])} px</div>'
        "</div></div>"
        for color in colors
    )
    st.markdown(f'<div class="swatch-grid">{cells}</div>', unsafe_allow_html=True)


def render_color_matches(matches: list[dict[str, object]]) -> None:
    """Traditional-colour matches as a compact bordered list."""
    if not matches:
        return
    rows = "".join(
        '<div class="match-row">'
        f'<span class="match-row__dot" style="background:{escape(match["hex_value"])}"></span>'
        f'<span class="match-row__name">{escape(match["traditional_name_zh"])}</span>'
        f'<span class="match-row__meta">{escape(match["hex_value"])} · ΔE {float(match["distance"]):.1f}</span>'
        "</div>"
        for match in matches
    )
    st.markdown(rows, unsafe_allow_html=True)
