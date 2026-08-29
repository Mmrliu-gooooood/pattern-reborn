# -*- coding: utf-8 -*-
"""Reject untraceable or incomplete competition demo assets. Never auto-fills rights."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


COMPETITION_CASE_IDS: tuple[str, ...] = (
    "lotus-paper-cut",
    "fish-lotus-blue-calico",
    "peony-embroidery",
    "scrolling-lotus-ceramic",
    "new-year-picture-detail",
    "architectural-cloud",
)

ALLOWED_CATEGORIES = frozenset(
    {
        "paper_cutting",
        "embroidery_brocade",
        "dyeing_textile",
        "ceramic_ornament",
        "lacquer_ornament",
        "folk_painting",
        "architectural_ornament",
        "metal_jewelry",
        "folk_crafts",
    }
)
ALLOWED_PROFILES = frozenset({"silhouette", "flat_color", "textile", "artifact_photo"})
ALLOWED_PROVENANCE = frozenset(
    {
        "verified_ich_source",
        "traditional_reference",
        "user_supplied_unverified",
    }
)
UNCLEAR_LICENSES = frozenset(
    {
        "unknown",
        "unclear",
        "n/a",
        "na",
        "none",
        "null",
        "未注明",
        "不明",
        "未知",
    }
)
HISTORICAL_PROVENANCE = frozenset({"verified_ich_source", "traditional_reference"})
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_REQUIRED_METADATA = (
    "title",
    "category",
    "profile",
    "source_filename",
    "sha256",
    "creator_institution",
    "license",
    "retrieval_date",
    "provenance",
    "processing_defaults",
    "expected_result",
    "ai_involvement",
)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: list[str]


def validate_demo_root(root: Path, *, competition_ready: bool = False) -> ValidationResult:
    errors: list[str] = []
    try:
        demo_root = Path(root).resolve()
    except OSError:
        return ValidationResult([f"无法访问演示目录：{root}"])
    if not demo_root.is_dir():
        return ValidationResult([f"演示目录不存在：{demo_root}"])

    manifest_path = demo_root / "manifest.json"
    if not manifest_path.is_file():
        return ValidationResult(["缺少 manifest.json。"])

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ValidationResult(["manifest.json 无法以 UTF-8 JSON 读取。"])
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        return ValidationResult(["manifest.json 必须包含 cases 数组。"])

    case_ids: list[str] = []
    for index, item in enumerate(payload["cases"]):
        case_ids.extend(_validate_manifest_case(demo_root, item, index, errors))

    if len(case_ids) != len(set(case_ids)):
        errors.append("清单中的案例标识不能重复。")

    if competition_ready:
        actual = set(case_ids)
        expected = set(COMPETITION_CASE_IDS)
        missing = [case_id for case_id in COMPETITION_CASE_IDS if case_id not in actual]
        extra = sorted(actual - expected)
        if missing or extra:
            parts = ["竞赛就绪需要恰好六个指定案例。"]
            if missing:
                parts.append("缺少：" + "、".join(missing) + "。")
            if extra:
                parts.append("多出：" + "、".join(extra) + "。")
            errors.append("".join(parts))

    return ValidationResult(errors)


def _validate_manifest_case(
    demo_root: Path,
    item: object,
    index: int,
    errors: list[str],
) -> list[str]:
    prefix = f"清单第 {index} 项"
    if not isinstance(item, dict):
        errors.append(f"{prefix} 必须是对象。")
        return []
    case_id = item.get("id")
    title_zh = item.get("title_zh")
    source = item.get("source")
    if not _non_empty_str(case_id) or not _non_empty_str(title_zh) or not _non_empty_str(source):
        errors.append(f"{prefix} 必须包含非空的 id、title_zh、source。")
        return []
    assert isinstance(case_id, str) and isinstance(source, str)

    source_path = _contained_path(demo_root, source)
    if source_path is None:
        errors.append(f"案例 {case_id} 的清单路径越界或不合法：{source}")
        return [case_id]
    if not source_path.is_file():
        errors.append(f"案例 {case_id} 的清单与文件不一致：源文件不存在（{source}）。")
        _validate_metadata_file(demo_root / case_id, case_id, None, errors)
        return [case_id]

    _validate_metadata_file(demo_root / case_id, case_id, source_path, errors)
    return [case_id]


def _validate_metadata_file(
    case_dir: Path,
    case_id: str,
    source_path: Path | None,
    errors: list[str],
) -> None:
    metadata_path = case_dir / "metadata.json"
    if not metadata_path.is_file():
        errors.append(f"案例 {case_id} 缺少 metadata.json。")
        return
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"案例 {case_id} 的 metadata.json 无法读取。")
        return
    if not isinstance(metadata, dict):
        errors.append(f"案例 {case_id} 的 metadata.json 必须是对象。")
        return

    for field in _REQUIRED_METADATA:
        if field not in metadata:
            errors.append(f"案例 {case_id} 缺少必填字段 {field}，校验器不会自动补全权利信息。")

    title = metadata.get("title")
    if field_present(metadata, "title") and not _non_empty_str(title):
        errors.append(f"案例 {case_id} 的 title 不能为空。")

    category = metadata.get("category")
    if field_present(metadata, "category") and category not in ALLOWED_CATEGORIES:
        errors.append(f"案例 {case_id} 的品类无效：{category!r}。")

    profile = metadata.get("profile")
    if field_present(metadata, "profile") and profile not in ALLOWED_PROFILES:
        errors.append(f"案例 {case_id} 的处理模式无效：{profile!r}。")

    creator = metadata.get("creator_institution")
    if field_present(metadata, "creator_institution") and not _non_empty_str(creator):
        errors.append(f"案例 {case_id} 缺少作者或收藏机构，校验器不会自动补全。")

    source_url = metadata.get("source_url")
    bibliography = metadata.get("bibliography")
    has_url = _non_empty_str(source_url)
    has_bib = _non_empty_str(bibliography)
    if not has_url and not has_bib:
        errors.append(f"案例 {case_id} 必须提供来源 URL 或书目。")
    if has_url:
        assert isinstance(source_url, str)
        if not _is_http_url(source_url):
            errors.append(f"案例 {case_id} 的来源 URL 必须是 http(s) 地址。")
        elif _is_search_engine_url(source_url):
            errors.append(f"案例 {case_id} 授权不明：禁止使用搜索引擎结果页图片。")

    license_value = metadata.get("license")
    if field_present(metadata, "license"):
        if not _non_empty_str(license_value):
            errors.append(f"案例 {case_id} 缺少许可信息，校验器不会自动补全授权。")
        elif str(license_value).strip().casefold() in UNCLEAR_LICENSES:
            errors.append(f"案例 {case_id} 授权不明：许可不能为 {license_value!r}。")

    retrieval_date = metadata.get("retrieval_date")
    if field_present(metadata, "retrieval_date") and (
        not _non_empty_str(retrieval_date) or not _DATE.fullmatch(str(retrieval_date))
    ):
        errors.append(f"案例 {case_id} 的检索日期必须为 YYYY-MM-DD。")

    provenance = metadata.get("provenance")
    if field_present(metadata, "provenance") and provenance not in ALLOWED_PROVENANCE:
        errors.append(
            f"案例 {case_id} 的来源分类无效：{provenance!r}。"
            "允许值为 verified_ich_source、traditional_reference、user_supplied_unverified。"
        )

    defaults = metadata.get("processing_defaults")
    if field_present(metadata, "processing_defaults") and not isinstance(defaults, dict):
        errors.append(f"案例 {case_id} 的 processing_defaults 必须是对象。")
    elif isinstance(defaults, dict) and not defaults:
        errors.append(f"案例 {case_id} 的 processing_defaults 不能为空。")

    expected = metadata.get("expected_result")
    if field_present(metadata, "expected_result") and not _non_empty_str(expected):
        errors.append(f"案例 {case_id} 的预期结果不能为空。")

    involvement = metadata.get("ai_involvement")
    if field_present(metadata, "ai_involvement") and not isinstance(involvement, dict):
        errors.append(f"案例 {case_id} 的 ai_involvement 必须是对象。")
    elif isinstance(involvement, dict):
        generated = involvement.get("source_is_ai_generated")
        if not isinstance(generated, bool):
            errors.append(f"案例 {case_id} 必须声明 source_is_ai_generated。")
        elif generated and provenance in HISTORICAL_PROVENANCE:
            errors.append(
                f"案例 {case_id} 将人工智能生成素材标为历史文物或传统原件，来源分类不能是 {provenance}。"
            )

    filename = metadata.get("source_filename")
    if source_path is not None:
        if field_present(metadata, "source_filename") and filename != source_path.name:
            errors.append(
                f"案例 {case_id} 的清单与文件不一致：source_filename={filename!r}，实际文件为 {source_path.name}。"
            )
        declared = metadata.get("sha256")
        actual = _sha256(source_path)
        if field_present(metadata, "sha256"):
            if not _non_empty_str(declared) or not _SHA256.fullmatch(str(declared)):
                errors.append(f"案例 {case_id} 的 SHA-256 格式无效。")
            elif str(declared).casefold() != actual:
                errors.append(
                    f"案例 {case_id} 的 SHA-256 与源文件不一致：记录 {declared}，实际 {actual}。"
                )


def field_present(metadata: dict[str, object], field: str) -> bool:
    return field in metadata


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_search_engine_url(value: str) -> bool:
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "/search" in path:
        return True
    markers = ("google.", "bing.", "baidu.", "yandex.", "images.example")
    return any(marker in host for marker in markers)


def _contained_path(root: Path, relative: str) -> Path | None:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    resolved = (root / candidate).resolve()
    try:
        if not resolved.is_relative_to(root.resolve()):
            return None
    except (OSError, ValueError):
        return None
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="校验可追溯演示素材；不会自动补全权利字段。")
    parser.add_argument("root", type=Path, help="data/demo 目录")
    parser.add_argument(
        "--competition-ready",
        action="store_true",
        help="要求恰好包含六个竞赛案例标识",
    )
    args = parser.parse_args(argv)
    result = validate_demo_root(args.root, competition_ready=args.competition_ready)
    stream = sys.stderr if result.errors else sys.stdout
    if result.errors:
        for error in result.errors:
            print(error, file=stream)
        print(f"校验失败：{len(result.errors)} 项。", file=stream)
        return 1
    print("校验通过。", file=stream)
    return 0


if __name__ == "__main__":
    sys.exit(main())
