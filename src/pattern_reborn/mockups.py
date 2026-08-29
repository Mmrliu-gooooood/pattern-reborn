# -*- coding: utf-8 -*-
"""Rights-cleared cultural-product mockup templates and compositing."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw

from pattern_reborn.images import save_png_atomic


class MockupError(ValueError):
    """贴图模板或合成输入无效。"""


_REQUIRED_TEMPLATE_IDS = ("bookmark", "tote_bag", "phone_case")
_DEFAULT_ASSETS = Path(__file__).resolve().parents[2] / "assets" / "mockups"
_TEMPLATE_DATE = "2026-08-29"
_CREATOR = "Pattern Reborn team"
_LICENSE = "project-original"

_PAPER = (232, 224, 212, 255)
_INK = (47, 79, 68, 255)
_CREAM = (247, 241, 230, 255)
_VERMILION = (179, 59, 52, 255)
_GOLD = (184, 151, 90, 255)
_CASE = (52, 58, 56, 255)
_CAMERA = (30, 32, 31, 255)

_TEMPLATE_SPECS: dict[str, dict[str, object]] = {
    "bookmark": {
        "dimensions": (240, 640),
        "placement_polygon": ((48, 80), (192, 80), (192, 560), (48, 560)),
    },
    "tote_bag": {
        "dimensions": (480, 560),
        "placement_polygon": ((110, 180), (370, 180), (370, 480), (110, 480)),
    },
    "phone_case": {
        "dimensions": (280, 560),
        "placement_polygon": ((56, 108), (224, 108), (224, 500), (56, 500)),
    },
}


@dataclass(frozen=True, slots=True)
class MockupTemplate:
    id: str
    path: Path
    canvas_size: tuple[int, int]
    placement_polygon: tuple[tuple[int, int], ...]
    creator: str
    license: str
    date: str


@dataclass(frozen=True, slots=True)
class ArtworkRef:
    path: Path
    ai_assisted: bool = False


@dataclass(frozen=True, slots=True)
class MockupOptions:
    pass


@dataclass(frozen=True, slots=True)
class MockupResult:
    image: Image.Image
    ai_assisted: bool


def load_mockup_catalog(assets_dir: Path | None = None) -> dict[str, MockupTemplate]:
    root = Path(assets_dir) if assets_dir is not None else _DEFAULT_ASSETS
    metadata_path = root / "metadata.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MockupError("贴图模板元数据无法读取。") from error
    records = payload.get("templates") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise MockupError("贴图模板元数据格式无效。")

    catalog: dict[str, MockupTemplate] = {}
    for record in records:
        template = _template_from_metadata(root, record)
        catalog[template.id] = template
    missing = [template_id for template_id in _REQUIRED_TEMPLATE_IDS if template_id not in catalog]
    if missing or set(catalog) != set(_REQUIRED_TEMPLATE_IDS):
        raise MockupError("贴图模板目录必须包含书签、帆布袋和手机壳。")
    return catalog


def compose_mockup(
    template: MockupTemplate,
    artwork: ArtworkRef,
    options: MockupOptions = MockupOptions(),
) -> MockupResult:
    _ = options
    try:
        with Image.open(template.path) as source:
            canvas = source.convert("RGBA")
    except (OSError, ValueError) as error:
        raise MockupError("贴图模板无法打开。") from error
    if canvas.size != template.canvas_size:
        raise MockupError("贴图模板尺寸与元数据不一致。")

    try:
        with Image.open(artwork.path) as source:
            motif = source.convert("RGBA")
    except (OSError, ValueError) as error:
        raise MockupError("贴图纹样无法打开。") from error

    warped = _warp_artwork(motif, template.placement_polygon, template.canvas_size)
    composed = Image.alpha_composite(canvas, warped)
    return MockupResult(image=composed, ai_assisted=bool(artwork.ai_assisted))


def save_composed_mockup(result: MockupResult, destination: Path) -> None:
    dest = Path(destination)
    save_png_atomic(result.image, dest)
    sidecar = dest.with_suffix(".json")
    payload = {"ai_assisted": bool(result.ai_assisted)}
    sidecar.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _template_from_metadata(root: Path, record: object) -> MockupTemplate:
    if not isinstance(record, dict):
        raise MockupError("贴图模板元数据格式无效。")
    template_id = record.get("id")
    filename = record.get("filename")
    creator = record.get("creator")
    license_id = record.get("license")
    date = record.get("date")
    dimensions = record.get("dimensions")
    polygon = record.get("placement_polygon")
    if (
        not isinstance(template_id, str)
        or not isinstance(filename, str)
        or creator != _CREATOR
        or license_id != _LICENSE
        or not isinstance(date, str)
        or not date
        or not _is_size(dimensions)
        or not _is_polygon(polygon)
    ):
        raise MockupError("贴图模板元数据字段不完整。")
    path = root / filename
    if path.name != f"{template_id}.png" or not path.is_file():
        raise MockupError("贴图模板文件缺失或文件名不匹配。")
    with Image.open(path) as image:
        if image.size != (int(dimensions[0]), int(dimensions[1])):
            raise MockupError("贴图模板尺寸与元数据不一致。")
    return MockupTemplate(
        id=template_id,
        path=path,
        canvas_size=(int(dimensions[0]), int(dimensions[1])),
        placement_polygon=tuple((int(x), int(y)) for x, y in polygon),
        creator=creator,
        license=license_id,
        date=date,
    )


def _is_size(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value)
    )


def _is_polygon(value: object) -> bool:
    if not isinstance(value, list) or len(value) < 4:
        return False
    for point in value:
        if not (isinstance(point, list) and len(point) == 2):
            return False
        if any(isinstance(item, bool) or not isinstance(item, int) for item in point):
            return False
    return True


def _warp_artwork(
    artwork: Image.Image,
    polygon: Sequence[tuple[int, int]],
    canvas_size: tuple[int, int],
) -> Image.Image:
    width, height = artwork.size
    source_quad = ((0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height)))
    dest_quad = tuple((float(x), float(y)) for x, y in polygon[:4])
    coeffs = _perspective_coeffs(source_quad, dest_quad)
    return artwork.transform(
        canvas_size,
        Image.Transform.PERSPECTIVE,
        coeffs,
        resample=Image.Resampling.BICUBIC,
    )


def _perspective_coeffs(
    source: Sequence[tuple[float, float]],
    destination: Sequence[tuple[float, float]],
) -> tuple[float, ...]:
    matrix = []
    observed = []
    for (source_x, source_y), (dest_x, dest_y) in zip(source, destination, strict=True):
        matrix.append([dest_x, dest_y, 1.0, 0.0, 0.0, 0.0, -source_x * dest_x, -source_x * dest_y])
        observed.append(source_x)
        matrix.append([0.0, 0.0, 0.0, dest_x, dest_y, 1.0, -source_y * dest_x, -source_y * dest_y])
        observed.append(source_y)
    try:
        solved = np.linalg.solve(np.asarray(matrix, dtype=np.float64), np.asarray(observed, dtype=np.float64))
    except np.linalg.LinAlgError as error:
        raise MockupError("贴图放置区域无效。") from error
    return tuple(float(value) for value in solved)


def _render_neutral_template(template_id: str) -> Image.Image:
    spec = _TEMPLATE_SPECS[template_id]
    width, height = spec["dimensions"]
    image = Image.new("RGBA", (width, height), _PAPER)
    draw = ImageDraw.Draw(image)
    if template_id == "bookmark":
        draw.rounded_rectangle((30, 24, 210, 616), radius=18, fill=_CREAM, outline=_INK, width=3)
        draw.ellipse((108, 36, 132, 60), outline=_INK, width=2)
        draw.ellipse((114, 42, 126, 54), fill=_VERMILION)
        draw.rectangle((48, 80, 192, 560), outline=_GOLD, width=1)
    elif template_id == "tote_bag":
        draw.arc((120, 36, 220, 188), start=180, end=0, fill=_INK, width=10)
        draw.arc((260, 36, 360, 188), start=180, end=0, fill=_INK, width=10)
        draw.rounded_rectangle((80, 140, 400, 520), radius=28, fill=_CREAM, outline=_INK, width=4)
        draw.rectangle((110, 180, 370, 480), outline=_GOLD, width=1)
    else:
        draw.rounded_rectangle((36, 24, 244, 536), radius=36, fill=_CASE, outline=_INK, width=3)
        draw.ellipse((56, 40, 100, 84), fill=_CAMERA, outline=_GOLD, width=2)
        draw.ellipse((72, 56, 84, 68), fill=_CREAM)
        draw.rectangle((56, 108, 224, 500), outline=_GOLD, width=1)
    return image


def _write_committed_assets(assets_dir: Path | None = None) -> None:
    root = Path(assets_dir) if assets_dir is not None else _DEFAULT_ASSETS
    root.mkdir(parents=True, exist_ok=True)
    templates = []
    for template_id in _REQUIRED_TEMPLATE_IDS:
        spec = _TEMPLATE_SPECS[template_id]
        image = _render_neutral_template(template_id)
        save_png_atomic(image, root / f"{template_id}.png")
        templates.append(
            {
                "id": template_id,
                "filename": f"{template_id}.png",
                "creator": _CREATOR,
                "license": _LICENSE,
                "date": _TEMPLATE_DATE,
                "dimensions": list(spec["dimensions"]),
                "placement_polygon": [list(point) for point in spec["placement_polygon"]],
            }
        )
    payload = {"templates": templates}
    (root / "metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
