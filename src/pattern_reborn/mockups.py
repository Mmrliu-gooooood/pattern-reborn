# -*- coding: utf-8 -*-
"""Rights-cleared cultural-product mockup templates and compositing."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from typing import Sequence
from uuid import uuid4

import numpy as np
from PIL import Image, ImageDraw

from pattern_reborn.images import ImageValidationError, load_safe_image, save_png_atomic


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
    canvas = _load_mockup_image(template.path, label="贴图模板").convert("RGBA")
    if canvas.size != template.canvas_size:
        raise MockupError("贴图模板尺寸与元数据不一致。")

    motif = _load_mockup_image(artwork.path, label="贴图纹样").convert("RGBA")

    warped = _warp_artwork(motif, template.placement_polygon, template.canvas_size)
    composed = Image.alpha_composite(canvas, warped)
    return MockupResult(image=composed, ai_assisted=bool(artwork.ai_assisted))


def save_composed_mockup(result: MockupResult, destination: Path) -> None:
    save_mockup_bundle_atomic(result, destination)


def save_mockup_bundle_atomic(result: MockupResult, destination: Path) -> None:
    """Publish a mockup PNG and provenance sidecar as a recoverable pair."""
    dest = Path(destination)
    sidecar = dest.with_suffix(".json")
    payload = {"ai_assisted": bool(result.ai_assisted)}
    transaction: Path | None = None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _recover_interrupted_mockup_transactions(dest)
        transaction = dest.parent / f".{dest.stem}.{uuid4().hex}.mockup-txn"
        transaction.mkdir()
        previous = {
            "png": dest.exists(),
            "json": sidecar.exists(),
        }
        _write_transaction_journal(transaction, dest, previous, state="preparing")
        _copy_previous_file(dest, transaction / "previous.png", previous["png"])
        _copy_previous_file(sidecar, transaction / "previous.json", previous["json"])
        _write_staged_png(result.image, transaction / "staged.png")
        _write_staged_json(transaction / "staged.json", payload)
        _write_transaction_journal(transaction, dest, previous, state="prepared")

        os.replace(transaction / "staged.png", dest)
        _write_transaction_journal(transaction, dest, previous, state="png_published")
        os.replace(transaction / "staged.json", sidecar)
        _write_transaction_journal(transaction, dest, previous, state="committed")
    except (ImageValidationError, OSError, ValueError, TypeError) as error:
        if transaction is not None:
            try:
                _restore_mockup_pair(transaction, dest, sidecar)
            except OSError:
                pass
        raise MockupError("贴图保存失败，已尝试恢复原有文件。") from error
    else:
        if transaction is not None:
            _discard_transaction(transaction)


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
    image = _load_mockup_image(path, label="贴图模板")
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


def _load_mockup_image(path: Path, *, label: str) -> Image.Image:
    try:
        return load_safe_image(path)
    except ImageValidationError as error:
        raise MockupError(f"{label}图像无法安全解码或格式、尺寸无效。") from error


def _write_staged_png(image: Image.Image, path: Path) -> None:
    if not isinstance(image, Image.Image):
        raise ImageValidationError("待保存的图像无效。")
    with path.open("xb") as handle:
        image.save(handle, format="PNG")
        handle.flush()
        _flush_to_disk(handle)


def _write_staged_json(path: Path, payload: dict[str, bool]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        _flush_to_disk(handle)


def _write_transaction_journal(
    transaction: Path,
    destination: Path,
    previous: dict[str, bool],
    *,
    state: str,
) -> None:
    journal = transaction / "journal.json"
    payload = {
        "destination": destination.name,
        "sidecar": destination.with_suffix(".json").name,
        "previous": previous,
        "state": state,
    }
    with journal.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        _flush_to_disk(handle)


def _copy_previous_file(source: Path, backup: Path, exists: bool) -> None:
    if exists:
        shutil.copyfile(source, backup)


def _recover_interrupted_mockup_transactions(destination: Path) -> None:
    for transaction in destination.parent.glob(f".{destination.stem}.*.mockup-txn"):
        if not transaction.is_dir():
            continue
        try:
            journal = _read_transaction_journal(transaction, destination)
            if journal["state"] in {"prepared", "png_published"}:
                _restore_mockup_pair(transaction, destination, destination.with_suffix(".json"), journal)
            _discard_transaction(transaction)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            raise MockupError("检测到无法安全恢复的贴图发布事务。")


def _restore_mockup_pair(
    transaction: Path,
    destination: Path,
    sidecar: Path,
    journal: dict[str, object] | None = None,
) -> None:
    record = journal if journal is not None else _read_transaction_journal(transaction, destination)
    previous = record["previous"]
    if not isinstance(previous, dict):
        raise OSError("mockup transaction journal is invalid")
    _restore_previous_file(transaction / "previous.png", destination, previous.get("png"))
    _restore_previous_file(transaction / "previous.json", sidecar, previous.get("json"))
    _discard_transaction(transaction)


def _read_transaction_journal(transaction: Path, destination: Path) -> dict[str, object]:
    payload = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("destination") != destination.name
        or payload.get("sidecar") != destination.with_suffix(".json").name
        or payload.get("state") not in {"preparing", "prepared", "png_published", "committed"}
    ):
        raise OSError("mockup transaction journal is invalid")
    return payload


def _restore_previous_file(backup: Path, destination: Path, existed: object) -> None:
    if existed is True:
        restoration = backup.parent / f".{backup.name}.{uuid4().hex}.restore"
        try:
            shutil.copyfile(backup, restoration)
            os.replace(restoration, destination)
        finally:
            restoration.unlink(missing_ok=True)
    elif existed is False:
        destination.unlink(missing_ok=True)
    else:
        raise OSError("mockup transaction journal is invalid")


def _discard_transaction(transaction: Path) -> None:
    shutil.rmtree(transaction, ignore_errors=True)


def _flush_to_disk(handle: object) -> None:
    try:
        os.fsync(handle.fileno())  # type: ignore[attr-defined]
    except OSError:
        pass


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
