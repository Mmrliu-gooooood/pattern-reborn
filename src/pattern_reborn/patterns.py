"""Deterministic motif recomposition driven by a stored seed and layout parameters."""

from __future__ import annotations

from enum import Enum
import math
import re

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_COLOR = re.compile(r"^#[0-9A-F]{6}$")


class PatternError(ValueError):
    """纹样重组参数或输入无效。"""


class LayoutKind(str, Enum):
    MIRROR = "mirror"
    ROTATION = "rotation"
    RADIAL = "radial"
    BORDER = "border"
    TWO_WAY = "two_way"
    FOUR_WAY = "four_way"


class PatternRequest(BaseModel):
    """Persisted recomposition parameters. Defaults stay conservative and explicit."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    layout: LayoutKind
    canvas: tuple[int, int]
    seed: int = 0
    spacing: int = 0
    scale: float = 1.0
    angle: float = 0.0
    palette_substitutions: dict[str, str] = Field(default_factory=dict)

    @field_validator("canvas")
    @classmethod
    def require_positive_canvas(cls, value: tuple[int, int]) -> tuple[int, int]:
        if not isinstance(value, tuple) or len(value) != 2:
            raise PatternError("画布尺寸必须包含宽度和高度。")
        width, height = value
        if (
            isinstance(width, bool)
            or isinstance(height, bool)
            or not isinstance(width, int)
            or not isinstance(height, int)
            or width <= 0
            or height <= 0
        ):
            raise PatternError("画布尺寸必须为正整数。")
        return (width, height)

    @field_validator("seed")
    @classmethod
    def require_integer_seed(cls, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise PatternError("随机种子必须是整数。")
        return value

    @field_validator("spacing")
    @classmethod
    def require_non_negative_spacing(cls, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PatternError("间距必须是非负整数。")
        return value

    @field_validator("scale")
    @classmethod
    def require_positive_scale(cls, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise PatternError("缩放必须为正的有限数值。")
        return float(value)

    @field_validator("angle")
    @classmethod
    def require_finite_angle(cls, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise PatternError("旋转角度必须是有限数值。")
        return float(value)

    @field_validator("palette_substitutions")
    @classmethod
    def require_hex_palette_pairs(cls, value: dict[str, str]) -> dict[str, str]:
        if not isinstance(value, dict):
            raise PatternError("调色板替换必须是颜色对照表。")
        normalized: dict[str, str] = {}
        for source, target in value.items():
            source_hex = str(source).upper()
            target_hex = str(target).upper()
            if not _HEX_COLOR.fullmatch(source_hex) or not _HEX_COLOR.fullmatch(target_hex):
                raise PatternError("调色板替换必须使用 #RRGGBB 颜色。")
            normalized[source_hex] = target_hex
        return normalized


def compose_pattern(motif: Image.Image, request: PatternRequest) -> Image.Image:
    """Return an RGBA canvas filled by a deterministic layout of the motif."""
    if not isinstance(motif, Image.Image):
        raise PatternError("纹样图像无效。")
    if not isinstance(request, PatternRequest):
        raise PatternError("纹样重组请求无效。")

    stamp = _prepare_stamp(motif, request)
    canvas = Image.new("RGBA", request.canvas, (0, 0, 0, 0))
    if request.layout is LayoutKind.MIRROR:
        _compose_mirror(canvas, stamp, request.spacing)
    elif request.layout is LayoutKind.ROTATION:
        _compose_rotation(canvas, stamp, request.seed)
    elif request.layout is LayoutKind.RADIAL:
        _compose_radial(canvas, stamp, request.spacing, request.seed)
    elif request.layout is LayoutKind.BORDER:
        _compose_border(canvas, stamp, request.spacing)
    elif request.layout is LayoutKind.TWO_WAY:
        _tile(canvas, stamp, request.spacing)
    elif request.layout is LayoutKind.FOUR_WAY:
        _compose_four_way(canvas, stamp, request.spacing)
    else:
        raise PatternError("不支持的纹样布局。")
    return canvas


def _prepare_stamp(motif: Image.Image, request: PatternRequest) -> Image.Image:
    stamp = motif.convert("RGBA").copy()
    stamp = _apply_palette_substitutions(stamp, request.palette_substitutions)
    stamp = _affine_scale(stamp, request.scale)
    if request.angle == 0.0:
        return stamp
    return stamp.rotate(
        request.angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(0, 0, 0, 0),
    )


def _apply_palette_substitutions(image: Image.Image, substitutions: dict[str, str]) -> Image.Image:
    if not substitutions:
        return image
    mapping = {_rgb_from_hex(source): _rgb_from_hex(target) for source, target in substitutions.items()}
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            replacement = mapping.get((red, green, blue))
            if replacement is not None:
                pixels[x, y] = (*replacement, alpha)
    return image


def _rgb_from_hex(value: str) -> tuple[int, int, int]:
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def _affine_scale(image: Image.Image, scale: float) -> Image.Image:
    if scale == 1.0:
        return image
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    matrix = (1.0 / scale, 0.0, 0.0, 0.0, 1.0 / scale, 0.0)
    return image.transform(
        (width, height),
        Image.Transform.AFFINE,
        matrix,
        resample=Image.Resampling.BICUBIC,
    )


def _tile(canvas: Image.Image, stamp: Image.Image, spacing: int) -> None:
    step_x = stamp.width + spacing
    step_y = stamp.height + spacing
    if step_x <= 0 or step_y <= 0:
        canvas.alpha_composite(stamp, (0, 0))
        return
    y = 0
    while y < canvas.height:
        x = 0
        while x < canvas.width:
            canvas.alpha_composite(stamp, (x, y))
            x += step_x
        y += step_y


def _compose_mirror(canvas: Image.Image, stamp: Image.Image, spacing: int) -> None:
    unit = Image.new("RGBA", (stamp.width * 2, stamp.height), (0, 0, 0, 0))
    unit.alpha_composite(stamp, (0, 0))
    unit.alpha_composite(stamp.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (stamp.width, 0))
    _tile(canvas, unit, spacing)


def _compose_four_way(canvas: Image.Image, stamp: Image.Image, spacing: int) -> None:
    flipped_x = stamp.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    flipped_y = stamp.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    flipped_xy = flipped_x.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    unit = Image.new("RGBA", (stamp.width * 2, stamp.height * 2), (0, 0, 0, 0))
    unit.alpha_composite(stamp, (0, 0))
    unit.alpha_composite(flipped_x, (stamp.width, 0))
    unit.alpha_composite(flipped_y, (0, stamp.height))
    unit.alpha_composite(flipped_xy, (stamp.width, stamp.height))
    _tile(canvas, unit, spacing)


def _compose_border(canvas: Image.Image, stamp: Image.Image, spacing: int) -> None:
    step_x = max(1, stamp.width + spacing)
    step_y = max(1, stamp.height + spacing)
    x = 0
    while x < canvas.width:
        canvas.alpha_composite(stamp, (x, 0))
        canvas.alpha_composite(stamp, (x, canvas.height - stamp.height))
        x += step_x
    y = 0
    while y < canvas.height:
        canvas.alpha_composite(stamp, (0, y))
        canvas.alpha_composite(stamp, (canvas.width - stamp.width, y))
        y += step_y


def _compose_rotation(canvas: Image.Image, stamp: Image.Image, seed: int) -> None:
    copies = 4
    offset = seed % 360
    center_x = canvas.width / 2
    center_y = canvas.height / 2
    for index in range(copies):
        rotated = stamp.rotate(
            offset + index * (360 / copies),
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0, 0),
        )
        x = round(center_x - rotated.width / 2)
        y = round(center_y - rotated.height / 2)
        canvas.alpha_composite(rotated, (x, y))


def _compose_radial(canvas: Image.Image, stamp: Image.Image, spacing: int, seed: int) -> None:
    copies = 8
    radius = min(canvas.size) * 0.28 + spacing
    start = seed % 360
    center_x = canvas.width / 2
    center_y = canvas.height / 2
    for index in range(copies):
        degrees = start + index * (360 / copies)
        radians = math.radians(degrees)
        oriented = stamp.rotate(
            -degrees,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0, 0),
        )
        x = round(center_x + radius * math.cos(radians) - oriented.width / 2)
        y = round(center_y + radius * math.sin(radians) - oriented.height / 2)
        canvas.alpha_composite(oriented, (x, y))
