import pytest

from pattern_reborn.limits import (
    MAX_CANVAS_EDGE,
    MAX_CANVAS_PIXELS,
    ImageLimitError,
    require_bounded_size,
    require_scaled_size,
)


def test_bounded_size_enforces_strict_edge_and_pixel_limits() -> None:
    assert require_bounded_size(
        4_096,
        4_096,
        label="画布尺寸",
        max_edge=MAX_CANVAS_EDGE,
        max_pixels=MAX_CANVAS_PIXELS,
    ) == (4_096, 4_096)

    invalid_sizes = [
        (True, 1, "正整数"),
        ("1", 1, "正整数"),
        (0, 1, "正整数"),
        (MAX_CANVAS_EDGE + 1, 1, "安全上限"),
        (4_097, 4_096, "安全上限"),
    ]
    for width, height, message in invalid_sizes:
        with pytest.raises(ImageLimitError, match=message):
            require_bounded_size(
                width,
                height,
                label="画布尺寸",
                max_edge=MAX_CANVAS_EDGE,
                max_pixels=MAX_CANVAS_PIXELS,
            )


def test_scaled_size_rejects_coerced_non_finite_and_oversized_results() -> None:
    assert require_scaled_size(
        1_024,
        1_024,
        2.0,
        label="缩放图像",
        max_pixels=4_194_304,
    ) == (2_048, 2_048)

    invalid_scales = [
        (True, "缩放比例"),
        ("2", "缩放比例"),
        (float("inf"), "缩放比例"),
        (1e308, "安全上限"),
        (2.001, "安全上限"),
    ]
    for scale, message in invalid_scales:
        with pytest.raises(ImageLimitError, match=message):
            require_scaled_size(
                1_024,
                1_024,
                scale,
                label="缩放图像",
                max_pixels=4_194_304,
            )


def test_scaled_size_maps_enormous_integer_scale_to_typed_limit_error() -> None:
    with pytest.raises(ImageLimitError, match="缩放图像.*安全上限"):
        require_scaled_size(
            1,
            1,
            10**10000,
            label="缩放图像",
            max_pixels=4_194_304,
        )
