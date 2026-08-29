import math

import numpy as np
import pytest

from pattern_reborn.preprocess import (
    PreprocessError,
    PreprocessSettings,
    crop,
    enhance,
    perspective_correct,
)


def test_crop_returns_a_normalized_rgb_copy() -> None:
    source = np.zeros((10, 12, 4), dtype=np.uint16)
    source[..., 0] = 255
    source[..., 1] = 128
    source[..., 3] = 99
    before = source.copy()

    result = crop(source, (2, 3, 9, 8))

    assert result.shape == (5, 7, 3)
    assert result.dtype == np.uint8
    assert result[0, 0].tolist() == [255, 128, 0]
    assert np.array_equal(source, before)


@pytest.mark.parametrize(
    "box",
    [
        (2, 2, 2, 7),
        (-1, 0, 4, 4),
        (0, 0, 13, 4),
        (0, 0, math.nan, 4),
    ],
)
def test_crop_rejects_unordered_or_out_of_bounds_boxes(box: tuple[float, float, float, float]) -> None:
    source = np.zeros((10, 12, 3), dtype=np.uint8)

    with pytest.raises(PreprocessError, match="裁剪"):
        crop(source, box)  # type: ignore[arg-type]


def test_perspective_transform_returns_requested_size() -> None:
    source = np.zeros((120, 160, 3), dtype=np.uint8)
    points = [(10, 10), (150, 15), (145, 110), (15, 105)]

    result = perspective_correct(source, points, output_size=(100, 80))

    assert result.shape == (80, 100, 3)
    assert result.dtype == np.uint8


@pytest.mark.parametrize(
    ("points", "output_size"),
    [
        ([(10, 10), (15, 105), (145, 110), (150, 15)], (100, 80)),
        ([(10, 10), (150, 15), (145, 110), (170, 105)], (100, 80)),
        ([(10, 10), (150, 15), (145, math.inf), (15, 105)], (100, 80)),
        ([(10, 10), (150, 15), (145, 110), (15, 105)], (0, 80)),
        ([(10, 10), (150, 15), (145, 110), (15, 105)], (100, math.inf)),
    ],
)
def test_perspective_transform_rejects_invalid_points_or_output_size(
    points: list[tuple[float, float]], output_size: tuple[float, float]
) -> None:
    source = np.zeros((120, 160, 3), dtype=np.uint8)

    with pytest.raises(PreprocessError, match="透视"):
        perspective_correct(source, points, output_size=output_size)  # type: ignore[arg-type]


def test_enhance_is_deterministic_and_does_not_mutate_input() -> None:
    y, x = np.indices((32, 32))
    source = np.stack(((x * 7) % 256, (y * 9) % 256, ((x + y) * 5) % 256), axis=-1).astype(
        np.uint8
    )
    before = source.copy()
    settings = PreprocessSettings(
        white_balance_strength=0.15,
        denoise_strength=3,
        clahe_clip_limit=1.25,
        clahe_tile_grid_size=(4, 4),
    )

    first = enhance(source, settings)
    second = enhance(source, settings)

    assert first.dtype == np.uint8
    assert first.shape == (32, 32, 3)
    assert np.array_equal(first, second)
    assert np.array_equal(source, before)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"white_balance_strength": -0.1},
        {"denoise_strength": -1},
        {"clahe_clip_limit": 0.0},
        {"clahe_tile_grid_size": (0, 4)},
    ],
)
def test_enhancement_settings_reject_unsafe_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(PreprocessError, match="增强"):
        PreprocessSettings(**kwargs)
