# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pattern_reborn.domain import ProfileId
from pattern_reborn.segmentation import (
    MobileSamSegmenter,
    PromptPoint,
    SegmentHints,
    Segmenter,
)


class FakePredictor:
    def __init__(self) -> None:
        self.image: np.ndarray | None = None
        self.calls: list[dict[str, Any]] = []

    def set_image(self, image: np.ndarray) -> None:
        self.image = np.asarray(image)

    def predict(self, **kwargs: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        self.calls.append(kwargs)
        assert self.image is not None
        height, width = self.image.shape[:2]
        mask = np.zeros((height, width), dtype=bool)
        box = kwargs.get("box")
        if box is not None:
            coords = np.asarray(box).reshape(-1)
            left, top, right, bottom = (int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3]))
            mask[top:bottom, left:right] = True
        return mask[None, ...], np.array([0.91], dtype=np.float32), np.zeros((1, 8, 8), dtype=np.float32)


@pytest.fixture
def fake_predictor() -> FakePredictor:
    return FakePredictor()


@pytest.fixture
def image() -> np.ndarray:
    rgb = np.full((48, 48, 3), 220, dtype=np.uint8)
    rgb[10:38, 10:38] = (40, 80, 120)
    return rgb


def test_mobile_sam_adapter_accepts_box_and_points(fake_predictor, image) -> None:
    result = MobileSamSegmenter(fake_predictor).segment(
        image, ProfileId.ARTIFACT_PHOTO,
        SegmentHints(box=(5, 5, 40, 40), points=[PromptPoint(20, 20, True)]),
    )
    assert result.mask.shape == image.shape[:2]


def test_mobile_sam_adapter_forwards_box_and_points_without_mutating_image(
    fake_predictor: FakePredictor, image: np.ndarray
) -> None:
    original = image.copy()
    hints = SegmentHints(box=(5, 5, 40, 40), points=[PromptPoint(20, 20, True), PromptPoint(6, 6, False)])

    result = MobileSamSegmenter(fake_predictor).segment(image, ProfileId.ARTIFACT_PHOTO, hints)

    assert np.array_equal(image, original)
    assert fake_predictor.image is not None
    assert fake_predictor.calls
    call = fake_predictor.calls[-1]
    box = np.asarray(call["box"]).reshape(-1)
    assert list(box[:4]) == [5, 5, 40, 40]
    coords = np.asarray(call["point_coords"])
    labels = np.asarray(call["point_labels"])
    assert coords.tolist() == [[20, 20], [6, 6]]
    assert labels.tolist() == [1, 0]
    assert result.mask.dtype == np.uint8
    assert set(np.unique(result.mask)).issubset({0, 255})
    assert result.mask[20, 20] == 255
    assert result.mask[2, 2] == 0
    assert result.rgba.mode == "RGBA"
    assert result.profile is ProfileId.ARTIFACT_PHOTO
    assert result.hints == hints


def test_mobile_sam_segmenter_satisfies_segmenter_protocol(
    fake_predictor: FakePredictor, image: np.ndarray
) -> None:
    segmenter: Segmenter = MobileSamSegmenter(fake_predictor)
    result = segmenter.segment(
        image,
        ProfileId.ARTIFACT_PHOTO,
        SegmentHints(box=(8, 8, 32, 32), points=[PromptPoint(12, 12, True)]),
    )
    assert result.mask.shape == (48, 48)
    assert result.algorithm_version.startswith("mobile-sam")
