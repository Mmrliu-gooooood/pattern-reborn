# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np

from pattern_reborn.capabilities import detect_capabilities
from pattern_reborn.domain import ProfileId
from pattern_reborn.segmentation import OpenCvSegmenter, SegmentHints


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "pattern_reborn"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_optional_ai.ps1"
CHECKSUM_RECORD = REPO_ROOT / "scripts" / "mobile_sam_checksum.json"

_FORBIDDEN_TOP_LEVEL = frozenset({"torch", "mobile_sam", "torchvision", "timm"})


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _top_level_imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_missing_mobile_sam_reports_disabled_and_keeps_opencv(monkeypatch) -> None:
    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", lambda name: None)
    status = detect_capabilities()
    assert status.mobile_sam.available is False
    assert status.opencv.available is True


def test_missing_mobile_sam_reason_is_chinese_and_opencv_path_still_segments(
    monkeypatch,
) -> None:
    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", lambda name: None)
    status = detect_capabilities()
    assert _has_cjk(status.mobile_sam.reason_zh)
    assert "MobileSAM" in status.mobile_sam.reason_zh

    image = np.full((32, 32, 3), 255, dtype=np.uint8)
    image[8:24, 8:24] = 20
    result = OpenCvSegmenter().segment(image, ProfileId.SILHOUETTE, SegmentHints())
    assert result.mask.shape == image.shape[:2]
    assert result.mask[16, 16] == 255


def test_canvas_and_mobile_sam_are_detected_independently_via_find_spec(monkeypatch) -> None:
    def fake_find_spec(name: str):
        return object() if name == "streamlit_drawable_konva" else None

    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", fake_find_spec)
    status = detect_capabilities()
    assert status.canvas.available is True
    assert status.mobile_sam.available is False
    assert status.opencv.available is True


def test_disable_optional_env_forces_mobile_sam_and_canvas_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PATTERN_REBORN_DISABLE_OPTIONAL", "1")
    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", lambda name: object())
    monkeypatch.setattr(
        "pattern_reborn.capabilities.find_vtracer", lambda: "/usr/bin/vtracer"
    )
    status = detect_capabilities()
    assert status.mobile_sam.available is False
    assert status.canvas.available is False
    assert _has_cjk(status.mobile_sam.reason_zh)
    assert _has_cjk(status.canvas.reason_zh)
    assert status.vtracer.available is True
    assert status.opencv.available is True


def test_vtracer_status_is_independent_of_find_spec(monkeypatch) -> None:
    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", lambda name: object())
    monkeypatch.setattr("pattern_reborn.capabilities.find_vtracer", lambda: None)
    status = detect_capabilities()
    assert status.vtracer.available is False
    assert status.mobile_sam.available is True
    assert status.opencv.available is True
    assert _has_cjk(status.vtracer.reason_zh)


def test_api_credentials_are_booleans_and_never_include_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("SEEDREAM_API_KEY", "secret-value-never-leak")
    monkeypatch.setenv("QWEN_API_KEY", "   ")
    status = detect_capabilities()
    assert status.api_credentials.seedream is True
    assert status.api_credentials.qwen is False
    dumped = repr(status) + str(asdict(status))
    assert "secret-value-never-leak" not in dumped
    assert isinstance(status.api_credentials.seedream, bool)
    assert isinstance(status.api_credentials.qwen, bool)


def test_offline_status_is_independent_of_optional_packages(monkeypatch) -> None:
    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", lambda name: None)
    monkeypatch.setattr("pattern_reborn.capabilities.probe_online", lambda: False)
    status = detect_capabilities()
    assert status.offline is True
    assert status.opencv.available is True

    monkeypatch.setattr("pattern_reborn.capabilities.probe_online", lambda: True)
    status = detect_capabilities()
    assert status.offline is False


def test_detect_capabilities_does_not_import_torch_or_mobile_sam(monkeypatch) -> None:
    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", lambda name: object())
    sys.modules.pop("mobile_sam", None)
    detect_capabilities()
    assert "mobile_sam" not in sys.modules
    assert "torch" not in sys.modules


def test_startup_modules_have_no_top_level_optional_model_imports() -> None:
    for path in (
        REPO_ROOT / "app.py",
        SRC_ROOT / "segmentation.py",
        SRC_ROOT / "capabilities.py",
    ):
        imported = _top_level_imported_modules(path)
        assert imported.isdisjoint(_FORBIDDEN_TOP_LEVEL), path.name


def test_checkpoint_metadata_records_expected_sha256() -> None:
    import json

    record = json.loads(CHECKSUM_RECORD.read_text(encoding="utf-8"))
    sha256 = record["sha256"]
    assert record["filename"] == "mobile_sam.pt"
    assert len(sha256) == 64
    assert all(char in "0123456789abcdef" for char in sha256)
    assert "models/mobile_sam" in record["destination"].replace("\\", "/")


def test_optional_ai_install_script_uses_venv_local_caches_and_checksum() -> None:
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()
    assert ".venv" in text
    assert "Scripts\\python.exe" in text or "Scripts/python.exe" in text
    for name in ("PIP_CACHE_DIR", "HF_HOME", "TORCH_HOME", "XDG_CACHE_HOME", "TEMP", "TMP"):
        assert name in text
    assert "mobile_sam" in lowered
    assert "sha256" in lowered
    assert "mobile_sam_checksum.json" in lowered
    assert "torch==" in lowered
    assert "download.pytorch.org/whl/cpu" in lowered
    assert "github.com/chaoningzhang/mobilesam" in lowered
    assert "[environment]::setenvironmentvariable" not in lowered
    assert "cuda toolkit" not in lowered
    assert "cudatoolkit" not in lowered
    assert "$env:path =" not in lowered
    assert "[environment]::setenvironmentvariable" not in lowered
