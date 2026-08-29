# -*- coding: utf-8 -*-
from pathlib import Path

from pydantic import ValidationError
import pytest

from pattern_reborn.generation.base import (
    FailureKind,
    GenerationFailure,
    GenerationRequest,
    ProviderId,
    StructureLevel,
    TargetApplication,
)
from tests.fixtures.images import write_image


@pytest.fixture
def reference_png(tmp_path: Path) -> Path:
    return write_image(tmp_path / "reference.png", image_format="PNG")


def make_generation_request(
    reference_png: Path,
    **overrides: object,
) -> GenerationRequest:
    payload: dict[str, object] = {
        "prompt": "保持莲纹骨架，生成书签纹样",
        "reference_path": reference_png,
        "model": "doubao-seedream-4-0-250828",
        "provider": ProviderId.SEEDREAM,
        "size": "1024x1024",
        "count": 1,
        "structure_level": StructureLevel.HIGH,
        "target_application": TargetApplication.BOOKMARK,
        "colors": ["qinghua-blue"],
        "negative_constraints": "避免现代卡通化",
    }
    payload.update(overrides)
    return GenerationRequest.model_validate(payload)


def test_generation_request_serialization_never_contains_key(reference_png) -> None:
    request = make_generation_request(reference_png)
    dumped = request.model_dump_json()
    assert "api_key" not in dumped
    assert "Bearer" not in dumped


def test_generation_request_rejects_credential_fields(reference_png: Path) -> None:
    with pytest.raises(ValidationError):
        make_generation_request(reference_png, api_key="secret-value")
    with pytest.raises(ValidationError):
        make_generation_request(reference_png, credential="secret-value")


def test_generation_request_count_must_be_exactly_one(reference_png: Path) -> None:
    with pytest.raises(ValidationError):
        make_generation_request(reference_png, count=0)
    with pytest.raises(ValidationError):
        make_generation_request(reference_png, count=2)


def test_generation_request_rejects_empty_or_malformed_size(reference_png: Path) -> None:
    with pytest.raises(ValidationError):
        make_generation_request(reference_png, size="")
    with pytest.raises(ValidationError):
        make_generation_request(reference_png, size="huge")


def test_generation_request_requires_exactly_one_reference_image(
    tmp_path: Path, reference_png: Path
) -> None:
    second = write_image(tmp_path / "second.png", image_format="PNG")
    with pytest.raises(ValidationError, match="参考"):
        make_generation_request(reference_png, reference_path=[])
    with pytest.raises(ValidationError, match="参考"):
        make_generation_request(reference_png, reference_path=[reference_png, second])
    with pytest.raises(ValidationError, match="参考"):
        make_generation_request(reference_png, reference_path="")


def test_generation_failure_redacts_arbitrary_provider_error_text() -> None:
    raw = (
        "HTTP/1.1 401 Unauthorized\n"
        "Authorization: Bearer sk-leaked-token\n"
        "X-Api-Key: abc123\n"
        "api_key=should-not-leak\n"
        "error: invalid key for user"
    )
    failure = GenerationFailure(
        FailureKind.AUTH,
        "身份验证失败，请检查访问凭证。",
        provider_code=raw,
    )
    rendered = f"{failure}{failure.provider_code}{failure!r}"
    assert "sk-leaked-token" not in rendered
    assert "Bearer" not in rendered
    assert "abc123" not in rendered
    assert "api_key" not in rendered
    assert "Authorization" not in rendered
    assert "invalid key for user" not in rendered
    assert failure.user_message_zh == "身份验证失败，请检查访问凭证。"
    assert failure.kind is FailureKind.AUTH
    assert failure.provider_code == "[REDACTED]"


def test_generation_failure_keeps_short_safe_provider_code() -> None:
    failure = GenerationFailure(
        FailureKind.QUOTA,
        "生成额度已用尽或请求过于频繁。",
        provider_code="429",
    )
    assert failure.provider_code == "429"
    assert "429" in str(failure)
