# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path

import httpx
from PIL import Image
from pydantic import SecretStr
import pytest

from pattern_reborn.generation.base import (
    FailureKind,
    GenerationFailure,
    GenerationRequest,
    ProviderId,
)
from tests.fixtures.images import write_image
from tests.test_generation_base import make_generation_request, reference_png  # noqa: F401


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color=(18, 52, 86)).save(buffer, format="PNG")
    return buffer.getvalue()


PNG_BYTES = _png_bytes()
PNG_BASE64 = base64.b64encode(PNG_BYTES).decode("ascii")
SEEDREAM_URL = "https://ark.example/api/v3/images/generations"
RESULT_URL = "https://temporary.example/result.png"


@pytest.fixture
def generation_request(reference_png: Path) -> GenerationRequest:
    return make_generation_request(reference_png)


def make_seedream(tmp_path: Path):
    from pattern_reborn.generation.seedream import SeedreamAdapter

    return SeedreamAdapter(
        client=httpx.Client(),
        base_url="https://ark.example",
        output_dir=tmp_path / "generated",
    )


def test_seedream_decodes_base64_result_without_exposing_key(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(
        json={"model": "seedream", "data": [{"b64_json": PNG_BASE64}], "usage": {}}
    )
    result = make_seedream(tmp_path).generate(
        generation_request, SecretStr("secret-value")
    )
    assert result.local_files[0].read_bytes().startswith(b"\x89PNG")
    assert "secret-value" not in result.model_dump_json()


def test_seedream_downloads_url_result_before_success(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(
        json={
            "model": "seedream",
            "created": 1750000000,
            "data": [{"url": RESULT_URL, "size": "1024x1024"}],
            "usage": {"generated_images": 1},
        }
    )
    download = respx_mock.get(RESULT_URL).respond(
        content=PNG_BYTES, headers={"Content-Type": "image/png"}
    )
    result = make_seedream(tmp_path).generate(
        generation_request, SecretStr("secret-value")
    )
    assert download.called
    assert result.local_files[0].exists()
    assert result.prompt == generation_request.prompt
    assert result.provider is ProviderId.SEEDREAM


def test_seedream_sends_mime_data_url_and_documented_fields(
    respx_mock, generation_request, tmp_path
) -> None:
    route = respx_mock.post(SEEDREAM_URL).respond(
        json={"model": "seedream", "data": [{"b64_json": PNG_BASE64}], "usage": {}}
    )
    make_seedream(tmp_path).generate(generation_request, SecretStr("secret-value"))
    sent = json.loads(route.calls.last.request.content.decode("utf-8"))
    assert sent["model"] == generation_request.model
    assert sent["prompt"] == generation_request.prompt
    assert sent["size"] == generation_request.size
    assert sent["response_format"] in {"url", "b64_json"}
    assert sent["image"].startswith("data:image/png;base64,")
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret-value"


def test_seedream_encodes_jpeg_reference_as_jpeg_data_url(
    respx_mock, tmp_path, reference_png
) -> None:
    jpeg_path = write_image(tmp_path / "reference.jpg", image_format="JPEG")
    request = make_generation_request(jpeg_path)
    route = respx_mock.post(SEEDREAM_URL).respond(
        json={"model": "seedream", "data": [{"b64_json": PNG_BASE64}], "usage": {}}
    )
    make_seedream(tmp_path).generate(request, SecretStr("secret-value"))
    sent = json.loads(route.calls.last.request.content.decode("utf-8"))
    assert sent["image"].startswith("data:image/jpeg;base64,")


def test_seedream_maps_auth_error(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(
        401,
        json={"error": {"code": "AuthenticationError", "message": "invalid api key"}},
    )
    with pytest.raises(GenerationFailure) as captured:
        make_seedream(tmp_path).generate(generation_request, SecretStr("secret-value"))
    failure = captured.value
    assert failure.kind is FailureKind.AUTH
    assert failure.user_message_zh == "身份验证失败，请检查访问凭证。"
    assert failure.provider_code == "401"
    assert "secret-value" not in str(failure)


def test_seedream_maps_quota_429(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(
        429, json={"error": {"code": "RateLimitExceeded", "message": "too many requests"}}
    )
    with pytest.raises(GenerationFailure) as captured:
        make_seedream(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.QUOTA
    assert captured.value.user_message_zh == "生成额度已用尽或请求过于频繁。"
    assert captured.value.provider_code == "429"


def test_seedream_maps_moderation_error(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(
        400,
        json={
            "error": {
                "code": "OutputImageSensitiveContentDetected",
                "message": "sensitive content",
            }
        },
    )
    with pytest.raises(GenerationFailure) as captured:
        make_seedream(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.MODERATION
    assert captured.value.user_message_zh == "生成内容未通过安全审核，请调整提示词后重试。"
    assert captured.value.provider_code == "400"


def test_seedream_maps_timeout(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(GenerationFailure) as captured:
        make_seedream(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.TIMEOUT
    assert captured.value.user_message_zh == "生成请求超时，请稍后重试。"
    assert captured.value.provider_code is None


def test_seedream_maps_malformed_body(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(json={"model": "seedream", "data": [], "usage": {}})
    with pytest.raises(GenerationFailure) as captured:
        make_seedream(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.MALFORMED
    assert captured.value.user_message_zh == "生成请求参数无效，请调整后重试。"


def test_seedream_rejects_non_image_download(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(
        json={"model": "seedream", "data": [{"url": RESULT_URL}], "usage": {}}
    )
    respx_mock.get(RESULT_URL).respond(
        content=b"<html>not an image</html>", headers={"Content-Type": "text/html"}
    )
    with pytest.raises(GenerationFailure) as captured:
        make_seedream(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.MALFORMED


def test_seedream_writes_atomic_png_under_generated(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(
        json={"model": "seedream", "data": [{"b64_json": PNG_BASE64}], "usage": {}}
    )
    result = make_seedream(tmp_path).generate(
        generation_request, SecretStr("secret-value")
    )
    destination = result.local_files[0]
    assert destination.parent == tmp_path / "generated"
    assert destination.suffix == ".png"
    assert destination.exists()
    assert not list(destination.parent.glob(".*.tmp"))


def test_seedream_preserves_prompt_on_failure(
    respx_mock, generation_request, tmp_path
) -> None:
    original = generation_request.model_dump()
    respx_mock.post(SEEDREAM_URL).respond(401, json={"error": {"code": "Unauthorized"}})
    with pytest.raises(GenerationFailure):
        make_seedream(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert generation_request.model_dump() == original
    assert generation_request.prompt == "保持莲纹骨架，生成书签纹样"
