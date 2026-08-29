"""Safe Pillow image import and atomic PNG output helpers."""

from dataclasses import dataclass
import os
from pathlib import Path
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


class ImageValidationError(ValueError):
    """图像文件不符合可安全处理的输入约束。"""


@dataclass(frozen=True, slots=True)
class ImageInfo:
    format: str
    width: int
    height: int
    mode: str


_SUPPORTED_FORMATS = frozenset({"PNG", "JPEG", "WEBP", "BMP", "TIFF"})


def probe_image(path: Path) -> ImageInfo:
    """Decode and validate an image, returning only its safe metadata."""
    image, image_format = _decode_image(path)
    return ImageInfo(
        format=image_format,
        width=image.width,
        height=image.height,
        mode=image.mode,
    )


def load_working_image(path: Path, max_edge: int = 2048) -> Image.Image:
    """Return a detached, orientation-corrected working image without editing the source."""
    if isinstance(max_edge, bool) or not isinstance(max_edge, int) or max_edge <= 0:
        raise ImageValidationError("图像最大边长必须为正整数。")

    image, _ = _decode_image(path)
    if max(image.size) <= max_edge:
        return image.copy()

    scale = max_edge / max(image.size)
    size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    return image.resize(size, Image.Resampling.LANCZOS).copy()


def save_png_atomic(image: Image.Image, destination: Path) -> None:
    """Write a PNG through a sibling temporary file and atomically replace the destination."""
    if not isinstance(image, Image.Image):
        raise ImageValidationError("待保存的图像无效。")

    target = Path(destination)
    temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as handle:
            image.save(handle, format="PNG")
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temporary, target)
    except (OSError, ValueError) as error:
        _discard_temporary_file(temporary)
        raise ImageValidationError("图像保存失败，原目标文件未被替换。") from error


def _decode_image(path: Path) -> tuple[Image.Image, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(Path(path)) as source:
                image_format = source.format
                if image_format not in _SUPPORTED_FORMATS:
                    raise ImageValidationError("图像格式不受支持。")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.load()
                return oriented.copy(), image_format
    except ImageValidationError:
        raise
    except (
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise ImageValidationError("图像无法安全解码或文件已损坏。") from error


def _discard_temporary_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
