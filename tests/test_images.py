from pathlib import Path
import struct
import zlib

from PIL import Image, PngImagePlugin
import pytest

import pattern_reborn.images as images_module
from pattern_reborn.images import ImageValidationError, load_working_image, probe_image, save_png_atomic
from tests.fixtures.images import write_image, write_paletted_png


@pytest.fixture
def rgb_fixture(tmp_path: Path) -> Path:
    return write_image(tmp_path / "source.png", image_format="PNG", size=(16, 8))


@pytest.mark.parametrize(
    ("image_format", "suffix"),
    [
        ("PNG", ".png"),
        ("JPEG", ".jpg"),
        ("WEBP", ".webp"),
        ("BMP", ".bmp"),
        ("TIFF", ".tiff"),
    ],
)
def test_probe_accepts_supported_formats_after_pillow_decoding(
    tmp_path: Path, image_format: str, suffix: str
) -> None:
    path = write_image(tmp_path / f"fixture{suffix}", image_format=image_format)

    info = probe_image(path)

    assert info.format == image_format
    assert (info.width, info.height) == (12, 8)
    assert info.mode == "RGB"


def test_probe_uses_decoded_format_instead_of_filename_extension(tmp_path: Path) -> None:
    path = write_image(tmp_path / "not-an-extension.data", image_format="PNG")

    assert probe_image(path).format == "PNG"


def test_probe_rejects_malformed_and_unsupported_content_with_safe_typed_error(tmp_path: Path) -> None:
    malformed = tmp_path / "damaged.png"
    malformed.write_bytes(b"not an image")
    svg = tmp_path / "vector.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")

    for path in (malformed, svg):
        with pytest.raises(ImageValidationError, match="图像"):
            probe_image(path)


def test_probe_turns_decompression_bomb_warning_into_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_image(tmp_path / "small.png", image_format="PNG", size=(2, 2))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)

    with pytest.raises(ImageValidationError, match="图像"):
        probe_image(path)


def test_probe_rejects_oversized_decoded_dimensions_before_pixel_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_image(tmp_path / "oversized-header.png", image_format="PNG", size=(1, 1))
    payload = bytearray(path.read_bytes())
    payload[16:24] = struct.pack(">II", 4_097, 4_096)
    payload[29:33] = struct.pack(">I", zlib.crc32(payload[12:29]))
    path.write_bytes(payload)

    def reject_pixel_load(self: PngImagePlugin.PngImageFile) -> None:
        raise AssertionError("pixel allocation was attempted")

    monkeypatch.setattr(PngImagePlugin.PngImageFile, "load", reject_pixel_load)

    with pytest.raises(ImageValidationError, match="安全上限"):
        probe_image(path)


def test_working_copy_respects_max_edge_and_preserves_source(tmp_path: Path, rgb_fixture: Path) -> None:
    before = rgb_fixture.read_bytes()

    image = load_working_image(rgb_fixture, max_edge=8)

    assert image.size == (8, 4)
    assert rgb_fixture.read_bytes() == before


def test_working_copy_never_enlarges_and_preserves_alpha(tmp_path: Path) -> None:
    path = write_image(tmp_path / "transparent.png", image_format="PNG", mode="RGBA", size=(4, 3))

    image = load_working_image(path, max_edge=32)

    assert image.size == (4, 3)
    assert image.mode == "RGBA"
    assert image.getpixel((1, 1))[3] == 34


def test_downscaled_opaque_paletted_png_uses_rgb_lanczos_and_preserves_source(tmp_path: Path) -> None:
    path = write_paletted_png(tmp_path / "opaque-palette.png", transparent=False)
    before = path.read_bytes()
    with Image.open(path) as source:
        nearest = source.convert("RGB").resize((4, 2), Image.Resampling.NEAREST)

    image = load_working_image(path, max_edge=4)

    assert image.mode == "RGB"
    assert image.size == (4, 2)
    assert image.tobytes() != nearest.tobytes()
    assert path.read_bytes() == before


def test_downscaled_transparent_paletted_png_uses_rgba_lanczos_and_preserves_alpha(
    tmp_path: Path,
) -> None:
    path = write_paletted_png(tmp_path / "transparent-palette.png", transparent=True)
    before = path.read_bytes()
    with Image.open(path) as source:
        nearest = source.convert("RGBA").resize((4, 2), Image.Resampling.NEAREST)

    image = load_working_image(path, max_edge=4)

    assert image.mode == "RGBA"
    assert image.size == (4, 2)
    assert image.getchannel("A").getextrema() == (0, 255)
    assert image.tobytes() != nearest.tobytes()
    assert path.read_bytes() == before


def test_unresized_paletted_png_keeps_its_decoded_mode(tmp_path: Path) -> None:
    path = write_paletted_png(tmp_path / "original-palette.png", transparent=True)

    image = load_working_image(path, max_edge=32)

    assert image.mode == "P"
    assert image.size == (16, 8)


def test_working_copy_applies_exif_orientation(tmp_path: Path) -> None:
    source = Image.new("RGB", (3, 5), color=(12, 34, 56))
    exif = Image.Exif()
    exif[274] = 6
    path = tmp_path / "rotated.jpg"
    source.save(path, exif=exif)

    image = load_working_image(path)

    assert image.size == (5, 3)


def test_working_copy_rejects_invalid_max_edge(rgb_fixture: Path) -> None:
    with pytest.raises(ImageValidationError, match="边长"):
        load_working_image(rgb_fixture, max_edge=0)


def test_working_copy_turns_decompression_bomb_warning_into_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_image(tmp_path / "small.png", image_format="PNG", size=(2, 2))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)

    with pytest.raises(ImageValidationError, match="图像"):
        load_working_image(path)


def test_atomic_png_save_replaces_destination_without_leaving_a_temp_file(tmp_path: Path) -> None:
    destination = tmp_path / "preview.png"
    image = Image.new("RGBA", (3, 2), color=(10, 20, 30, 40))

    save_png_atomic(image, destination)

    with Image.open(destination) as saved:
        assert saved.mode == "RGBA"
        assert saved.getpixel((0, 0)) == (10, 20, 30, 40)
    assert not list(tmp_path.glob(".preview.png.*.tmp"))


def test_atomic_png_save_keeps_existing_destination_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "preview.png"
    destination.write_bytes(b"previous destination")

    def reject_replace(source: object, target: object) -> None:
        raise PermissionError("access denied")

    monkeypatch.setattr(images_module.os, "replace", reject_replace)

    with pytest.raises(ImageValidationError, match="保存"):
        save_png_atomic(Image.new("RGB", (2, 2)), destination)

    assert destination.read_bytes() == b"previous destination"
    assert not list(tmp_path.glob(".preview.png.*.tmp"))
