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
from tests.test_generation_base import make_generation_request, reference_png  # noqa: F401


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color=(18, 52, 86)).save(buffer, format="PNG")
    return buffer.getvalue()


PNG_BYTES = _png_bytes()
PNG_BASE64 = base64.b64encode(PNG_BYTES).decode("ascii")
QWEN_URL = "https://qwen.example/api/v1/services/aigc/multimodal-generation/generation"
RESULT_URL = "https://temporary.example/result.png"
QWEN_FULL_RESPONSE = {
    "output": {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": [{"image": RESULT_URL}],
                    "role": "assistant",
                },
            }
        ]
    },
    "usage": {"height": 1024, "image_count": 1, "width": 1024},
    "request_id": "d0250a3d-b07f-49e1-bdc8-test",
}


@pytest.fixture
def generation_request(reference_png: Path) -> GenerationRequest:
    return make_generation_request(
        reference_png,
        provider=ProviderId.QWEN,
        model="qwen-image-3.0-pro",
        size="1024x1024",
    )


def make_qwen(tmp_path: Path):
    from pattern_reborn.generation.qwen import QwenAdapter

    return QwenAdapter(
        client=httpx.Client(),
        base_url="https://qwen.example",
        output_dir=tmp_path / "generated",
    )


def test_qwen_downloads_temporary_url_before_success(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(QWEN_URL).respond(json=QWEN_FULL_RESPONSE)
    download = respx_mock.get(RESULT_URL).respond(
        content=PNG_BYTES, headers={"Content-Type": "image/png"}
    )
    result = make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert download.called
    assert result.local_files[0].exists()
    assert "secret-value" not in result.model_dump_json()


def test_qwen_decodes_base64_result_without_exposing_key(
    respx_mock, generation_request, tmp_path
) -> None:
    payload = {
        "output": {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": [
                            {"image": f"data:image/png;base64,{PNG_BASE64}"}
                        ],
                        "role": "assistant",
                    },
                }
            ]
        },
        "usage": {},
        "request_id": "b64-test",
    }
    respx_mock.post(QWEN_URL).respond(json=payload)
    result = make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert result.local_files[0].read_bytes().startswith(b"\x89PNG")
    assert result.provider is ProviderId.QWEN
    assert result.prompt == generation_request.prompt
    assert "secret-value" not in result.model_dump_json()


def test_qwen_sends_image_then_text_and_supported_parameters(
    respx_mock, generation_request, tmp_path
) -> None:
    route = respx_mock.post(QWEN_URL).respond(json=QWEN_FULL_RESPONSE)
    respx_mock.get(RESULT_URL).respond(
        content=PNG_BYTES, headers={"Content-Type": "image/png"}
    )
    make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    sent = json.loads(route.calls.last.request.content.decode("utf-8"))
    content = sent["input"]["messages"][0]["content"]
    assert sent["model"] == generation_request.model
    assert "image" in content[0]
    assert content[0]["image"].startswith("data:image/png;base64,")
    assert content[1]["text"] == generation_request.prompt
    assert sent["parameters"]["size"] == "1024*1024"
    assert sent["parameters"]["n"] == 1
    assert sent["parameters"]["negative_prompt"] == generation_request.negative_constraints
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret-value"


def test_qwen_maps_auth_error(respx_mock, generation_request, tmp_path) -> None:
    respx_mock.post(QWEN_URL).respond(
        401, json={"code": "InvalidApiKey", "message": "No API-key provided."}
    )
    with pytest.raises(GenerationFailure) as captured:
        make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.AUTH
    assert captured.value.user_message_zh == "身份验证失败，请检查访问凭证。"
    assert captured.value.provider_code == "401"
    assert "secret-value" not in str(captured.value)


def test_qwen_maps_quota_429(respx_mock, generation_request, tmp_path) -> None:
    respx_mock.post(QWEN_URL).respond(
        429, json={"code": "Throttling.RateQuota", "message": "Too many requests"}
    )
    with pytest.raises(GenerationFailure) as captured:
        make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.QUOTA
    assert captured.value.user_message_zh == "生成额度已用尽或请求过于频繁。"
    assert captured.value.provider_code == "429"


def test_qwen_maps_moderation_error(respx_mock, generation_request, tmp_path) -> None:
    respx_mock.post(QWEN_URL).respond(
        400,
        json={"code": "DataInspectionFailed", "message": "input data may contain inappropriate content"},
    )
    with pytest.raises(GenerationFailure) as captured:
        make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.MODERATION
    assert captured.value.user_message_zh == "生成内容未通过安全审核，请调整提示词后重试。"
    assert captured.value.provider_code == "400"


def test_qwen_maps_timeout(respx_mock, generation_request, tmp_path) -> None:
    respx_mock.post(QWEN_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(GenerationFailure) as captured:
        make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.TIMEOUT
    assert captured.value.user_message_zh == "生成请求超时，请稍后重试。"
    assert captured.value.provider_code is None


def test_qwen_maps_malformed_body(respx_mock, generation_request, tmp_path) -> None:
    respx_mock.post(QWEN_URL).respond(json={"output": {"choices": []}, "request_id": "empty"})
    with pytest.raises(GenerationFailure) as captured:
        make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.MALFORMED
    assert captured.value.user_message_zh == "生成请求参数无效，请调整后重试。"


def test_qwen_rejects_non_image_download(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(QWEN_URL).respond(json=QWEN_FULL_RESPONSE)
    respx_mock.get(RESULT_URL).respond(
        content=b"not-an-image", headers={"Content-Type": "application/octet-stream"}
    )
    with pytest.raises(GenerationFailure) as captured:
        make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert captured.value.kind is FailureKind.MALFORMED


def test_qwen_writes_atomic_png_under_generated(
    respx_mock, generation_request, tmp_path
) -> None:
    respx_mock.post(QWEN_URL).respond(json=QWEN_FULL_RESPONSE)
    respx_mock.get(RESULT_URL).respond(
        content=PNG_BYTES, headers={"Content-Type": "image/png"}
    )
    result = make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    destination = result.local_files[0]
    assert destination.parent == tmp_path / "generated"
    assert destination.suffix == ".png"
    assert destination.exists()
    assert not list(destination.parent.glob(".*.tmp"))


def test_qwen_preserves_prompt_on_failure(
    respx_mock, generation_request, tmp_path
) -> None:
    original = generation_request.model_dump()
    respx_mock.post(QWEN_URL).respond(401, json={"code": "InvalidApiKey"})
    with pytest.raises(GenerationFailure):
        make_qwen(tmp_path).generate(generation_request, SecretStr("secret-value"))
    assert generation_request.model_dump() == original
    assert generation_request.prompt == "保持莲纹骨架，生成书签纹样"

