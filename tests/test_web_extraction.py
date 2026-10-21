"""Quality fixtures are generated locally and use no model or network service."""
import cv2
import numpy as np
import pytest
from pathlib import Path
from pydantic import ValidationError

from pattern_reborn.domain import ProfileId
from pattern_reborn.segmentation import (
    MaskEditMode, MaskStroke, OpenCvSegmenter, SegmentHints, SegmentationError,
)
from pattern_reborn.web_extraction import ExtractionSettings, extract_local, extraction_capabilities


def noisy_paper():
    rng = np.random.default_rng(622)
    # A textured photograph whose luminance overlaps the red paper.
    coarse = rng.integers(45, 190, (9, 12), dtype=np.uint8)
    noise = cv2.resize(coarse, (180, 144), interpolation=cv2.INTER_CUBIC)
    noise = np.clip(noise.astype(np.int16) + rng.integers(-12, 13, noise.shape), 0, 255).astype(np.uint8)
    rgb = np.repeat(noise[:, :, None], 3, axis=2)
    target = np.zeros(rgb.shape[:2], np.uint8)
    cv2.circle(target, (90, 70), 44, 255, -1)
    cv2.rectangle(target, (83, 104), (97, 130), 255, -1)
    cv2.circle(target, (90, 70), 12, 0, -1)
    colored = np.stack((rng.integers(165, 220, target.shape),
                        rng.integers(25, 48, target.shape),
                        rng.integers(20, 40, target.shape)), axis=2).astype(np.uint8)
    rgb[target > 0] = colored[target > 0]
    return rgb, np.full(target.shape, 255, np.uint8), target


def iou(actual, expected):
    a, b = actual > 0, expected > 0
    return np.count_nonzero(a & b) / np.count_nonzero(a | b)


def test_color_and_auto_improve_noisy_red_paper_over_baseline():
    rgb, alpha, target = noisy_paper()
    baseline = OpenCvSegmenter().segment(rgb, ProfileId.SILHOUETTE, SegmentHints()).mask
    for settings in (ExtractionSettings(), ExtractionSettings(mode="color", color="#c0271e", tolerance=24)):
        result = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(), settings)
        assert iou(result.mask, target) > 0.97
        assert iou(result.mask, target) > iou(baseline, target) + 0.25
        assert set(np.unique(result.mask)) <= {0, 255}
        assert np.array_equal(np.asarray(result.rgba)[:, :, :3], rgb)
    assert iou(baseline, target) < 0.7


def test_auto_separates_red_paper_from_dark_reddish_wood_at_image_border():
    rgb, alpha, target = noisy_paper()
    wood = np.zeros_like(rgb)
    wood[:, :, 0] = np.linspace(55, 95, rgb.shape[1]).astype(np.uint8)
    wood[:, :, 1] = 24
    wood[:, :, 2] = 13
    rgb[110:] = wood[110:]
    rgb[(target > 0)] = [195, 35, 28]
    result = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(), ExtractionSettings())
    assert result.parameters["selected_method"] == "chromatic-foreground"
    assert iou(result.mask, target) > 0.97
    assert np.count_nonzero(result.mask[-1]) == 0


@pytest.mark.parametrize("brightness", [60, 85])
def test_auto_keeps_dark_colored_art_when_background_is_already_clean(brightness):
    rgb, alpha, target = noisy_paper()
    rgb[target > 0] = [brightness, 12, 10]
    result = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(), ExtractionSettings())
    assert result.parameters["selected_method"] == "chromatic-foreground"
    assert iou(result.mask, target) > 0.97


@pytest.mark.parametrize("max_edge", [1024, 2048])
def test_auto_real_lotus_paper_photo_rejects_wall_and_dark_wood(max_edge):
    from pattern_reborn.images import load_working_image
    path = Path(__file__).resolve().parents[1] / "data/demo/lotus-paper-cut/source.jpg"
    rgb = np.asarray(load_working_image(path, max_edge=max_edge).convert("RGB"))
    alpha = np.full(rgb.shape[:2], 255, np.uint8)
    result = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(), ExtractionSettings())
    # Independent easy foreground/background anchors in the licensed real photo;
    # these avoid claiming a fully annotated or perfectly segmented cutout.
    core = (rgb[:, :, 0] >= 150) & (rgb[:, :, 0].astype(int) - rgb[:, :, 1] >= 110) & (rgb[:, :, 0].astype(int) - rgb[:, :, 2] >= 100)
    assert np.count_nonzero(core) > core.size * 0.1
    assert result.parameters["selected_method"] == "chromatic-foreground"
    assert np.mean(result.mask[core] > 0) > 0.95
    assert np.mean(result.mask[:int(len(rgb) * 0.3)] > 0) < 0.01
    assert np.mean(result.mask[int(len(rgb) * 0.7):] > 0) < 0.01


@pytest.mark.parametrize("scene", ["uniform", "low_contrast", "wood_gradient", "other_hue"])
def test_auto_does_not_retry_a_colored_background_without_separated_bright_foreground(scene):
    rgb = np.full((100, 140, 3), [180, 30, 20], np.uint8)
    if scene == "low_contrast":
        rgb[25:75, 40:100] = [200, 32, 22]
    elif scene == "wood_gradient":
        rgb[:, :, 0] = np.linspace(55, 95, rgb.shape[1]).astype(np.uint8)
    elif scene == "other_hue":
        rgb[25:75, 40:100] = [20, 230, 20]
    result = extract_local(rgb, np.full(rgb.shape[:2], 255, np.uint8), ProfileId.SILHOUETTE,
                           SegmentHints(), ExtractionSettings())
    assert result.parameters["selected_method"] == "opencv"


def test_seed_selection_is_deterministic_and_preserves_cutouts():
    rgb, alpha, target = noisy_paper()
    settings = ExtractionSettings(mode="color", seed=(90, 40), tolerance=30)
    first = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(), settings)
    second = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(), settings)
    assert np.array_equal(first.mask, second.mask)
    assert first.mask[70, 90] == 0
    assert iou(first.mask, target) > 0.97


@pytest.mark.parametrize("mode", ["auto", "whole"])
def test_transparent_input_retains_original_alpha_and_small_islands(mode):
    rgb = np.full((32, 32, 3), 180, np.uint8)
    alpha = np.zeros((32, 32), np.uint8)
    alpha[8:24, 8:24] = 128
    alpha[2, 2] = 37
    before_rgb, before_alpha = rgb.copy(), alpha.copy()
    result = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(),
                           ExtractionSettings(mode=mode, minimum_area=4096, fill_holes=True, smooth=3))
    assert np.array_equal(np.asarray(result.rgba)[:, :, 3], alpha)
    assert np.array_equal(rgb, before_rgb)
    assert np.array_equal(alpha, before_alpha)


def test_cleanup_runs_before_manual_strokes_and_never_revives_transparency():
    rgb, alpha, _ = noisy_paper()
    alpha[19:22, 19:22] = 0
    strokes = [MaskStroke(MaskEditMode.KEEP, [(20, 20)], 7),
               MaskStroke(MaskEditMode.REMOVE, [(90, 40)], 5)]
    result = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(),
                           ExtractionSettings(fill_holes=True, smooth=3, minimum_area=500), strokes=strokes)
    assert result.mask[40, 90] == 0
    assert result.mask[20, 23] == 255  # Tiny hand correction survives component cleanup.
    assert result.mask[20, 20] == 0
    assert result.mask[70, 90] == 255  # Explicit hole filling.
    assert np.all(np.asarray(result.rgba)[:, :, 3] <= alpha)


def test_feather_changes_output_only_and_is_clipped_to_source_alpha():
    rgb, alpha, _ = noisy_paper()
    alpha[:, :70] = 0
    result = extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(),
                           ExtractionSettings(mode="color", color="#c0271e"), feather=4)
    assert set(np.unique(result.mask)) <= {0, 255}
    assert np.all(np.asarray(result.rgba)[:, :, 3] <= alpha)
    assert np.any((np.asarray(result.rgba)[:, :, 3] > 0) & (np.asarray(result.rgba)[:, :, 3] < 255))


@pytest.mark.parametrize("settings", [
    {"seed": (-1, 10)}, {"seed": (180, 3)},
])
def test_seed_bounds_fail_instead_of_wrapping(settings):
    rgb, alpha, _ = noisy_paper()
    with pytest.raises(SegmentationError, match="范围"):
        extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(), ExtractionSettings(mode="color", **settings))


@pytest.mark.parametrize("values", [
    {"seed": (True, 3)}, {"tolerance": float("nan")}, {"minimum_area": 5000},
    {"smooth": 4}, {"fill_holes": "yes"}, {"color": "red"},
])
def test_settings_reject_unsafe_or_ambiguous_values(values):
    with pytest.raises(ValidationError):
        ExtractionSettings(**values)


def test_roi_and_manual_stroke_bounds():
    rgb, alpha, _ = noisy_paper()
    with pytest.raises(SegmentationError, match="选区"):
        extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(box=(0, 0, 1000, 30)), ExtractionSettings())
    with pytest.raises(SegmentationError, match="范围"):
        extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(), ExtractionSettings(),
                      strokes=[MaskStroke(MaskEditMode.KEEP, [(180, 4)], 3)])


def test_optional_probe_never_imports_or_downloads_and_disabled_mode_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("PATTERN_REBORN_DISABLE_OPTIONAL", "1")
    assert extraction_capabilities(tmp_path)["mobile_sam"]["available"] is False
    rgb, alpha, _ = noisy_paper()
    with pytest.raises(SegmentationError, match="不会自动下载"):
        extract_local(rgb, alpha, ProfileId.SILHOUETTE, SegmentHints(box=(1, 1, 100, 100)),
                      ExtractionSettings(mode="mobile_sam"), root=tmp_path)
