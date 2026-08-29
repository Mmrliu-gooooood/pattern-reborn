import math

import numpy as np
import pytest
from PIL import Image

from pattern_reborn.analysis import (
    AnalysisError,
    PaletteColor,
    analyze_contours,
    analyze_palette,
    analyze_symmetry,
    match_traditional_colors,
)
from pattern_reborn.knowledge import TraditionalColor


@pytest.fixture
def two_color_rgba() -> Image.Image:
    """Three opaque red pixels, one opaque blue pixel, and transparent green."""
    return Image.fromarray(
        np.array(
            [
                [[255, 0, 0, 255], [255, 0, 0, 255], [0, 0, 255, 255]],
                [[255, 0, 0, 255], [0, 255, 0, 0], [0, 255, 0, 0]],
            ],
            dtype=np.uint8,
        ),
    )


@pytest.fixture
def symmetric_mask() -> np.ndarray:
    mask = np.zeros((11, 13), dtype=np.uint8)
    mask[2:9, 5:8] = 255
    mask[4:7, 3:10] = 255
    return mask


def test_palette_is_seeded_sorted_and_excludes_fully_transparent_pixels(
    two_color_rgba: Image.Image,
) -> None:
    """A transparent-only color must not alter palette coverage or centers."""
    before = np.asarray(two_color_rgba).copy()

    first = analyze_palette(two_color_rgba, count=2, seed=2026)
    second = analyze_palette(two_color_rgba, count=2, seed=2026)

    assert first == second
    assert [(color.rgb, color.pixel_count, color.coverage) for color in first] == [
        ((255, 0, 0), 3, 0.75),
        ((0, 0, 255), 1, 0.25),
    ]
    assert np.array_equal(np.asarray(two_color_rgba), before)


def test_palette_breaks_equal_coverage_ties_by_rgb() -> None:
    """Changing k-means label order must not change the public result order."""
    image = Image.fromarray(np.array([[[0, 0, 255], [255, 0, 0]]], dtype=np.uint8))

    palette = analyze_palette(image, count=2, seed=7)

    assert [item.rgb for item in palette] == [(0, 0, 255), (255, 0, 0)]


@pytest.mark.parametrize(
    ("image", "count", "seed"),
    [
        (Image.new("L", (1, 1)), 1, 1),
        (Image.new("RGB", (1, 1)), 0, 1),
        (Image.new("RGB", (1, 1)), 1, True),
        (Image.new("RGBA", (1, 1), (1, 2, 3, 0)), 1, 1),
        (Image.new("RGB", (1, 1), (1, 2, 3)), 2, 1),
    ],
)
def test_palette_rejects_invalid_or_insufficient_samples_with_typed_chinese_safe_error(
    image: Image.Image, count: object, seed: object
) -> None:
    """Invalid palette inputs must become user-safe public errors, not OpenCV errors."""
    with pytest.raises(AnalysisError) as raised:
        analyze_palette(image, count=count, seed=seed)  # type: ignore[arg-type]

    assert str(raised.value)
    assert "Traceback" not in str(raised.value)


def test_traditional_color_matching_uses_shared_lab_space_and_numeric_distance() -> None:
    """A catalog entry with the same RGB has zero Lab distance and wins."""
    exact = _traditional_color("exact", "精确", "#B2372D")
    other = _traditional_color("other", "其他", "#1F3A5F")

    matches = match_traditional_colors(
        [PaletteColor(rgb=(178, 55, 45), pixel_count=4, coverage=1.0)],
        [other, exact],
    )

    assert matches[0].traditional_color == exact
    assert matches[0].distance == pytest.approx(0.0, abs=1e-6)


def test_contours_report_external_count_holes_all_perimeter_and_pixel_area() -> None:
    """A ring is one external contour plus one hole, while area counts foreground pixels."""
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[1:9, 1:9] = 255
    mask[3:7, 3:7] = 0
    before = mask.copy()

    report = analyze_contours(mask)

    assert report.contour_count == 1
    assert report.hole_count == 1
    assert report.foreground_area == 48
    assert report.foreground_ratio == pytest.approx(0.48)
    expected_perimeter = 40.0 + 4.0 * math.sqrt(2.0)
    assert report.total_perimeter == pytest.approx(expected_perimeter)
    assert report.complexity == pytest.approx(
        expected_perimeter**2 / (4.0 * math.pi * 48.0)
    )
    assert np.array_equal(mask, before)


def test_contours_reject_non_binary_masks_with_typed_error() -> None:
    with pytest.raises(AnalysisError, match="蒙版"):
        analyze_contours(np.array([[1]], dtype=np.uint8))


def test_symmetry_centers_foreground_before_flip_and_sorts_all_rotation_orders(
    symmetric_mask: np.ndarray,
) -> None:
    """Translation in a larger canvas must not lower bilateral symmetry."""
    translated = np.zeros((21, 27), dtype=np.uint8)
    translated[7:18, 10:23] = symmetric_mask
    before = translated.copy()

    report = analyze_symmetry(translated)

    assert report.vertical_score == pytest.approx(1.0)
    assert report.horizontal_score == pytest.approx(1.0)
    assert {candidate.order for candidate in report.rotations} == {2, 3, 4, 6, 8}
    assert list(report.rotations) == sorted(
        report.rotations, key=lambda candidate: (-candidate.score, candidate.order)
    )
    assert np.array_equal(translated, before)


def test_symmetry_rejects_an_empty_mask_with_typed_error() -> None:
    with pytest.raises(AnalysisError, match="前景"):
        analyze_symmetry(np.zeros((3, 3), dtype=np.uint8))


def _traditional_color(slug: str, name_zh: str, hex_value: str) -> TraditionalColor:
    return TraditionalColor(
        slug=slug,
        name_zh=name_zh,
        hex_value=hex_value,
        reference_title="测试参考",
        reference_bibliography="测试书目",
        digital_value_note_zh="数字色值为本平台近似，非通用标准。",
    )
