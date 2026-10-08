# -*- coding: utf-8 -*-
"""Optional drawable-canvas support and its numeric fallback.

The canvas package is an extra dependency, so nothing here may import it at
module scope; :func:`render_canvas` imports it lazily and degrades to a warning
plus the numeric box/point inputs when it is missing. The object-to-hints
mapping is pure and unit-tested directly.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pattern_reborn.capabilities import Capabilities
from pattern_reborn.segmentation import MaskEditMode, MaskStroke, PromptPoint, SegmentHints

CANVAS_FALLBACK_ZH = "未检测到可绘制画布组件，已回退为框选与提示点输入。"
CANVAS_TOOLS = ("点选", "框选", "保留笔刷", "删除笔刷")
CANVAS_SIZE = 360


def hints_from_canvas_objects(raw: object) -> tuple[SegmentHints, list[MaskStroke]]:
    """Map drawable-canvas objects into segmentation hints and mask strokes."""
    objects = _canvas_object_list(raw)
    box: tuple[int, int, int, int] | None = None
    points: list[PromptPoint] = []
    strokes: list[MaskStroke] = []
    for item in objects:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or item.get("className") or "").lower()
        attrs = item.get("attrs") if isinstance(item.get("attrs"), dict) else item
        if not isinstance(attrs, dict):
            continue
        if kind in {"rect", "rectangle"}:
            parsed = _rect_box(attrs)
            if parsed is not None:
                box = parsed
        elif kind in {"circle", "point", "dot"}:
            parsed_point = _point_xy(attrs)
            if parsed_point is not None:
                points.append(PromptPoint(x=parsed_point[0], y=parsed_point[1], keep=True))
        elif kind in {"line", "freedraw"}:
            stroke = _stroke_from_line(attrs)
            if stroke is not None:
                strokes.append(stroke)
    return SegmentHints(box=box, points=tuple(points)), strokes


def _canvas_object_list(raw: object) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    payload = raw
    if not isinstance(payload, dict):
        json_payload = getattr(raw, "json", None)
        objects = getattr(raw, "objects", None)
        if isinstance(json_payload, dict):
            payload = json_payload
        elif isinstance(objects, list):
            return list(objects)
        else:
            return []
    nested = payload.get("json")
    if isinstance(nested, dict) and isinstance(nested.get("objects"), list):
        return list(nested["objects"])
    objects = payload.get("objects")
    return list(objects) if isinstance(objects, list) else []


def _rect_box(attrs: dict) -> tuple[int, int, int, int] | None:
    x = attrs.get("x", attrs.get("left"))
    y = attrs.get("y", attrs.get("top"))
    width = attrs.get("width")
    height = attrs.get("height")
    try:
        left = int(round(float(x)))
        top = int(round(float(y)))
        right = left + int(round(float(width)))
        bottom = top + int(round(float(height)))
    except (TypeError, ValueError, OverflowError):
        return None
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _point_xy(attrs: dict) -> tuple[int, int] | None:
    x = attrs.get("x", attrs.get("left"))
    y = attrs.get("y", attrs.get("top"))
    try:
        return int(round(float(x))), int(round(float(y)))
    except (TypeError, ValueError, OverflowError):
        return None


def _stroke_from_line(attrs: dict) -> MaskStroke | None:
    raw_points = attrs.get("points")
    parsed: list[tuple[int, int]] = []
    if isinstance(raw_points, (list, tuple)) and raw_points:
        if isinstance(raw_points[0], (list, tuple)) and len(raw_points[0]) == 2:
            for item in raw_points:
                try:
                    parsed.append((int(round(float(item[0]))), int(round(float(item[1])))))
                except (TypeError, ValueError, OverflowError, IndexError):
                    return None
        elif all(not isinstance(item, (list, tuple)) for item in raw_points):
            numbers = list(raw_points)
            for index in range(0, len(numbers) - 1, 2):
                try:
                    parsed.append(
                        (int(round(float(numbers[index]))), int(round(float(numbers[index + 1]))))
                    )
                except (TypeError, ValueError, OverflowError, IndexError):
                    return None
    if len(parsed) < 1:
        return None
    width = attrs.get("strokeWidth", attrs.get("width", 3))
    try:
        stroke_width = max(1, int(round(float(width))))
    except (TypeError, ValueError, OverflowError):
        stroke_width = 3
    mode = (
        MaskEditMode.REMOVE
        if str(attrs.get("mode", "")).lower() in {"remove", "erase", "删除"}
        else MaskEditMode.KEEP
    )
    return MaskStroke(mode=mode, points=parsed, width=stroke_width)


def parse_stroke_points(raw: str) -> list[tuple[int, int]]:
    """Parse ``x,y;x,y`` free-text strokes; full-width punctuation is accepted."""
    points: list[tuple[int, int]] = []
    for part in raw.replace("；", ";").split(";"):
        item = part.strip()
        if not item:
            continue
        x_text, y_text = item.replace("，", ",").split(",", 1)
        points.append((int(x_text.strip()), int(y_text.strip())))
    if not points:
        raise ValueError("笔触至少需要一个坐标。")
    return points


def manual_prompt_points(point_x: object, point_y: object, keep_point: object) -> tuple[PromptPoint, ...]:
    """Translate the numeric hint fields, treating the untouched origin as absent."""
    x = int(point_x)
    y = int(point_y)
    keep = bool(keep_point)
    if x == 0 and y == 0 and keep:
        return ()
    return (PromptPoint(x=x, y=y, keep=keep),)


def _load_drawable_canvas():
    from streamlit_drawable_konva import st_canvas

    return st_canvas


def render_canvas(capabilities: Capabilities, source_path: Path | None):
    """Draw the optional canvas, or return ``None`` so callers keep the numeric path."""
    if not capabilities.canvas.available:
        return None
    try:
        renderer = _load_drawable_canvas()
        tool = st.selectbox("画布工具", list(CANVAS_TOOLS))
        drawing_mode = {"点选": "point", "框选": "rect"}.get(tool, "freedraw")
        background = str(source_path) if source_path is not None and source_path.is_file() else None
        result = renderer(
            drawing_mode=drawing_mode,
            key="studio_canvas",
            height=CANVAS_SIZE,
            width=CANVAS_SIZE,
            background_image=background,
        )
        st.session_state["canvas_objects"] = result
        return result
    except Exception:
        st.warning(CANVAS_FALLBACK_ZH)
        return None
