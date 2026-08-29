import json

import numpy as np
import pytest

from pattern_reborn.domain import ProfileId
from pattern_reborn.segmentation import (
    MaskEditMode,
    MaskStroke,
    OpenCvSegmenter,
    PromptPoint,
    SegmentationError,
    SegmentHints,
    apply_mask_strokes,
    extract_rgba,
    filter_small_components,
)


@pytest.fixture
def ring_image() -> np.ndarray:
    image = np.full((64, 64, 3), 255, dtype=np.uint8)
    yy, xx = np.ogrid[:64, :64]
    radius_squared = (xx - 32) ** 2 + (yy - 32) ** 2
    image[(12**2 <= radius_squared) & (radius_squared <= 24**2)] = (20, 20, 20)
    return image


@pytest.fixture
def blank_mask() -> np.ndarray:
    return np.zeros((32, 32), dtype=np.uint8)


def test_silhouette_keeps_outer_shape_and_inner_hole(ring_image: np.ndarray) -> None:
    result = OpenCvSegmenter().segment(ring_image, ProfileId.SILHOUETTE, SegmentHints())

    assert result.mask.dtype == np.uint8
    assert result.mask[10, 10] == 0
    assert result.mask[32, 32] == 0
    assert result.mask[20, 32] == 255


def test_flat_color_extracts_the_smaller_lab_color_region() -> None:
    image = np.full((48, 48, 3), (238, 232, 215), dtype=np.uint8)
    image[12:36, 12:36] = (185, 30, 45)

    result = OpenCvSegmenter().segment(image, ProfileId.FLAT_COLOR, SegmentHints())

    assert result.mask[24, 24] == 255
    assert result.mask[4, 4] == 0


def test_textile_suppresses_light_texture_while_keeping_dark_motif() -> None:
    image = np.full((64, 64, 3), (220, 210, 190), dtype=np.uint8)
    image[::2, ::2] = (210, 200, 180)
    image[20:44, 22:42] = (55, 70, 105)

    result = OpenCvSegmenter().segment(image, ProfileId.TEXTILE, SegmentHints())

    assert result.mask[32, 32] == 255
    assert result.mask[4, 4] == 0


def test_artifact_requires_a_roi() -> None:
    image = np.full((48, 48, 3), 220, dtype=np.uint8)

    with pytest.raises(SegmentationError, match="ROI"):
        OpenCvSegmenter().segment(image, ProfileId.ARTIFACT_PHOTO, SegmentHints())


def test_artifact_clips_roi_and_extracts_grabcut_foreground_without_mutating_input() -> None:
    image = np.full((64, 64, 3), (235, 235, 235), dtype=np.uint8)
    image[16:48, 20:44] = (45, 85, 130)
    original = image.copy()

    result = OpenCvSegmenter().segment(
        image,
        ProfileId.ARTIFACT_PHOTO,
        SegmentHints(box=(-8, 8, 52, 56)),
    )

    assert np.array_equal(image, original)
    assert result.mask[32, 32] == 255
    assert result.mask[2, 2] == 0
    assert result.record()["hints"]["box"] == [0, 8, 52, 56]
    assert "roi_clipped" in result.warnings


def test_artifact_rejects_a_roi_that_clips_to_no_area() -> None:
    image = np.full((32, 32, 3), 200, dtype=np.uint8)

    with pytest.raises(SegmentationError, match="ROI"):
        OpenCvSegmenter().segment(
            image,
            ProfileId.ARTIFACT_PHOTO,
            SegmentHints(box=(40, 0, 50, 20)),
        )


def test_box_limits_foreground_to_the_selected_region() -> None:
    image = np.full((48, 48, 3), 255, dtype=np.uint8)
    image[8:18, 8:18] = 20
    image[28:40, 28:40] = 20

    result = OpenCvSegmenter().segment(
        image,
        ProfileId.SILHOUETTE,
        SegmentHints(box=(24, 24, 44, 44)),
    )

    assert result.mask[12, 12] == 0
    assert result.mask[32, 32] == 255


@pytest.mark.parametrize("point", [PromptPoint(8, 8, True), PromptPoint(23, 23, True)])
def test_keep_prompt_at_roi_boundary_cannot_escape_roi(point: PromptPoint) -> None:
    image = np.full((32, 32, 3), (238, 232, 215), dtype=np.uint8)
    image[12:20, 12:20] = (185, 30, 45)

    result = OpenCvSegmenter(minimum_component_area=1).segment(
        image,
        ProfileId.FLAT_COLOR,
        SegmentHints(box=(8, 8, 24, 24), points=[point]),
    )

    assert result.mask[point.y, point.x] == 255
    assert not result.mask[:8].any()
    assert not result.mask[24:].any()
    assert not result.mask[:, :8].any()
    assert not result.mask[:, 24:].any()


def test_non_artifact_profile_allows_a_single_pixel_clipped_region() -> None:
    image = np.full((32, 32, 3), (238, 232, 215), dtype=np.uint8)
    image[8:24, 8:24] = (185, 30, 45)

    result = OpenCvSegmenter(minimum_component_area=1).segment(
        image,
        ProfileId.FLAT_COLOR,
        SegmentHints(box=(16, 16, 17, 17)),
    )

    assert result.mask[16, 16] == 255
    assert result.mask.sum() == 255


@pytest.mark.parametrize(
    "box",
    [42, "abcd", (1, 2, 3), (1, 2, 3, 4, 5), (1, 2, 3, 4.5)],
)
def test_segment_hints_rejects_malformed_box_with_typed_error(box: object) -> None:
    with pytest.raises(SegmentationError):
        SegmentHints(box=box)  # type: ignore[arg-type]


@pytest.mark.parametrize("points", [None, 42, "point", [object()]])
def test_segment_hints_rejects_malformed_points_with_typed_error(points: object) -> None:
    with pytest.raises(SegmentationError):
        SegmentHints(points=points)  # type: ignore[arg-type]


def test_extract_rgba_preserves_source_rgb_and_uses_binary_mask_as_alpha() -> None:
    image = np.array([[[12, 34, 56], [78, 90, 123]]], dtype=np.uint8)
    mask = np.array([[0, 255]], dtype=np.uint8)
    image_before = image.copy()
    mask_before = mask.copy()

    rgba = extract_rgba(image, mask)

    assert rgba.mode == "RGBA"
    assert np.array_equal(np.asarray(rgba), np.array([[[12, 34, 56, 0], [78, 90, 123, 255]]], dtype=np.uint8))
    assert np.array_equal(image, image_before)
    assert np.array_equal(mask, mask_before)


def test_filter_small_components_discards_isolated_noise() -> None:
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[2, 2] = 255
    mask[8:12, 8:12] = 255

    filtered = filter_small_components(mask, minimum_area=4)

    assert filtered[2, 2] == 0
    assert filtered[9, 9] == 255
    assert mask[2, 2] == 255


def test_keep_and_remove_strokes_are_applied_in_order(blank_mask: np.ndarray) -> None:
    edits = [
        MaskStroke(MaskEditMode.KEEP, [(10, 10), (20, 10)], 5),
        MaskStroke(MaskEditMode.REMOVE, [(15, 10)], 3),
    ]

    edited = apply_mask_strokes(blank_mask, edits)

    assert edited[10, 10] == 255
    assert edited[10, 15] == 0
    assert blank_mask.max() == 0


def test_mask_strokes_round_trip_through_json_including_prompt_points() -> None:
    hints = SegmentHints(
        box=(1, 2, 30, 40),
        points=[PromptPoint(3, 4, True), PromptPoint(8, 9, False)],
    )
    strokes = [
        MaskStroke(MaskEditMode.KEEP, [(1, 2), (3, 4)], 7),
        MaskStroke(MaskEditMode.REMOVE, [(5, 6)], 3),
    ]

    restored_hints = SegmentHints.from_record(json.loads(json.dumps(hints.record())))
    restored_strokes = [MaskStroke.from_record(item) for item in json.loads(json.dumps([stroke.record() for stroke in strokes]))]

    assert restored_hints == hints
    assert restored_strokes == strokes


def test_result_records_profile_parameters_hints_version_and_warnings() -> None:
    image = np.full((32, 32, 3), 255, dtype=np.uint8)
    image[8:24, 8:24] = 0

    result = OpenCvSegmenter(minimum_component_area=3).segment(
        image,
        ProfileId.SILHOUETTE,
        SegmentHints(points=[PromptPoint(12, 12, True)]),
    )

    record = result.record()
    assert record["profile"] == ProfileId.SILHOUETTE.value
    assert record["parameters"]["minimum_component_area"] == 3
    assert record["hints"]["points"] == [{"x": 12, "y": 12, "keep": True}]
    assert record["algorithm_version"].startswith("opencv-baseline-")
    assert record["warnings"] == []
    assert result.rgba.mode == "RGBA"
