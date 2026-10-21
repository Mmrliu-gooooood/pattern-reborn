"""Bounded local extraction choices for the web editor, with source alpha intact.

Coordinates are pixels in the orientation-corrected working image, never CSS
pixels. Color tolerance is Euclidean CIE Lab distance (L=0..100). Cleanup runs
before ordered manual strokes, so a user's final correction wins.
"""
from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
import hashlib
from importlib.util import find_spec
import json
import os
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageFilter
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from .domain import ProfileId
from .limits import MAX_INTERMEDIATE_EDGE, MAX_INTERMEDIATE_PIXELS, require_bounded_size
from .segmentation import (
    MaskStroke, MobileSamSegmenter, OpenCvSegmenter, SegmentHints,
    SegmentationError, SegmentResult, apply_mask_strokes, combine_with_source_alpha,
)


class ExtractionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mode: Literal["auto", "opencv", "color", "whole", "mobile_sam"] = "auto"
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    seed: tuple[StrictInt, StrictInt] | None = None
    tolerance: float = Field(default=24, ge=1, le=100, allow_inf_nan=False, strict=True)
    minimum_area: StrictInt = Field(default=16, ge=0, le=4096)
    fill_holes: StrictBool = False
    smooth: StrictInt = Field(default=0, ge=0, le=3)


def extraction_capabilities(root: Path | None = None) -> dict[str, object]:
    """Probe without importing Torch, loading weights or making network requests."""
    base = _root(root)
    checkpoint = base / "models/mobile_sam/mobile_sam.pt"
    disabled = os.getenv("PATTERN_REBORN_DISABLE_OPTIONAL") == "1"
    available = not disabled and _installed("mobile_sam") and _installed("torch") and checkpoint.is_file()
    return {
        "modes": ["auto", "opencv", "color", "whole", "mobile_sam"],
        "mobile_sam": {
            "available": available,
            "reason": "本机已有依赖与权重，首次使用会在 CPU 加载并校验。" if available else
                "本机未启用 MobileSAM 或缺少依赖/本地权重；可使用自动、选色或 OpenCV。",
        },
        "advice": "透明素材可选保留整图；纯色剪纸可选色并调容差。复杂照片建议先框选，再用保留/擦除笔修正；请目视检查细线和镂空。",
    }


def extract_local(
    rgb: np.ndarray,
    alpha: np.ndarray,
    profile: ProfileId,
    hints: SegmentHints,
    settings: ExtractionSettings,
    *,
    strokes: Sequence[MaskStroke] = (),
    feather: int = 0,
    root: Path | None = None,
) -> SegmentResult:
    """Produce binary analysis mask and RGBA; neither input array is mutated."""
    _validate_image(rgb, alpha)
    if not isinstance(settings, ExtractionSettings) or not isinstance(hints, SegmentHints):
        raise SegmentationError("提取设置或选区无效。")
    if not isinstance(profile, ProfileId):
        raise SegmentationError("提取配置无效。")
    if isinstance(feather, bool) or not isinstance(feather, int) or not 0 <= feather <= 10:
        raise SegmentationError("柔化必须是 0 到 10 的整数。")
    height, width = alpha.shape
    _validate_coordinates(hints, settings, strokes, width, height)
    warnings: list[str] = []
    mode = settings.mode
    selected = mode
    if mode == "whole" or (mode == "auto" and np.any(alpha < 255)):
        selected = "source-alpha"
        mask = np.where(alpha > 0, 255, 0).astype(np.uint8)
        warnings.append("已保留源图透明度与全部像素；可用擦除笔进一步修正。")
    elif mode == "color":
        if settings.color is not None:
            target = np.asarray([int(settings.color[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.uint8)
        elif settings.seed is not None:
            x, y = settings.seed
            target = rgb[y, x].copy()
        else:
            raise SegmentationError("选色提取需要颜色或图像内的取色点。")
        mask = _color_mask(rgb, target, settings.tolerance)
        warnings.append("选色按颜色相近度保留像素；背景同色时请用擦除笔修正。")
    elif mode == "mobile_sam":
        if hints.box is None and not hints.points:
            raise SegmentationError("MobileSAM 需要先框选主体或添加提示点。")
        result = _mobile_sam(_root(root)).segment(rgb, profile, hints)
        mask = result.mask
        warnings.append("MobileSAM 在本机 CPU 处理；复杂纹理、细线与镂空仍需检查。")
    else:
        candidate = _chromatic_foreground(rgb) if mode == "auto" else None
        if candidate is not None:
            selected = "chromatic-foreground"
            mask = candidate
            warnings.append("自动识别了较鲜明的前景颜色；如误选背景，可改用选色或 OpenCV 并手工修正。")
        else:
            selected = "opencv"
            mask = OpenCvSegmenter(minimum_component_area=1).segment(rgb, profile, hints).mask
            warnings.append("OpenCV 使用颜色/明暗规则；复杂背景可先框选或改用选色，细线请手工检查。")
    if hints.box is not None:
        left, top, right, bottom = hints.box
        limited = np.zeros_like(mask)
        limited[top:bottom, left:right] = mask[top:bottom, left:right]
        mask = limited
    # Whole-image mode must preserve every source pixel unless the user explicitly
    # paints. It is useful even for opaque artwork that needs no segmentation.
    if selected != "source-alpha":
        mask = _cleanup(mask, settings)
    for point in hints.points:
        cv2.circle(mask, (point.x, point.y), 2, 255 if point.keep else 0, thickness=-1)
    mask = apply_mask_strokes(np.ascontiguousarray(mask), strokes)
    mask = combine_with_source_alpha(mask, alpha)
    output_alpha = Image.fromarray(mask)
    if feather:
        output_alpha = output_alpha.filter(ImageFilter.GaussianBlur(feather))
    rgba = Image.fromarray(np.dstack((rgb, np.minimum(np.asarray(output_alpha), alpha))))
    if not np.any(mask):
        warnings.append("未找到前景；可提高选色容差、换提取模式或使用保留笔。")
    return SegmentResult(
        mask=mask, rgba=rgba, profile=profile, hints=hints,
        parameters={"extraction": settings.model_dump(mode="json"), "selected_method": selected, "feather": feather},
        algorithm_version="local-extraction-2.1", warnings=tuple(warnings),
    )


def _color_mask(rgb: np.ndarray, target: np.ndarray, tolerance: float) -> np.ndarray:
    lab = cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
    target_lab = cv2.cvtColor(target.reshape(1, 1, 3).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[0, 0]
    distance = np.sum((lab - target_lab) ** 2, axis=2)
    return np.where(distance <= tolerance ** 2, 255, 0).astype(np.uint8)


def _chromatic_foreground(rgb: np.ndarray) -> np.ndarray | None:
    """Conservative hue selection for saturated paper/paint against a dull photo."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    chromatic = (hsv[:, :, 1] >= 100) & (hsv[:, :, 2] >= 45)
    if np.count_nonzero(chromatic) < max(16, chromatic.size * 0.01):
        return None
    histogram = np.bincount(hsv[:, :, 0][chromatic], minlength=180)
    # A circular 15-bin window avoids splitting red at hue 0/179.
    support = sum(np.roll(histogram, offset) for offset in range(-7, 8))
    hue = int(np.argmax(support))
    difference = np.abs(hsv[:, :, 0].astype(np.int16) - hue)
    candidate = chromatic & (np.minimum(difference, 180 - difference) <= 12)
    fraction = float(np.count_nonzero(candidate)) / candidate.size
    border = np.concatenate((candidate[0], candidate[-1], candidate[:, 0], candidate[:, -1]))
    if np.mean(border) <= 0.1:
        # Keep the original low-light candidate when it is already isolated;
        # dark inks and paper must not acquire a global brightness cutoff.
        return np.where(candidate, 255, 0).astype(np.uint8) if 0.01 <= fraction <= 0.7 else None

    # Dark reddish wood can share the dominant hue with bright red paper and
    # contaminate the image border. Retry only that same hue, using a measured
    # brightness split. Require clear separation from the colored border so a
    # uniformly colored background is still rejected.
    value = hsv[:, :, 2]
    split, _ = cv2.threshold(value[candidate].reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    border_value = np.concatenate((value[0], value[-1], value[:, 0], value[:, -1]))[border]
    candidate &= value > split
    bright_value = value[candidate]
    if not bright_value.size or float(np.percentile(bright_value, 10)) < float(np.percentile(border_value, 90)) + 32:
        return None
    fraction = float(np.count_nonzero(candidate)) / candidate.size
    border = np.concatenate((candidate[0], candidate[-1], candidate[:, 0], candidate[:, -1]))
    if not 0.01 <= fraction <= 0.7 or np.mean(border) > 0.1:
        return None
    return np.where(candidate, 255, 0).astype(np.uint8)


def _cleanup(mask: np.ndarray, settings: ExtractionSettings) -> np.ndarray:
    cleaned = mask.copy()
    if settings.smooth:
        radius = settings.smooth
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)
    if settings.fill_holes:
        padded = np.pad(cleaned, 1, constant_values=0)
        cv2.floodFill(padded, None, (0, 0), 255)
        cleaned = cv2.bitwise_or(cleaned, cv2.bitwise_not(padded[1:-1, 1:-1]))
    if settings.minimum_area > 1:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
        keep = np.zeros(count, dtype=np.uint8)
        keep[1:] = np.where(stats[1:, cv2.CC_STAT_AREA] >= settings.minimum_area, 255, 0)
        cleaned = keep[labels]
    return np.ascontiguousarray(cleaned)


def _validate_image(rgb: np.ndarray, alpha: np.ndarray) -> None:
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise SegmentationError("图像必须是 RGB uint8 数组。")
    if not isinstance(alpha, np.ndarray) or alpha.dtype != np.uint8 or alpha.shape != rgb.shape[:2]:
        raise SegmentationError("源透明度必须与图像尺寸一致。")
    require_bounded_size(rgb.shape[1], rgb.shape[0], label="提取图像尺寸",
                         max_edge=MAX_INTERMEDIATE_EDGE, max_pixels=MAX_INTERMEDIATE_PIXELS)


def _validate_coordinates(hints, settings, strokes, width: int, height: int) -> None:
    if hints.box is not None:
        left, top, right, bottom = hints.box
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise SegmentationError("选区必须位于图像内，且宽高不能为零。")
    points = [(p.x, p.y) for p in hints.points]
    if settings.seed is not None:
        points.append(settings.seed)
    if not isinstance(strokes, Sequence) or len(strokes) > 100:
        raise SegmentationError("笔触数量超出上限。")
    for stroke in strokes:
        if not isinstance(stroke, MaskStroke) or not 1 <= stroke.width <= 200:
            raise SegmentationError("笔触设置无效。")
        points.extend(stroke.points)
    if len(points) > 20000 or any(not (0 <= x < width and 0 <= y < height) for x, y in points):
        raise SegmentationError("取色点、提示点或笔触超出图像范围/数量上限。")


def _root(root: Path | None) -> Path:
    return Path(root).resolve() if root is not None else Path(__file__).resolve().parents[2]


def _installed(module: str) -> bool:
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _mobile_sam(root: Path) -> MobileSamSegmenter:
    if not extraction_capabilities(root)["mobile_sam"]["available"]:
        raise SegmentationError("MobileSAM 当前不可用；请使用自动、选色或 OpenCV。不会自动下载模型。")
    checkpoint = root / "models/mobile_sam/mobile_sam.pt"
    return _load_mobile_sam(str(checkpoint), checkpoint.stat().st_mtime_ns, checkpoint.stat().st_size)


@lru_cache(maxsize=1)
def _load_mobile_sam(checkpoint: str, _mtime: int, _size: int) -> MobileSamSegmenter:
    try:
        path = Path(checkpoint)
        metadata = json.loads((path.parents[2] / "scripts/mobile_sam_checksum.json").read_text(encoding="utf-8"))
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != metadata["sha256"]:
            raise ValueError("checkpoint checksum")
        from mobile_sam import SamPredictor, sam_model_registry
        model = sam_model_registry["vit_t"](checkpoint=checkpoint)
        model.to(device="cpu")
        model.eval()
        return MobileSamSegmenter(SamPredictor(model))
    except Exception as error:
        raise SegmentationError("MobileSAM 本地权重校验或加载失败；可继续使用其他本地模式。") from error
