# -*- coding: utf-8 -*-
"""Pure mapping helpers behind the optional drawable canvas.

The canvas package is an extra, so these run against the plain data shapes the
renderer hands back rather than against a live canvas.
"""

from __future__ import annotations

import pytest

from pattern_reborn.segmentation import MaskEditMode, PromptPoint
from pattern_reborn.ui.canvas import (
    CANVAS_FALLBACK_ZH,
    hints_from_canvas_objects,
    manual_prompt_points,
    parse_stroke_points,
)


def test_hints_from_canvas_objects_maps_rect_points_and_strokes() -> None:
    hints, strokes = hints_from_canvas_objects(
        {
            "objects": [
                {"type": "rect", "x": 10, "y": 20, "width": 30, "height": 40},
                {"type": "circle", "x": 15, "y": 25},
                {"type": "line", "points": [[1, 2], [3, 4]], "strokeWidth": 5},
            ]
        }
    )
    assert hints.box == (10, 20, 40, 60)
    assert PromptPoint(15, 25, True) in hints.points
    assert len(strokes) == 1
    assert tuple(strokes[0].points) == ((1, 2), (3, 4))
    assert strokes[0].width == 5
    assert strokes[0].mode is MaskEditMode.KEEP


def test_hints_from_canvas_objects_accepts_a_freedraw_flat_point_list() -> None:
    hints, strokes = hints_from_canvas_objects(
        {"objects": [{"type": "freedraw", "points": [1, 2, 3, 4], "mode": "erase"}]}
    )
    assert hints.box is None
    assert tuple(strokes[0].points) == ((1, 2), (3, 4))
    assert strokes[0].mode is MaskEditMode.REMOVE


def test_hints_from_canvas_objects_handles_nested_and_object_shaped_payloads() -> None:
    nested = {"json": {"objects": [{"type": "rect", "left": 5, "top": 6, "width": 7, "height": 8}]}}
    hints, _ = hints_from_canvas_objects(nested)
    assert hints.box == (5, 6, 12, 14)

    class _Payload:
        objects = [{"type": "rect", "x": 0, "y": 0, "width": 2, "height": 2}]

    hints, _ = hints_from_canvas_objects(_Payload())
    assert hints.box == (0, 0, 2, 2)


@pytest.mark.parametrize(
    "raw",
    [None, [], {}, "text", {"objects": "not-a-list"}, [1, 2, 3], {"objects": [{"width": 5}]}],
)
def test_hints_from_canvas_objects_ignores_unusable_payloads(raw: object) -> None:
    hints, strokes = hints_from_canvas_objects(raw)
    assert hints.box is None
    assert hints.points == ()
    assert strokes == []


def test_degenerate_and_non_numeric_rectangles_are_rejected() -> None:
    for attrs in (
        {"x": 5, "y": 5, "width": 0, "height": 10},
        {"x": 5, "y": 5, "width": 10, "height": 0},
        {"x": "a", "y": 5, "width": 10, "height": 10},
        {"width": 10, "height": 10},
    ):
        hints, _ = hints_from_canvas_objects({"objects": [{"type": "rect", **attrs}]})
        assert hints.box is None, attrs


def test_parse_stroke_points_accepts_ascii_and_full_width_punctuation() -> None:
    assert parse_stroke_points("1,2;3,4") == [(1, 2), (3, 4)]
    assert parse_stroke_points("1，2；3，4") == [(1, 2), (3, 4)]
    assert parse_stroke_points(" 1,2 ; ; 3,4 ") == [(1, 2), (3, 4)]


@pytest.mark.parametrize("raw", ["", "   ", ";", ";;"])
def test_parse_stroke_points_rejects_an_empty_definition(raw: str) -> None:
    with pytest.raises(ValueError, match="笔触至少需要一个坐标"):
        parse_stroke_points(raw)


def test_manual_prompt_points_treats_the_untouched_origin_as_absent() -> None:
    assert manual_prompt_points(0, 0, True) == ()
    assert manual_prompt_points(0, 0, False) == (PromptPoint(0, 0, False),)
    assert manual_prompt_points(4, 9, True) == (PromptPoint(4, 9, True),)


def test_canvas_fallback_copy_stays_in_chinese() -> None:
    assert "画布" in CANVAS_FALLBACK_ZH
