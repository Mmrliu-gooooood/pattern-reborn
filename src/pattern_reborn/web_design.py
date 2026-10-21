"""Local workspace composition with texture-preserving palette replacement."""
from __future__ import annotations

import re
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .analysis import analyze_palette
from .patterns import LayoutKind, PatternRequest, compose_pattern, fit_motif_to_canvas


class DesignSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layout: LayoutKind = LayoutKind.FOUR_WAY
    width: int = Field(default=1024, ge=64, le=4096, strict=True)
    height: int = Field(default=1024, ge=64, le=4096, strict=True)
    scale: float = Field(default=0.35, ge=0.05, le=1)
    angle: float = Field(default=0, ge=-180, le=180)
    spacing: int = Field(default=16, ge=0, le=256, strict=True)
    seed: int = Field(default=0, ge=0, le=2147483647, strict=True)
    background: str | None = None
    colors: dict[str, str] = Field(default_factory=dict, max_length=6)

    @field_validator("background")
    @classmethod
    def color(cls, value):
        if value is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("颜色必须为 #RRGGBB。")
        return value.upper() if value else None

    @field_validator("colors")
    @classmethod
    def color_map(cls, value):
        return {cls.color(k): cls.color(v) for k, v in value.items()}

    def request(self):
        return PatternRequest(layout=self.layout, canvas=(self.width, self.height),
                              scale=self.scale, angle=self.angle, spacing=self.spacing, seed=self.seed)


class DesignEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    settings: DesignSettings


def palette_for(image: Image.Image) -> list[str]:
    sample = image.convert("RGBA")
    sample.thumbnail((256, 256))
    pixels = np.asarray(sample)
    visible = pixels[:, :, :3][pixels[:, :, 3] > 0]
    if not len(visible):
        raise ValueError("纹样为空，请先保存有效的提取结果。")
    count = min(6, len(np.unique(visible, axis=0)))
    return [c.hex_value.upper() for c in analyze_palette(sample, count=count, seed=0)]


def recolor(image: Image.Image, palette: list[str], replacements: dict[str, str]) -> Image.Image:
    """Shift each palette group by its center delta, retaining local texture and alpha."""
    if not replacements:
        return image.copy()
    if set(replacements) - set(palette):
        raise ValueError("原色已改变，请重新打开重组工作台。")
    rgb = lambda color: [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    centers = np.array([rgb(c) for c in palette], dtype=np.float32)
    targets = np.array([rgb(replacements.get(c, c)) for c in palette], dtype=np.float32)
    result = np.array(image.convert("RGBA"))
    flat = result.reshape(-1, 4)
    for start in range(0, len(flat), 65536):
        block = flat[start:start + 65536]
        values = block[:, :3].astype(np.float32)
        groups = ((values[:, None, :] - centers) ** 2).sum(axis=2).argmin(axis=1)
        block[:, :3] = np.clip(values + (targets - centers)[groups], 0, 255).astype(np.uint8)
    return Image.fromarray(result)


def render_design(image: Image.Image, settings: DesignSettings) -> Image.Image:
    motif = image.convert("RGBA")
    box = motif.getchannel("A").getbbox()
    if box is None:
        raise ValueError("纹样为空。")
    motif = recolor(motif, palette_for(motif), settings.colors).crop(box)
    # Normalize the motif to the selected canvas so scale has consistent meaning.
    ratio = min(settings.width / motif.width, settings.height / motif.height)
    motif = motif.resize((max(1, round(motif.width * ratio)), max(1, round(motif.height * ratio))), Image.Resampling.LANCZOS)
    result = compose_pattern(fit_motif_to_canvas(motif, (settings.width, settings.height)), settings.request())
    if settings.background:
        result = Image.alpha_composite(Image.new("RGBA", result.size, settings.background), result)
    return result
