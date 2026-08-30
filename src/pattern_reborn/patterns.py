"""Deterministic motif recomposition driven by a stored seed and layout parameters."""

from __future__ import annotations

from enum import Enum
import math
import re

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .limits import (
    MAX_CANVAS_EDGE,
    MAX_CANVAS_PIXELS,
    MAX_INTERMEDIATE_EDGE,
    MAX_INTERMEDIATE_PIXELS,
    ImageLimitError,
    require_bounded_size,
    require_scaled_size,
)

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

    def __init__(self, /, **data: object) -> None:
        if "canvas" in data:
            data["canvas"] = _require_canvas(data["canvas"])
        super().__init__(**data)

    @field_validator("canvas", mode="before")
    @classmethod
    def require_positive_canvas(cls, value: object) -> tuple[int, int]:
        return _require_canvas(value)

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

    @field_validator("scale", mode="before")
    @classmethod
    def require_positive_scale(cls, value: object) -> float:
        try:
            require_scaled_size(
                1,
                1,
                value,
                label="缩放",
                max_pixels=MAX_INTERMEDIATE_PIXELS,
            )
        except ImageLimitError as error:
            raise PatternError(str(error)) from error
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


def _require_canvas(value: object) -> tuple[int, int]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise PatternError("画布尺寸必须包含宽度和高度。")
    try:
        return require_bounded_size(
            value[0],
            value[1],
            label="画布尺寸",
            max_edge=MAX_CANVAS_EDGE,
            max_pixels=MAX_CANVAS_PIXELS,
        )
    except ImageLimitError as error:
        raise PatternError(str(error)) from error


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
    try:
        require_bounded_size(
            motif.width,
            motif.height,
            label="纹样图像",
            max_edge=MAX_INTERMEDIATE_EDGE,
            max_pixels=MAX_INTERMEDIATE_PIXELS,
        )
    except ImageLimitError as error:
        raise PatternError(str(error)) from error
    stamp = motif.convert("RGBA").copy()
    stamp = _apply_palette_substitutions(stamp, request.palette_substitutions)
    stamp = _affine_scale(stamp, request.scale)
    if request.angle == 0.0:
        return stamp
    return _rotate_expanded(stamp, request.angle)


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
    try:
        width, height = require_scaled_size(
            image.width,
            image.height,
            scale,
            label="缩放图像",
            max_pixels=MAX_INTERMEDIATE_PIXELS,
        )
    except ImageLimitError as error:
        raise PatternError(str(error)) from error
    matrix = (1.0 / scale, 0.0, 0.0, 0.0, 1.0 / scale, 0.0)
    return image.transform(
        (width, height),
        Image.Transform.AFFINE,
        matrix,
        resample=Image.Resampling.BICUBIC,
    )


def _rotate_expanded(image: Image.Image, angle: float) -> Image.Image:
    width, height = _expanded_rotation_size(image.width, image.height, angle)
    try:
        require_bounded_size(
            width,
            height,
            label="旋转图像",
            max_edge=MAX_INTERMEDIATE_EDGE,
            max_pixels=MAX_INTERMEDIATE_PIXELS,
        )
    except ImageLimitError as error:
        raise PatternError(str(error)) from error
    return image.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(0, 0, 0, 0),
    )


def _expanded_rotation_size(width: int, height: int, angle: float) -> tuple[int, int]:
    normalized = angle % 360.0
    if normalized in (0.0, 180.0):
        return width, height
    if normalized in (90.0, 270.0):
        return height, width

    radians = -math.radians(normalized)
    cosine = round(math.cos(radians), 15)
    sine = round(math.sin(radians), 15)
    center_x = width / 2
    center_y = height / 2
    translate_x = cosine * -center_x + sine * -center_y + center_x
    translate_y = -sine * -center_x + cosine * -center_y + center_y
    corners = (
        (0, 0),
        (width, 0),
        (width, height),
        (0, height),
    )
    transformed = [
        (
            cosine * x + sine * y + translate_x,
            -sine * x + cosine * y + translate_y,
        )
        for x, y in corners
    ]
    x_values = [point[0] for point in transformed]
    y_values = [point[1] for point in transformed]
    return (
        math.ceil(max(x_values)) - math.floor(min(x_values)),
        math.ceil(max(y_values)) - math.floor(min(y_values)),
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
    unit_size = (stamp.width * 2, stamp.height)
    try:
        require_bounded_size(
            *unit_size,
            label="镜像单元",
            max_edge=MAX_INTERMEDIATE_EDGE,
            max_pixels=MAX_INTERMEDIATE_PIXELS,
        )
    except ImageLimitError as error:
        raise PatternError(str(error)) from error
    unit = Image.new("RGBA", unit_size, (0, 0, 0, 0))
    unit.alpha_composite(stamp, (0, 0))
    unit.alpha_composite(stamp.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (stamp.width, 0))
    _tile(canvas, unit, spacing)


def _compose_four_way(canvas: Image.Image, stamp: Image.Image, spacing: int) -> None:
    unit_size = (stamp.width * 2, stamp.height * 2)
    try:
        require_bounded_size(
            *unit_size,
            label="四向单元",
            max_edge=MAX_INTERMEDIATE_EDGE,
            max_pixels=MAX_INTERMEDIATE_PIXELS,
        )
    except ImageLimitError as error:
        raise PatternError(str(error)) from error
    flipped_x = stamp.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    flipped_y = stamp.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    flipped_xy = flipped_x.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    unit = Image.new("RGBA", unit_size, (0, 0, 0, 0))
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
        rotated = _rotate_expanded(stamp, offset + index * (360 / copies))
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
        oriented = _rotate_expanded(stamp, -degrees)
        x = round(center_x + radius * math.cos(radians) - oriented.width / 2)
        y = round(center_y + radius * math.sin(radians) - oriented.height / 2)
        canvas.alpha_composite(oriented, (x, y))
