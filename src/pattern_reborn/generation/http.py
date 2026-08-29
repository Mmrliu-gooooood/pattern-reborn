# -*- coding: utf-8 -*-
"""Shared HTTP mapping, data-URL encoding, and immediate image capture."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import SecretStr

from pattern_reborn.generation.base import FailureKind, GenerationFailure
from pattern_reborn.images import ImageValidationError, probe_image, save_png_atomic

USER_MESSAGE_ZH: dict[FailureKind, str] = {
    FailureKind.AUTH: "身份验证失败，请检查访问凭证。",
    FailureKind.QUOTA: "生成额度已用尽或请求过于频繁。",
    FailureKind.MODERATION: "生成内容未通过安全审核，请调整提示词后重试。",
    FailureKind.TIMEOUT: "生成请求超时，请稍后重试。",
    FailureKind.MALFORMED: "生成请求参数无效，请调整后重试。",
    FailureKind.MISSING_CREDENTIAL: "未配置平台访问凭证。",
}

_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}

_MODERATION_MARKERS = (
    "sensitive",
    "moderation",
    "inspection",
    "datainspection",
    "content_filter",
    "inappropriate",
    "审核",
    "违规",
)

_AUTH_MARKERS = (
    "invalidapikey",
    "authentication",
    "unauthorized",
    "forbidden",
)

_QUOTA_MARKERS = (
    "throttl",
    "ratequota",
    "ratelimit",
    "quota",
)


def mapped_failure(kind: FailureKind, provider_code: str | None = None) -> GenerationFailure:
    return GenerationFailure(kind, USER_MESSAGE_ZH[kind], provider_code)


def raise_mapped(kind: FailureKind, provider_code: str | None = None) -> NoReturn:
    raise mapped_failure(kind, provider_code)


def encode_data_url(path: Path) -> str:
    try:
        info = probe_image(path)
    except ImageValidationError:
        raise_mapped(FailureKind.MALFORMED)
    mime = _MIME_BY_FORMAT.get(info.format)
    if mime is None:
        raise_mapped(FailureKind.MALFORMED)
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def authorization_headers(credential: SecretStr) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credential.get_secret_value()}",
        "Content-Type": "application/json",
    }


def classify_http_error(status_code: int, body_text: str) -> FailureKind:
    lowered = body_text.lower()
    if status_code in (401, 403):
        return FailureKind.AUTH
    if status_code == 429:
        return FailureKind.QUOTA
    if status_code in (408, 504):
        return FailureKind.TIMEOUT
    if status_code == 451 or any(marker in lowered for marker in _MODERATION_MARKERS):
        return FailureKind.MODERATION
    if any(marker in lowered for marker in _AUTH_MARKERS):
        return FailureKind.AUTH
    if any(marker in lowered for marker in _QUOTA_MARKERS):
        return FailureKind.QUOTA
    return FailureKind.MALFORMED


def post_json(
    client: httpx.Client,
    url: str,
    payload: dict[str, object],
    credential: SecretStr,
) -> httpx.Response:
    try:
        response = client.post(
            url,
            json=payload,
            headers=authorization_headers(credential),
            timeout=60.0,
        )
    except httpx.TimeoutException:
        raise_mapped(FailureKind.TIMEOUT)
    except httpx.RequestError:
        raise_mapped(FailureKind.MALFORMED)
    if response.status_code >= 400:
        raise_mapped(
            classify_http_error(response.status_code, response.text),
            str(response.status_code),
        )
    return response


def download_bytes(client: httpx.Client, url: str) -> bytes:
    try:
        response = client.get(url, timeout=60.0)
    except httpx.TimeoutException:
        raise_mapped(FailureKind.TIMEOUT)
    except httpx.RequestError:
        raise_mapped(FailureKind.MALFORMED)
    if response.status_code >= 400:
        raise_mapped(
            classify_http_error(response.status_code, response.text),
            str(response.status_code),
        )
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type and not content_type.startswith("image/") and content_type != "application/octet-stream":
        raise_mapped(FailureKind.MALFORMED)
    return response.content


def decode_image_value(value: str, client: httpx.Client) -> bytes:
    if value.startswith(("http://", "https://")):
        return download_bytes(client, value)
    encoded = value
    if value.startswith("data:") and "," in value:
        encoded = value.split(",", 1)[1]
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise_mapped(FailureKind.MALFORMED)


def persist_generated_png(data: bytes, output_dir: Path, stem: str) -> Path:
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            copy = image.copy()
    except (UnidentifiedImageError, OSError, ValueError):
        raise_mapped(FailureKind.MALFORMED)
    destination = output_dir / f"{stem}-{uuid4().hex}.png"
    try:
        save_png_atomic(copy, destination)
    except ImageValidationError:
        raise_mapped(FailureKind.MALFORMED)
    return destination

