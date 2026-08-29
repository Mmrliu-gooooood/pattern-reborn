"""Optional VTracer adapter. Missing or invalid SVG never blocks PNG workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


class VectorizeError(ValueError):
    """矢量转换失败或输出无效。"""


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    available: bool
    reason_zh: str = ""


@dataclass(frozen=True, slots=True)
class VectorSettings:
    colormode: str = "color"
    hierarchical: str = "stacked"
    mode: str = "spline"
    filter_speckle: int = 4
    color_precision: int = 6
    layer_difference: int = 16
    corner_threshold: int = 60
    length_threshold: float = 4.0
    max_iterations: int = 10
    splice_threshold: int = 45
    path_precision: int = 3


@dataclass(frozen=True, slots=True)
class VectorResult:
    available: bool
    reason_zh: str = ""
    destination: Path | None = None


_UNAVAILABLE_ZH = "未检测到 VTracer，已禁用 SVG 导出。PNG 工作流不受影响。"
_INVALID_SVG_ZH = "VTracer 输出无效，已保留 PNG 结果。"
_CONVERT_FAILED_ZH = "VTracer 转换失败，已保留 PNG 结果。"


def find_vtracer() -> Any | None:
    """Lazily discover VTracer. Import failures are catchable and never crash PNG paths."""
    try:
        import vtracer
    except Exception:
        return None
    convert = getattr(vtracer, "convert_image_to_svg_py", None)
    if not callable(convert):
        return None
    return vtracer


class Vectorizer:
    def capability(self) -> CapabilityStatus:
        if find_vtracer() is None:
            return CapabilityStatus(available=False, reason_zh=_UNAVAILABLE_ZH)
        return CapabilityStatus(available=True)

    def vectorize(
        self,
        source_png: Path,
        destination_svg: Path,
        settings: VectorSettings = VectorSettings(),
    ) -> VectorResult:
        module = find_vtracer()
        if module is None:
            return VectorResult(available=False, reason_zh=_UNAVAILABLE_ZH)

        destination = Path(destination_svg)
        temporary = destination.parent / f".{destination.name}.{uuid4().hex}.tmp"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            module.convert_image_to_svg_py(str(Path(source_png)), str(temporary), **asdict(settings))
            if not _is_svg(temporary):
                _discard_temporary_file(temporary)
                return VectorResult(available=False, reason_zh=_INVALID_SVG_ZH)
            os.replace(temporary, destination)
            return VectorResult(available=True, destination=destination)
        except Exception:
            _discard_temporary_file(temporary)
            return VectorResult(available=False, reason_zh=_CONVERT_FAILED_ZH)


def _is_svg(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
        return "<svg" in path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False


def _discard_temporary_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
