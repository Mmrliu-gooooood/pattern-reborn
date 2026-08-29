# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT = SCRIPTS_DIR / "validate_demo_assets.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_demo_assets import COMPETITION_CASE_IDS, validate_demo_root


@pytest.fixture
def demo_png(tmp_path: Path) -> Path:
    path = tmp_path / "_assets" / "demo.png"
    path.parent.mkdir()
    Image.new("RGB", (8, 8), (180, 40, 40)).save(path, format="PNG")
    return path


def write_demo_case(
    root: Path,
    *,
    source: Path,
    license: str = "CC BY 4.0",
    source_url: str | None = "https://institution.example/object/1",
    case_id: str = "sample-case",
    title: str = "演示纹样",
    category: str = "paper_cutting",
    profile: str = "silhouette",
    creator_institution: str = "Example Institution",
    bibliography: str | None = None,
    retrieval_date: str = "2026-08-29",
    provenance: str = "traditional_reference",
    processing_defaults: dict[str, object] | None = None,
    expected_result: str = "提取清晰轮廓。",
    ai_involvement: dict[str, object] | None = None,
    sha256: str | None = None,
    source_filename: str | None = None,
    copy_source: bool = True,
    omit: frozenset[str] | None = None,
    manifest_source: str | None = None,
) -> Path:
    case_dir = root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    dest_name = source_filename or f"source{source.suffix.lower()}"
    dest = case_dir / dest_name
    if copy_source:
        dest.write_bytes(source.read_bytes())
    digest = sha256
    if digest is None and dest.is_file():
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    metadata: dict[str, object] = {
        "title": title,
        "category": category,
        "profile": profile,
        "source_filename": dest_name,
        "sha256": digest or "",
        "creator_institution": creator_institution,
        "source_url": source_url,
        "bibliography": bibliography,
        "license": license,
        "retrieval_date": retrieval_date,
        "provenance": provenance,
        "processing_defaults": processing_defaults or {"threshold_mode": "otsu"},
        "expected_result": expected_result,
        "ai_involvement": ai_involvement
        or {
            "source_is_ai_generated": False,
            "note": "源图非人工智能生成。",
        },
    }
    for key in omit or ():
        metadata.pop(key, None)
    (case_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    payload: dict[str, object] = {"cases": []}
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = list(payload.get("cases") or [])
    cases = [item for item in cases if not (isinstance(item, dict) and item.get("id") == case_id)]
    cases.append(
        {
            "id": case_id,
            "title_zh": title,
            "source": manifest_source or f"{case_id}/{dest_name}",
        }
    )
    payload["cases"] = cases
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return case_dir


def test_validator_accepts_complete_rights_record(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(
        tmp_path,
        source=demo_png,
        license="CC BY 4.0",
        source_url="https://institution.example/object/1",
    )
    assert validate_demo_root(tmp_path).errors == []


def test_validator_rejects_unclear_search_engine_image(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(
        tmp_path,
        source=demo_png,
        license="unknown",
        source_url="https://images.example/search?q=lotus",
    )
    result = validate_demo_root(tmp_path)
    assert any("授权" in error for error in result.errors)


def test_validator_accepts_institution_collection_object_url(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(
        tmp_path,
        source=demo_png,
        license="CC0 / The Met Open Access",
        source_url="https://www.metmuseum.org/art/collection/search/39735",
        creator_institution="The Metropolitan Museum of Art, 1987.277",
    )
    assert validate_demo_root(tmp_path).errors == []


def test_validator_rejects_missing_source_file(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(tmp_path, source=demo_png, copy_source=False)
    result = validate_demo_root(tmp_path)
    assert any("缺失" in error or "不存在" in error for error in result.errors)


def test_validator_rejects_sha256_mismatch(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(tmp_path, source=demo_png, sha256="0" * 64)
    result = validate_demo_root(tmp_path)
    assert any("SHA-256" in error or "sha256" in error.lower() for error in result.errors)


def test_validator_rejects_missing_author_or_institution(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(tmp_path, source=demo_png, creator_institution="")
    result = validate_demo_root(tmp_path)
    assert any("作者" in error or "机构" in error for error in result.errors)


def test_validator_rejects_invalid_provenance_classification(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(tmp_path, source=demo_png, provenance="museum_scan")
    result = validate_demo_root(tmp_path)
    assert any("来源分类" in error for error in result.errors)


def test_validator_rejects_ai_material_labeled_as_historical_artifact(
    tmp_path: Path, demo_png: Path
) -> None:
    write_demo_case(
        tmp_path,
        source=demo_png,
        provenance="traditional_reference",
        expected_result="历史文物原件。",
        ai_involvement={
            "source_is_ai_generated": True,
            "note": "人工智能生成的莲纹。",
        },
    )
    result = validate_demo_root(tmp_path)
    assert any("人工智能" in error or "文物" in error or "历史" in error for error in result.errors)


def test_validator_rejects_manifest_file_mismatch(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(
        tmp_path,
        source=demo_png,
        manifest_source="missing-folder/source.png",
    )
    result = validate_demo_root(tmp_path)
    assert any("清单" in error or "不一致" in error for error in result.errors)


def test_empty_development_manifest_passes_without_competition_ready(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"cases": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert validate_demo_root(tmp_path).errors == []


def test_competition_ready_requires_exactly_six_case_ids(tmp_path: Path, demo_png: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"cases": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    empty = validate_demo_root(tmp_path, competition_ready=True)
    joined = "\n".join(empty.errors)
    assert empty.errors
    for case_id in COMPETITION_CASE_IDS:
        assert case_id in joined

    for case_id in COMPETITION_CASE_IDS:
        write_demo_case(tmp_path, source=demo_png, case_id=case_id)
    assert validate_demo_root(tmp_path, competition_ready=True).errors == []

    write_demo_case(tmp_path, source=demo_png, case_id="extra-case")
    extra = validate_demo_root(tmp_path, competition_ready=True)
    assert any("extra-case" in error or "恰好" in error for error in extra.errors)


def test_cli_competition_ready_flag_rejects_empty_manifest(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"cases": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path), "--competition-ready"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert completed.returncode != 0
    output = f"{completed.stderr or ''}{completed.stdout or ''}"
    assert "lotus-paper-cut" in output


def test_validator_does_not_autofill_missing_rights(tmp_path: Path, demo_png: Path) -> None:
    write_demo_case(tmp_path, source=demo_png, creator_institution="", omit=frozenset({"license"}))
    metadata_path = tmp_path / "sample-case" / "metadata.json"
    before = metadata_path.read_text(encoding="utf-8")
    result = validate_demo_root(tmp_path)
    assert result.errors
    assert metadata_path.read_text(encoding="utf-8") == before
    assert "license" not in json.loads(before)
