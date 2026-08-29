# -*- coding: utf-8 -*-
"""Independent optional-capability detection. Never imports Torch or MobileSAM."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
import os
import socket

from pattern_reborn.vectorize import find_vtracer

_MOBILE_SAM_UNAVAILABLE_ZH = "未检测到 MobileSAM，已禁用引导式 AI 分割。OpenCV 路径仍可用。"
_VTRACER_UNAVAILABLE_ZH = "未检测到 VTracer，已禁用 SVG 导出。PNG 工作流不受影响。"
_CANVAS_UNAVAILABLE_ZH = "未检测到可绘制画布组件，已回退为框选与提示点输入。"
_OPENCV_UNAVAILABLE_ZH = "未检测到 OpenCV，本地提取不可用。"


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    available: bool
    reason_zh: str = ""


@dataclass(frozen=True, slots=True)
class ApiCredentialStatus:
    seedream: bool
    qwen: bool


@dataclass(frozen=True, slots=True)
class Capabilities:
    opencv: CapabilityStatus
    vtracer: CapabilityStatus
    mobile_sam: CapabilityStatus
    canvas: CapabilityStatus
    api_credentials: ApiCredentialStatus
    offline: bool


def probe_online() -> bool:
    """Best-effort network probe. Failures are treated as offline, never raised."""
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=0.25):
            return True
    except OSError:
        return False


def _credential_present(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and bool(str(value).strip())


def _optional_disabled() -> bool:
    return os.environ.get("PATTERN_REBORN_DISABLE_OPTIONAL", "").strip() == "1"


def _opencv_status() -> CapabilityStatus:
    try:
        import cv2  # noqa: F401
    except Exception:
        return CapabilityStatus(available=False, reason_zh=_OPENCV_UNAVAILABLE_ZH)
    return CapabilityStatus(available=True)


def detect_capabilities() -> Capabilities:
    optional_disabled = _optional_disabled()
    vtracer_present = find_vtracer() is not None
    mobile_sam_present = (
        not optional_disabled and find_spec("mobile_sam") is not None
    )
    canvas_present = (
        not optional_disabled and find_spec("streamlit_drawable_konva") is not None
    )
    return Capabilities(
        opencv=_opencv_status(),
        vtracer=CapabilityStatus(
            available=vtracer_present,
            reason_zh="" if vtracer_present else _VTRACER_UNAVAILABLE_ZH,
        ),
        mobile_sam=CapabilityStatus(
            available=mobile_sam_present,
            reason_zh="" if mobile_sam_present else _MOBILE_SAM_UNAVAILABLE_ZH,
        ),
        canvas=CapabilityStatus(
            available=canvas_present,
            reason_zh="" if canvas_present else _CANVAS_UNAVAILABLE_ZH,
        ),
        api_credentials=ApiCredentialStatus(
            seedream=_credential_present("SEEDREAM_API_KEY"),
            qwen=_credential_present("QWEN_API_KEY"),
        ),
        offline=not probe_online(),
    )
