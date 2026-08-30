"""Shared pre-allocation limits for image-processing operations."""

import math


MAX_SOURCE_PIXELS = 16_777_216
MAX_CANVAS_PIXELS = 16_777_216
MAX_CANVAS_EDGE = 8_192
MAX_INTERMEDIATE_PIXELS = 4_194_304
MAX_INTERMEDIATE_EDGE = 8_192


class ImageLimitError(ValueError):
    """图像尺寸或缩放参数超出安全处理范围。"""


def require_bounded_size(
    width: object,
    height: object,
    *,
    label: str,
    max_edge: int,
    max_pixels: int,
) -> tuple[int, int]:
    """Return a strict positive size when it fits the supplied budgets."""
    if isinstance(width, bool) or isinstance(height, bool):
        raise ImageLimitError(f"{label}必须为正整数。")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ImageLimitError(f"{label}必须为正整数。")
    if width > max_edge or height > max_edge or width * height > max_pixels:
        raise ImageLimitError(f"{label}超出安全上限。")
    return width, height


def require_scaled_size(
    width: object,
    height: object,
    scale: object,
    *,
    label: str,
    max_pixels: int,
) -> tuple[int, int]:
    """Return rounded scaled dimensions when the result is safe to allocate."""
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
    ):
        raise ImageLimitError(f"{label}必须为正整数。")
    if (
        isinstance(scale, bool)
        or not isinstance(scale, (int, float))
        or not math.isfinite(scale)
        or scale <= 0
    ):
        raise ImageLimitError(f"{label}缩放比例必须为正的有限数值。")

    try:
        scaled_width_value = width * scale
        scaled_height_value = height * scale
    except OverflowError as error:
        raise ImageLimitError(f"{label}超出安全上限。") from error
    if not math.isfinite(scaled_width_value) or not math.isfinite(scaled_height_value):
        raise ImageLimitError(f"{label}超出安全上限。")

    scaled_width = max(1, round(scaled_width_value))
    scaled_height = max(1, round(scaled_height_value))
    return require_bounded_size(
        scaled_width,
        scaled_height,
        label=label,
        max_edge=MAX_INTERMEDIATE_EDGE,
        max_pixels=max_pixels,
    )
