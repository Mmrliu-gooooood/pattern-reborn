"""Deterministic RGB uint8 preprocessing transforms for later OpenCV stages."""

from dataclasses import dataclass
import math
from typing import Sequence

import cv2
import numpy as np

from pattern_reborn.limits import (
    MAX_INTERMEDIATE_EDGE,
    MAX_INTERMEDIATE_PIXELS,
    ImageLimitError,
    require_bounded_size,
)


class PreprocessError(ValueError):
    """预处理参数或图像数组不符合安全约束。"""


@dataclass(frozen=True, slots=True)
class PreprocessSettings:
    """Conservative, explicit settings for deterministic image enhancement."""

    white_balance_strength: float = 0.1
    denoise_strength: int = 3
    clahe_clip_limit: float = 1.25
    clahe_tile_grid_size: tuple[int, int] = (8, 8)

    def __post_init__(self) -> None:
        strength = _strict_finite_number(self.white_balance_strength, "增强白平衡")
        if not 0.0 <= strength <= 1.0:
            raise PreprocessError("增强白平衡强度必须在 0 到 1 之间。")
        if (
            isinstance(self.denoise_strength, bool)
            or not isinstance(self.denoise_strength, int)
            or not 0 <= self.denoise_strength <= 10
        ):
            raise PreprocessError("增强降噪强度必须是 0 到 10 的整数。")
        clip_limit = _strict_finite_number(self.clahe_clip_limit, "增强 CLAHE")
        if not 0.1 <= clip_limit <= 4.0:
            raise PreprocessError("增强 CLAHE 对比度限制必须在 0.1 到 4 之间。")
        if not isinstance(self.clahe_tile_grid_size, tuple) or len(
            self.clahe_tile_grid_size
        ) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16
            for value in self.clahe_tile_grid_size
        ):
            raise PreprocessError("增强 CLAHE 网格必须由 1 到 16 的整数构成。")
        object.__setattr__(self, "white_balance_strength", strength)
        object.__setattr__(self, "clahe_clip_limit", clip_limit)


def crop(image: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Return an independent RGB uint8 crop after validating its bounds."""
    rgb = _as_rgb_uint8(image)
    if len(box) != 4:
        raise PreprocessError("裁剪范围必须包含四个坐标。")
    left, top, right, bottom = (_integer_coordinate(value, "裁剪") for value in box)
    height, width = rgb.shape[:2]
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise PreprocessError("裁剪范围必须有序且位于图像边界内。")
    return rgb[top:bottom, left:right].copy()


def perspective_correct(
    image: np.ndarray,
    points: list[tuple[float, float]],
    output_size: tuple[int, int],
) -> np.ndarray:
    """Correct a TL, TR, BR, BL quadrilateral into the requested RGB output size."""
    output_width, output_height = _validate_output_size(output_size)
    rgb = _as_rgb_uint8(image)
    source_points = _validate_perspective_points(points, width=rgb.shape[1], height=rgb.shape[0])
    target_points = np.array(
        [
            (0, 0),
            (output_width - 1, 0),
            (output_width - 1, output_height - 1),
            (0, output_height - 1),
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source_points, target_points)
    return cv2.warpPerspective(
        rgb,
        transform,
        (output_width, output_height),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REPLICATE,
    )


def enhance(image: np.ndarray, settings: PreprocessSettings) -> np.ndarray:
    """Apply deterministic white balance, denoising, and local-contrast enhancement."""
    if not isinstance(settings, PreprocessSettings):
        raise PreprocessError("增强设置无效。")
    rgb = _as_rgb_uint8(image)
    balanced = _white_balance(rgb, settings.white_balance_strength)
    if settings.denoise_strength:
        balanced = cv2.fastNlMeansDenoisingColored(
            balanced,
            None,
            h=settings.denoise_strength,
            hColor=settings.denoise_strength,
            templateWindowSize=7,
            searchWindowSize=21,
        )
    lab = cv2.cvtColor(balanced, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(
        clipLimit=settings.clahe_clip_limit,
        tileGridSize=settings.clahe_tile_grid_size,
    )
    lab[..., 0] = clahe.apply(lab[..., 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB).copy()


def _as_rgb_uint8(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray) or not np.issubdtype(image.dtype, np.number):
        raise PreprocessError("图像数组必须是数值数组。")
    if not np.isfinite(image).all():
        raise PreprocessError("图像数组必须只包含有限数值。")
    normalized = np.clip(image, 0, 255).astype(np.uint8, copy=True)
    if normalized.ndim == 2:
        return cv2.cvtColor(normalized, cv2.COLOR_GRAY2RGB)
    if normalized.ndim != 3:
        raise PreprocessError("图像数组必须是二维灰度或三维彩色数组。")
    channels = normalized.shape[2]
    if channels == 1:
        return cv2.cvtColor(normalized, cv2.COLOR_GRAY2RGB)
    if channels == 3:
        return np.ascontiguousarray(normalized)
    if channels == 4:
        return np.ascontiguousarray(normalized[..., :3])
    raise PreprocessError("图像数组必须包含 1、3 或 4 个通道。")


def _validate_perspective_points(
    points: Sequence[Sequence[float]], *, width: int, height: int
) -> np.ndarray:
    if len(points) != 4:
        raise PreprocessError("透视校正必须提供四个角点。")
    try:
        parsed = np.array(
            [(_finite_number(x, "透视"), _finite_number(y, "透视")) for x, y in points],
            dtype=np.float32,
        )
    except (TypeError, ValueError) as error:
        raise PreprocessError("透视角点必须各含两个有限坐标。") from error
    if not ((parsed[:, 0] >= 0).all() and (parsed[:, 0] < width).all()):
        raise PreprocessError("透视角点必须位于图像边界内。")
    if not ((parsed[:, 1] >= 0).all() and (parsed[:, 1] < height).all()):
        raise PreprocessError("透视角点必须位于图像边界内。")
    if not (
        parsed[0, 0] <= parsed[1, 0]
        and parsed[3, 0] <= parsed[2, 0]
        and parsed[0, 1] <= parsed[3, 1]
        and parsed[1, 1] <= parsed[2, 1]
    ):
        raise PreprocessError("透视角点必须按左上、右上、右下、左下顺序提供。")
    edges = np.roll(parsed, -1, axis=0) - parsed
    following_edges = np.roll(edges, -1, axis=0)
    cross_products = edges[:, 0] * following_edges[:, 1] - edges[:, 1] * following_edges[:, 0]
    if not np.all(cross_products > 0):
        raise PreprocessError("透视角点必须构成有序且非退化的四边形。")
    return parsed


def _validate_output_size(output_size: tuple[int, int]) -> tuple[int, int]:
    if len(output_size) != 2:
        raise PreprocessError("透视输出尺寸必须包含宽度和高度。")
    width = _integer_coordinate(output_size[0], "透视输出")
    height = _integer_coordinate(output_size[1], "透视输出")
    if width <= 0 or height <= 0:
        raise PreprocessError("透视输出尺寸必须为正数。")
    try:
        return require_bounded_size(
            width,
            height,
            label="透视输出尺寸",
            max_edge=MAX_INTERMEDIATE_EDGE,
            max_pixels=MAX_INTERMEDIATE_PIXELS,
        )
    except ImageLimitError as error:
        raise PreprocessError(str(error)) from error


def _white_balance(image: np.ndarray, strength: float) -> np.ndarray:
    if strength == 0:
        return image.copy()
    working = image.astype(np.float32)
    channel_means = working.mean(axis=(0, 1))
    target_mean = float(channel_means.mean())
    gains = target_mean / np.maximum(channel_means, 1.0)
    corrected = working * gains
    blended = working * (1.0 - strength) + corrected * strength
    return np.clip(blended, 0, 255).astype(np.uint8)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise PreprocessError(f"{label}参数必须为有限数值。")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise PreprocessError(f"{label}参数必须为有限数值。") from error
    if not math.isfinite(number):
        raise PreprocessError(f"{label}参数必须为有限数值。")
    return number


def _strict_finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreprocessError(f"{label}参数必须为有限数值。")
    try:
        number = float(value)
    except OverflowError as error:
        raise PreprocessError(f"{label}参数必须为有限数值。") from error
    if not math.isfinite(number):
        raise PreprocessError(f"{label}参数必须为有限数值。")
    return number


def _integer_coordinate(value: object, label: str) -> int:
    number = _finite_number(value, label)
    if not number.is_integer():
        raise PreprocessError(f"{label}坐标必须为整数。")
    return int(number)
