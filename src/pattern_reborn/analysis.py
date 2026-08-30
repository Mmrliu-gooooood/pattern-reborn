"""Deterministic, local motif palette, contour, and symmetry measurements.

The metrics in this module describe pixels and geometry only.  Traditional
color matches are digital CIE Lab approximations, not cultural assertions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import cv2
import numpy as np
from PIL import Image

from pattern_reborn.knowledge import TraditionalColor


class AnalysisError(ValueError):
    """分析输入或参数无效。"""


@dataclass(frozen=True, slots=True)
class PaletteColor:
    """A representative RGB k-means center and its measured sample coverage."""

    rgb: tuple[int, int, int]
    pixel_count: int
    coverage: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rgb, tuple)
            or len(self.rgb) != 3
            or any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255 for value in self.rgb)
        ):
            raise AnalysisError("调色板 RGB 必须包含三个 0 到 255 的整数。")
        if isinstance(self.pixel_count, bool) or not isinstance(self.pixel_count, int) or self.pixel_count <= 0:
            raise AnalysisError("调色板像素数量必须为正整数。")
        if not isinstance(self.coverage, (int, float)) or isinstance(self.coverage, bool) or not math.isfinite(self.coverage) or not 0.0 <= float(self.coverage) <= 1.0:
            raise AnalysisError("调色板覆盖率必须是 0 到 1 之间的有限数值。")

    @property
    def hex_value(self) -> str:
        """Return the representative RGB center in uppercase hexadecimal notation."""
        return "#" + "".join(f"{value:02X}" for value in self.rgb)


@dataclass(frozen=True, slots=True)
class ColorMatch:
    """A nearest catalog color measured in the same CIE Lab coordinate space."""

    palette_color: PaletteColor
    traditional_color: TraditionalColor
    distance: float

    def __post_init__(self) -> None:
        if not isinstance(self.palette_color, PaletteColor) or not isinstance(self.traditional_color, TraditionalColor):
            raise AnalysisError("传统色匹配记录无效。")
        if not isinstance(self.distance, (int, float)) or isinstance(self.distance, bool) or not math.isfinite(self.distance) or self.distance < 0:
            raise AnalysisError("传统色距离必须是非负有限数值。")


@dataclass(frozen=True, slots=True)
class ContourReport:
    """External contours, their holes, and pixel-based foreground geometry.

    ``contour_count`` counts only external contours. ``hole_count`` counts all
    child contours returned by OpenCV's two-level hierarchy. ``total_perimeter``
    includes both external and hole boundaries. Foreground area is the number
    of non-zero mask pixels, rather than an approximation from contour area.
    """

    contour_count: int
    hole_count: int
    total_perimeter: float
    foreground_area: int
    foreground_ratio: float
    complexity: float

    @property
    def external_count(self) -> int:
        """Alias that makes the external-only counting rule explicit."""
        return self.contour_count


@dataclass(frozen=True, slots=True)
class RotationCandidate:
    """IoU after rotating the centered foreground by one order step."""

    order: int
    score: float


@dataclass(frozen=True, slots=True)
class SymmetryReport:
    """Bilateral and rotational IoU scores for a centered foreground mask."""

    vertical_score: float
    horizontal_score: float
    rotations: tuple[RotationCandidate, ...]

    @property
    def rotation_candidates(self) -> tuple[RotationCandidate, ...]:
        """Alias for callers that prefer the candidate terminology."""
        return self.rotations


def analyze_palette(image: Image.Image, count: int, seed: int) -> list[PaletteColor]:
    """Cluster opaque RGB/RGBA pixels with seeded k-means without mutating ``image``."""
    samples = _opaque_rgb_samples(image)
    cluster_count = _require_positive_integer(count, "调色板数量")
    rng_seed = _require_seed(seed)
    unique_samples = np.unique(samples, axis=0)
    if cluster_count > len(samples):
        raise AnalysisError("调色板数量不能超过不透明像素数量。")
    if cluster_count > len(unique_samples):
        raise AnalysisError("调色板数量不能超过不透明像素中的唯一颜色数量。")

    cv2.setRNGSeed(rng_seed)
    _, labels, centers = cv2.kmeans(
        samples.astype(np.float32),
        cluster_count,
        None,
        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 0.1),
        1,
        cv2.KMEANS_PP_CENTERS,
    )
    assigned = labels.reshape(-1)
    total = len(samples)
    colors = [
        PaletteColor(
            rgb=tuple(int(value) for value in np.clip(np.rint(centers[index]), 0, 255)),
            pixel_count=int(np.count_nonzero(assigned == index)),
            coverage=float(np.count_nonzero(assigned == index) / total),
        )
        for index in range(cluster_count)
    ]
    return sorted(colors, key=lambda color: (-color.coverage, color.rgb))


def match_traditional_colors(
    colors: Sequence[PaletteColor], catalog: Sequence[TraditionalColor]
) -> list[ColorMatch]:
    """Return one deterministic nearest CIE Lab catalog match per palette color."""
    palette = _require_sequence(colors, PaletteColor, "调色板")
    traditional_colors = _require_sequence(catalog, TraditionalColor, "传统色目录")
    if not traditional_colors:
        raise AnalysisError("传统色目录不能为空。")

    catalog_labs = _rgb_to_cie_lab(
        np.asarray([_hex_to_rgb(color.hex_value) for color in traditional_colors], dtype=np.uint8)
    )
    matches: list[ColorMatch] = []
    for color in palette:
        palette_lab = _rgb_to_cie_lab(np.asarray([color.rgb], dtype=np.uint8))[0]
        distances = np.linalg.norm(catalog_labs - palette_lab, axis=1)
        winner = min(
            range(len(traditional_colors)),
            key=lambda index: (float(distances[index]), traditional_colors[index].slug),
        )
        matches.append(
            ColorMatch(
                palette_color=color,
                traditional_color=traditional_colors[winner],
                distance=float(distances[winner]),
            )
        )
    return matches


def analyze_contours(mask: np.ndarray) -> ContourReport:
    """Measure external contours and holes from an immutable binary uint8 mask."""
    binary_mask = _require_binary_mask(mask)
    contours, hierarchy = cv2.findContours(
        binary_mask.copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE
    )
    parents = hierarchy[0, :, 3] if hierarchy is not None else np.empty(0, dtype=np.int32)
    contour_count = int(np.count_nonzero(parents == -1))
    hole_count = int(np.count_nonzero(parents != -1))
    total_perimeter = float(sum(cv2.arcLength(contour, True) for contour in contours))
    foreground_area = int(np.count_nonzero(binary_mask))
    foreground_ratio = float(foreground_area / binary_mask.size)
    complexity = (
        float(total_perimeter**2 / (4.0 * math.pi * foreground_area))
        if foreground_area
        else 0.0
    )
    return ContourReport(
        contour_count=contour_count,
        hole_count=hole_count,
        total_perimeter=total_perimeter,
        foreground_area=foreground_area,
        foreground_ratio=foreground_ratio,
        complexity=complexity,
    )


def analyze_symmetry(mask: np.ndarray) -> SymmetryReport:
    """Compare foreground IoU against bilateral flips and five NN rotations."""
    binary_mask = _require_binary_mask(mask)
    if not np.any(binary_mask):
        raise AnalysisError("蒙版不包含可分析的前景。")
    foreground = _foreground_crop(binary_mask)
    vertical_score = _iou(foreground, np.fliplr(foreground))
    horizontal_score = _iou(foreground, np.flipud(foreground))
    centered = _center_foreground(foreground)
    rotations = tuple(
        sorted(
            (
                RotationCandidate(order=order, score=_iou(centered, _rotate_nearest(centered, 360.0 / order)))
                for order in (2, 3, 4, 6, 8)
            ),
            key=lambda candidate: (-candidate.score, candidate.order),
        )
    )
    return SymmetryReport(
        vertical_score=vertical_score,
        horizontal_score=horizontal_score,
        rotations=rotations,
    )


def _opaque_rgb_samples(image: object) -> np.ndarray:
    if not isinstance(image, Image.Image) or image.mode not in {"RGB", "RGBA"}:
        raise AnalysisError("图像必须是 Pillow RGB 或 RGBA 图像。")
    pixels = np.asarray(image)
    if pixels.ndim != 3 or pixels.shape[0] == 0 or pixels.shape[1] == 0:
        raise AnalysisError("图像必须包含至少一个像素。")
    if image.mode == "RGBA":
        pixels = pixels[pixels[..., 3] != 0, :3]
    else:
        pixels = pixels.reshape((-1, 3))
    if len(pixels) == 0:
        raise AnalysisError("图像不包含可用于调色板分析的不透明像素。")
    return np.ascontiguousarray(pixels, dtype=np.uint8)


def _require_binary_mask(mask: object) -> np.ndarray:
    if not isinstance(mask, np.ndarray) or mask.dtype != np.uint8 or mask.ndim != 2:
        raise AnalysisError("蒙版必须是二值 uint8 数组。")
    if mask.shape[0] == 0 or mask.shape[1] == 0 or not np.isin(mask, (0, 255)).all():
        raise AnalysisError("蒙版必须是非空且仅包含 0 或 255 的二值 uint8 数组。")
    return np.ascontiguousarray(mask)


def _require_positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AnalysisError(f"{label}必须是正整数。")
    return value


def _require_seed(seed: object) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2_147_483_647:
        raise AnalysisError("随机种子必须是 0 到 2147483647 的整数。")
    return seed


def _require_sequence(value: object, item_type: type[object], label: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AnalysisError(f"{label}必须是序列。")
    items = tuple(value)
    if not all(isinstance(item, item_type) for item in items):
        raise AnalysisError(f"{label}包含无效记录。")
    return items


def _hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    return tuple(int(hex_value[index : index + 2], 16) for index in (1, 3, 5))


def _rgb_to_cie_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert uint8 RGB rows to OpenCV's float CIE Lab representation."""
    normalized = rgb.astype(np.float32).reshape((1, -1, 3)) / 255.0
    return cv2.cvtColor(normalized, cv2.COLOR_RGB2LAB).reshape((-1, 3))


def _center_foreground(foreground: np.ndarray) -> np.ndarray:
    side = max(foreground.shape)
    pad_y = side - foreground.shape[0]
    pad_x = side - foreground.shape[1]
    return np.pad(
        foreground,
        ((pad_y // 2, pad_y - pad_y // 2), (pad_x // 2, pad_x - pad_x // 2)),
    )


def _foreground_crop(mask: np.ndarray) -> np.ndarray:
    rows, columns = np.nonzero(mask)
    return mask[rows.min() : rows.max() + 1, columns.min() : columns.max() + 1] != 0


def _rotate_nearest(mask: np.ndarray, angle: float) -> np.ndarray:
    side = mask.shape[0]
    matrix = cv2.getRotationMatrix2D(((side - 1) / 2.0, (side - 1) / 2.0), angle, 1.0)
    rotated = cv2.warpAffine(
        mask.astype(np.uint8),
        matrix,
        (side, side),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return rotated != 0


def _iou(left: np.ndarray, right: np.ndarray) -> float:
    union = np.logical_or(left, right)
    return float(np.count_nonzero(np.logical_and(left, right)) / np.count_nonzero(union))
