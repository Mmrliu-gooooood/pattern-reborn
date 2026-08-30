"""Deterministic offline OpenCV motif extraction and reversible mask edits."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

import cv2
import numpy as np
from PIL import Image

from pattern_reborn.domain import ProfileId


ALGORITHM_VERSION = "opencv-baseline-1.0"
MOBILE_SAM_ALGORITHM_VERSION = "mobile-sam-1.0"


class SegmentationError(ValueError):
    """Segmentation inputs or region guidance are invalid."""


class MaskEditMode(str, Enum):
    KEEP = "keep"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class PromptPoint:
    """One serialized foreground/background prompt point."""

    x: int
    y: int
    keep: bool

    def __post_init__(self) -> None:
        _require_integer(self.x, "提示点 X")
        _require_integer(self.y, "提示点 Y")
        if not isinstance(self.keep, bool):
            raise SegmentationError("提示点保留标记必须是布尔值。")

    def record(self) -> dict[str, object]:
        return {"x": self.x, "y": self.y, "keep": self.keep}

    @classmethod
    def from_record(cls, record: object) -> PromptPoint:
        if not isinstance(record, dict):
            raise SegmentationError("提示点记录无效。")
        try:
            return cls(x=record["x"], y=record["y"], keep=record["keep"])
        except KeyError as error:
            raise SegmentationError("提示点记录缺少字段。") from error


@dataclass(frozen=True, slots=True)
class SegmentHints:
    """Serializable region guidance shared by all segmenters."""

    box: tuple[int, int, int, int] | None = None
    points: Sequence[PromptPoint] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.box is not None:
            if not _is_public_sequence(self.box):
                raise SegmentationError("选区必须是坐标序列。")
            if len(self.box) != 4:
                raise SegmentationError("选区必须包含四个坐标。")
            normalized_box = tuple(_require_integer(value, "ROI") for value in self.box)
            object.__setattr__(self, "box", normalized_box)
        if not _is_public_sequence(self.points):
            raise SegmentationError("提示点必须是序列。")
        normalized_points = tuple(self.points)
        if not all(isinstance(point, PromptPoint) for point in normalized_points):
            raise SegmentationError("提示点必须全部为有效提示点。")
        object.__setattr__(self, "points", normalized_points)

    def record(self) -> dict[str, object]:
        return {
            "box": list(self.box) if self.box is not None else None,
            "points": [point.record() for point in self.points],
        }

    @classmethod
    def from_record(cls, record: object) -> SegmentHints:
        if not isinstance(record, dict):
            raise SegmentationError("区域提示记录无效。")
        try:
            box = record["box"]
            points = [PromptPoint.from_record(point) for point in record["points"]]
        except (KeyError, TypeError) as error:
            raise SegmentationError("区域提示记录缺少字段。") from error
        return cls(box=tuple(box) if box is not None else None, points=points)


@dataclass(frozen=True, slots=True)
class MaskStroke:
    """An ordered, replayable keep/remove brush stroke."""

    mode: MaskEditMode
    points: Sequence[tuple[int, int]]
    width: int

    def __post_init__(self) -> None:
        if not isinstance(self.mode, MaskEditMode):
            raise SegmentationError("蒙版编辑模式无效。")
        normalized_points: list[tuple[int, int]] = []
        for point in self.points:
            if not isinstance(point, Sequence) or len(point) != 2:
                raise SegmentationError("笔触点必须包含两个坐标。")
            normalized_points.append(
                (_require_integer(point[0], "笔触"), _require_integer(point[1], "笔触"))
            )
        if not normalized_points:
            raise SegmentationError("笔触至少需要一个坐标。")
        width = _require_integer(self.width, "笔触宽度")
        if width <= 0:
            raise SegmentationError("笔触宽度必须为正整数。")
        object.__setattr__(self, "points", tuple(normalized_points))
        object.__setattr__(self, "width", width)

    def record(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "points": [list(point) for point in self.points],
            "width": self.width,
        }

    @classmethod
    def from_record(cls, record: object) -> MaskStroke:
        if not isinstance(record, dict):
            raise SegmentationError("笔触记录无效。")
        try:
            return cls(
                mode=MaskEditMode(record["mode"]),
                points=record["points"],
                width=record["width"],
            )
        except (KeyError, ValueError) as error:
            raise SegmentationError("笔触记录无效。") from error


@dataclass(frozen=True, slots=True)
class SegmentResult:
    """A binary mask, source-preserving RGBA extraction, and JSON-safe provenance."""

    mask: np.ndarray
    rgba: Image.Image
    profile: ProfileId
    parameters: dict[str, object]
    hints: SegmentHints
    algorithm_version: str = ALGORITHM_VERSION
    warnings: tuple[str, ...] = ()

    def record(self) -> dict[str, object]:
        return {
            "profile": self.profile.value,
            "parameters": self.parameters.copy(),
            "hints": self.hints.record(),
            "algorithm_version": self.algorithm_version,
            "warnings": list(self.warnings),
        }


class Segmenter(Protocol):
    def segment(
        self, image: np.ndarray, profile: ProfileId, hints: SegmentHints
    ) -> SegmentResult: ...


class OpenCvSegmenter:
    """The mandatory local OpenCV baseline for all four processing profiles."""

    def __init__(self, minimum_component_area: int = 16) -> None:
        area = _require_integer(minimum_component_area, "最小连通区域")
        if area <= 0:
            raise SegmentationError("最小连通区域必须为正整数。")
        self._minimum_component_area = area

    def segment(
        self, image: np.ndarray, profile: ProfileId, hints: SegmentHints
    ) -> SegmentResult:
        rgb = _require_rgb_uint8(image)
        _require_segmentable_size(rgb)
        if not isinstance(profile, ProfileId):
            raise SegmentationError("提取配置无效。")
        if not isinstance(hints, SegmentHints):
            raise SegmentationError("区域提示无效。")

        roi, resolved_hints, warnings = _resolve_roi(
            hints,
            width=rgb.shape[1],
            height=rgb.shape[0],
            require_grabcut_size=profile is ProfileId.ARTIFACT_PHOTO,
        )
        if profile is ProfileId.ARTIFACT_PHOTO and roi is None:
            raise SegmentationError("文物照片配置需要有效 ROI。")

        parameters: dict[str, object] = {
            "minimum_component_area": self._minimum_component_area,
            "profile_algorithm": _profile_algorithm(profile),
        }
        if profile is ProfileId.SILHOUETTE:
            mask = _segment_silhouette(rgb)
        elif profile is ProfileId.FLAT_COLOR:
            mask = _segment_flat_color(rgb)
        elif profile is ProfileId.TEXTILE:
            mask = _segment_textile(rgb)
        else:
            assert roi is not None
            mask = _segment_artifact(rgb, roi)
            parameters["grabcut_iterations"] = 3

        if roi is not None:
            mask = _limit_to_roi(mask, roi)
        filtered = filter_small_components(mask, self._minimum_component_area)
        if np.count_nonzero(filtered) != np.count_nonzero(mask):
            warnings.append("removed_small_components")
        prompted = _apply_prompt_points(filtered, resolved_hints.points, roi)
        if roi is not None:
            prompted = _limit_to_roi(prompted, roi)
        if not np.any(prompted):
            warnings.append("no_foreground_detected")

        final_mask = np.ascontiguousarray(prompted, dtype=np.uint8)
        return SegmentResult(
            mask=final_mask.copy(),
            rgba=extract_rgba(rgb, final_mask),
            profile=profile,
            parameters=parameters,
            hints=resolved_hints,
            warnings=tuple(warnings),
        )


class MobileSamSegmenter:
    """Optional MobileSAM adapter. The predictor is injected; Torch is never imported here."""

    def __init__(self, predictor: object) -> None:
        self._predictor = predictor

    def segment(
        self, image: np.ndarray, profile: ProfileId, hints: SegmentHints
    ) -> SegmentResult:
        rgb = _require_rgb_uint8(image)
        _require_segmentable_size(rgb)
        if not isinstance(profile, ProfileId):
            raise SegmentationError("提取配置无效。")
        if not isinstance(hints, SegmentHints):
            raise SegmentationError("区域提示无效。")

        roi, resolved_hints, warnings = _resolve_roi(
            hints,
            width=rgb.shape[1],
            height=rgb.shape[0],
            require_grabcut_size=False,
        )
        clipped_points = tuple(
            PromptPoint(
                *_clip_point(
                    (point.x, point.y),
                    width=rgb.shape[1],
                    height=rgb.shape[0],
                ),
                point.keep,
            )
            for point in resolved_hints.points
        )
        if clipped_points != resolved_hints.points:
            warnings.append("prompt_points_clipped")
        resolved_hints = SegmentHints(box=roi, points=clipped_points)

        set_image = getattr(self._predictor, "set_image", None)
        predict = getattr(self._predictor, "predict", None)
        if not callable(set_image) or not callable(predict):
            raise SegmentationError("MobileSAM 预测器无效。")

        set_image(rgb.copy())
        predict_kwargs: dict[str, object] = {"multimask_output": False}
        if resolved_hints.box is not None:
            predict_kwargs["box"] = np.asarray(resolved_hints.box, dtype=np.float32)
        if resolved_hints.points:
            predict_kwargs["point_coords"] = np.asarray(
                [[point.x, point.y] for point in resolved_hints.points], dtype=np.float32
            )
            predict_kwargs["point_labels"] = np.asarray(
                [1 if point.keep else 0 for point in resolved_hints.points], dtype=np.int32
            )

        masks, _scores, _logits = predict(**predict_kwargs)
        final_mask = _mask_from_predictor(masks, rgb.shape[:2])
        if not np.any(final_mask):
            warnings.append("no_foreground_detected")

        return SegmentResult(
            mask=final_mask.copy(),
            rgba=extract_rgba(rgb, final_mask),
            profile=profile,
            parameters={
                "profile_algorithm": "mobile-sam-prompted",
                "multimask_output": False,
            },
            hints=resolved_hints,
            algorithm_version=MOBILE_SAM_ALGORITHM_VERSION,
            warnings=tuple(warnings),
        )


def apply_mask_strokes(mask: np.ndarray, strokes: Sequence[MaskStroke]) -> np.ndarray:
    """Replay ordered keep/remove strokes on a copied binary mask."""
    edited = _require_binary_mask(mask).copy()
    for stroke in strokes:
        if not isinstance(stroke, MaskStroke):
            raise SegmentationError("笔触无效。")
        color = 255 if stroke.mode is MaskEditMode.KEEP else 0
        points = tuple(_clip_point(point, width=edited.shape[1], height=edited.shape[0]) for point in stroke.points)
        if len(points) == 1:
            cv2.circle(edited, points[0], max(0, stroke.width // 2), color, thickness=-1)
        else:
            cv2.polylines(edited, [np.asarray(points, dtype=np.int32)], False, color, thickness=stroke.width)
            cv2.circle(edited, points[0], max(0, stroke.width // 2), color, thickness=-1)
            cv2.circle(edited, points[-1], max(0, stroke.width // 2), color, thickness=-1)
    return edited


def extract_rgba(image: np.ndarray, mask: np.ndarray) -> Image.Image:
    """Build RGBA output whose RGB channels exactly match the RGB uint8 source."""
    rgb = _require_rgb_uint8(image)
    binary_mask = _require_binary_mask(mask)
    if binary_mask.shape != rgb.shape[:2]:
        raise SegmentationError("蒙版尺寸必须与图像一致。")
    return Image.fromarray(np.dstack((rgb, binary_mask)).copy())


def combine_with_source_alpha(mask: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Clear segmented pixels that were fully transparent in the source image."""
    binary_mask = _require_binary_mask(mask)
    source_alpha = _require_source_alpha(alpha)
    if source_alpha.shape != binary_mask.shape:
        raise SegmentationError("源透明度尺寸必须与蒙版一致。")
    return np.ascontiguousarray(
        np.where(source_alpha > 0, binary_mask, 0),
        dtype=np.uint8,
    )


def filter_small_components(mask: np.ndarray, minimum_area: int) -> np.ndarray:
    """Return a copied binary mask with connected components smaller than the limit removed."""
    binary_mask = _require_binary_mask(mask)
    area = _require_integer(minimum_area, "最小连通区域")
    if area <= 0:
        raise SegmentationError("最小连通区域必须为正整数。")
    labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
    filtered = np.zeros_like(binary_mask)
    for label in range(1, labels_count):
        if stats[label, cv2.CC_STAT_AREA] >= area:
            filtered[labels == label] = 255
    return filtered


def _segment_silhouette(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5
    )
    selected = _select_foreground(otsu, cv2.bitwise_not(otsu), adaptive, cv2.bitwise_not(adaptive))
    kernel = np.ones((3, 3), dtype=np.uint8)
    return cv2.morphologyEx(selected, cv2.MORPH_OPEN, kernel)


def _segment_flat_color(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    samples = lab.reshape((-1, 3)).astype(np.float32)
    cv2.setRNGSeed(20260829)
    _, labels, _ = cv2.kmeans(
        samples,
        2,
        None,
        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 20, 0.1),
        1,
        cv2.KMEANS_PP_CENTERS,
    )
    first = np.where(labels.reshape(rgb.shape[:2]) == 0, 255, 0).astype(np.uint8)
    return _select_foreground(first, cv2.bitwise_not(first))


def _segment_textile(rgb: np.ndarray) -> np.ndarray:
    smoothed = cv2.bilateralFilter(rgb, d=7, sigmaColor=50, sigmaSpace=50)
    gray = cv2.cvtColor(smoothed, cv2.COLOR_RGB2GRAY)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 4
    )
    selected = _select_foreground(otsu, cv2.bitwise_not(otsu), adaptive, cv2.bitwise_not(adaptive))
    return cv2.morphologyEx(selected, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))


def _segment_artifact(rgb: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
    left, top, right, bottom = roi
    grabcut_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    try:
        cv2.grabCut(
            rgb.copy(),
            grabcut_mask,
            (left, top, right - left, bottom - top),
            None,
            None,
            3,
            cv2.GC_INIT_WITH_RECT,
        )
    except cv2.error as error:
        raise SegmentationError("ROI 无法用于 GrabCut 提取。") from error
    foreground = (grabcut_mask == cv2.GC_FGD) | (grabcut_mask == cv2.GC_PR_FGD)
    return np.where(foreground, 255, 0).astype(np.uint8)


def _select_foreground(*candidates: np.ndarray) -> np.ndarray:
    valid = [candidate for candidate in candidates if 0 < np.count_nonzero(candidate) < candidate.size]
    if not valid:
        return np.zeros_like(candidates[0])
    return min(valid, key=lambda candidate: (_border_foreground_fraction(candidate), np.count_nonzero(candidate))).copy()


def _border_foreground_fraction(mask: np.ndarray) -> float:
    border = np.concatenate((mask[0], mask[-1], mask[1:-1, 0], mask[1:-1, -1]))
    return float(np.count_nonzero(border)) / border.size


def _resolve_roi(
    hints: SegmentHints, *, width: int, height: int, require_grabcut_size: bool
) -> tuple[tuple[int, int, int, int] | None, SegmentHints, list[str]]:
    if hints.box is None:
        return None, hints, []
    left, top, right, bottom = hints.box
    clipped = (
        min(max(left, 0), width),
        min(max(top, 0), height),
        min(max(right, 0), width),
        min(max(bottom, 0), height),
    )
    if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
        raise SegmentationError("ROI 裁剪后必须保留有效面积。")
    if require_grabcut_size and (clipped[2] - clipped[0] < 2 or clipped[3] - clipped[1] < 2):
        raise SegmentationError("ROI 对 GrabCut 而言过小。")
    warnings = ["roi_clipped"] if clipped != hints.box else []
    return clipped, SegmentHints(box=clipped, points=hints.points), warnings


def _limit_to_roi(mask: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
    left, top, right, bottom = roi
    limited = np.zeros_like(mask)
    limited[top:bottom, left:right] = mask[top:bottom, left:right]
    return limited


def _apply_prompt_points(
    mask: np.ndarray,
    points: Sequence[PromptPoint],
    roi: tuple[int, int, int, int] | None,
) -> np.ndarray:
    prompted = mask.copy()
    for point in points:
        if not (0 <= point.x < prompted.shape[1] and 0 <= point.y < prompted.shape[0]):
            continue
        if roi is not None and not (roi[0] <= point.x < roi[2] and roi[1] <= point.y < roi[3]):
            continue
        cv2.circle(prompted, (point.x, point.y), 2, 255 if point.keep else 0, thickness=-1)
    return prompted


def _profile_algorithm(profile: ProfileId) -> str:
    return {
        ProfileId.SILHOUETTE: "otsu-adaptive-morphology",
        ProfileId.FLAT_COLOR: "lab-kmeans",
        ProfileId.TEXTILE: "bilateral-otsu-adaptive",
        ProfileId.ARTIFACT_PHOTO: "grabcut-rectangle",
    }[profile]


def _mask_from_predictor(masks: object, shape: tuple[int, int]) -> np.ndarray:
    array = np.asarray(masks)
    if array.ndim == 3:
        array = array[0]
    if array.shape != shape:
        raise SegmentationError("蒙版尺寸必须与图像一致。")
    binary = np.where(array > 0, 255, 0).astype(np.uint8)
    return np.ascontiguousarray(binary)


def _require_rgb_uint8(image: object) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        raise SegmentationError("图像必须是 RGB uint8 数组。")
    if image.ndim != 3 or image.shape[2] != 3 or not image.shape[0] or not image.shape[1]:
        raise SegmentationError("图像必须是非空 RGB uint8 数组。")
    return np.ascontiguousarray(image)


def _require_segmentable_size(image: np.ndarray) -> None:
    if image.shape[0] < 2 or image.shape[1] < 2:
        raise SegmentationError("图像尺寸过小，至少需要 2×2 像素。")


def _require_binary_mask(mask: object) -> np.ndarray:
    if not isinstance(mask, np.ndarray) or mask.dtype != np.uint8 or mask.ndim != 2:
        raise SegmentationError("蒙版必须是二值 uint8 数组。")
    if not mask.shape[0] or not mask.shape[1] or not np.isin(mask, (0, 255)).all():
        raise SegmentationError("蒙版必须只包含 0 或 255。")
    return np.ascontiguousarray(mask)


def _require_source_alpha(alpha: object) -> np.ndarray:
    if not isinstance(alpha, np.ndarray) or alpha.dtype != np.uint8 or alpha.ndim != 2:
        raise SegmentationError("源透明度必须是 uint8 二维数组。")
    if not alpha.shape[0] or not alpha.shape[1]:
        raise SegmentationError("源透明度必须是非空 uint8 二维数组。")
    return np.ascontiguousarray(alpha)


def _require_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SegmentationError(f"{label}必须是整数。")
    return value


def _is_public_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _clip_point(point: tuple[int, int], *, width: int, height: int) -> tuple[int, int]:
    return (min(max(point[0], 0), width - 1), min(max(point[1], 0), height - 1))
