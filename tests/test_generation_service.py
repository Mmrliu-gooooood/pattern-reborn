# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
import pytest

from pattern_reborn.config import ProviderConfig
from pattern_reborn.generation.base import (
    CredentialMode,
    FailureKind,
    GenerationFailure,
    GenerationRequest,
    ProviderId,
    RemoteGenerationResult,
)
from tests.test_generation_base import make_generation_request, reference_png  # noqa: F401
from tests.test_qwen import PNG_BYTES, QWEN_FULL_RESPONSE, RESULT_URL
from tests.test_seedream import PNG_BASE64, SEEDREAM_URL


@pytest.fixture
def seedream_request(reference_png: Path) -> GenerationRequest:
    return make_generation_request(reference_png)


@pytest.fixture
def qwen_request(reference_png: Path) -> GenerationRequest:
    return make_generation_request(
        reference_png,
        provider=ProviderId.QWEN,
        model="qwen-image-3.0-pro",
        size="1024x1024",
    )


class RecordingResolver:
    def __init__(self, secret: str = "secret-value") -> None:
        self.secret = secret
        self.calls: list[tuple[ProviderId, CredentialMode, str | None]] = []

    def resolve(
        self,
        provider_id: ProviderId,
        mode: CredentialMode,
        byok: SecretStr | None,
    ) -> SecretStr:
        self.calls.append(
            (provider_id, mode, None if byok is None else byok.get_secret_value())
        )
        return SecretStr(self.secret)


class RecordingAdapter:
    def __init__(self, provider: ProviderId, *, error: Exception | None = None) -> None:
        self.provider = provider
        self.calls: list[GenerationRequest] = []
        self._error = error

    def generate(self, request: GenerationRequest, credential: SecretStr):
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return RemoteGenerationResult(
            provider=self.provider,
            model=request.model,
            prompt=request.prompt,
            local_files=[],
        )


def make_service(tmp_path: Path, resolver=None):
    import httpx

    from pattern_reborn.generation.qwen import QwenAdapter
    from pattern_reborn.generation.seedream import SeedreamAdapter
    from pattern_reborn.generation.service import GenerationService

    generated = tmp_path / "generated"
    adapters = {
        ProviderId.SEEDREAM: SeedreamAdapter(
            client=httpx.Client(),
            base_url="https://ark.example",
            output_dir=generated,
        ),
        ProviderId.QWEN: QwenAdapter(
            client=httpx.Client(),
            base_url="https://qwen.example",
            output_dir=generated,
        ),
    }
    return GenerationService(adapters, resolver or RecordingResolver())


def test_service_dispatches_to_requested_qwen_provider_only(
    respx_mock, qwen_request, tmp_path
) -> None:
    qwen_route = respx_mock.post(
        "https://qwen.example/api/v1/services/aigc/multimodal-generation/generation"
    ).respond(
        json=QWEN_FULL_RESPONSE
    )
    respx_mock.get(RESULT_URL).respond(
        content=PNG_BYTES, headers={"Content-Type": "image/png"}
    )
    result = make_service(tmp_path).generate(
        qwen_request, CredentialMode.BYOK, SecretStr("secret-value")
    )
    assert qwen_route.called
    assert result.provider is ProviderId.QWEN
    assert result.local_files[0].exists()


def test_service_dispatches_to_requested_seedream_provider_only(
    respx_mock, seedream_request, tmp_path
) -> None:
    seedream_route = respx_mock.post(SEEDREAM_URL).respond(
        json={"model": "seedream", "data": [{"b64_json": PNG_BASE64}], "usage": {}}
    )
    result = make_service(tmp_path).generate(
        seedream_request, CredentialMode.BYOK, SecretStr("secret-value")
    )
    assert seedream_route.called
    assert result.provider is ProviderId.SEEDREAM
    assert "secret-value" not in result.model_dump_json()


def test_one_adapter_failure_never_invokes_the_other(
    seedream_request,
) -> None:
    from pattern_reborn.generation.service import GenerationService

    seedream = RecordingAdapter(
        ProviderId.SEEDREAM,
        error=GenerationFailure(FailureKind.AUTH, "身份验证失败，请检查访问凭证。", "401"),
    )
    qwen = RecordingAdapter(ProviderId.QWEN)
    service = GenerationService(
        {ProviderId.SEEDREAM: seedream, ProviderId.QWEN: qwen},
        RecordingResolver(),
    )
    with pytest.raises(GenerationFailure) as captured:
        service.generate(seedream_request, CredentialMode.PLATFORM)
    assert captured.value.kind is FailureKind.AUTH
    assert seedream.calls
    assert qwen.calls == []


def test_seedream_http_failure_does_not_call_qwen_endpoint(
    respx_mock, seedream_request, tmp_path
) -> None:
    respx_mock.post(SEEDREAM_URL).respond(
        401, json={"error": {"code": "AuthenticationError"}}
    )
    original = seedream_request.model_dump()
    with pytest.raises(GenerationFailure) as captured:
        make_service(tmp_path).generate(
            seedream_request, CredentialMode.BYOK, SecretStr("secret-value")
        )
    assert captured.value.kind is FailureKind.AUTH
    assert seedream_request.model_dump() == original


def test_platform_mode_uses_resolver_without_byok(
    seedream_request,
) -> None:
    from pattern_reborn.generation.service import GenerationService

    resolver = RecordingResolver()
    seedream = RecordingAdapter(ProviderId.SEEDREAM)
    qwen = RecordingAdapter(ProviderId.QWEN)
    service = GenerationService(
        {ProviderId.SEEDREAM: seedream, ProviderId.QWEN: qwen},
        resolver,
    )
    service.generate(seedream_request, CredentialMode.PLATFORM)
    assert resolver.calls == [(ProviderId.SEEDREAM, CredentialMode.PLATFORM, None)]
    assert qwen.calls == []


def test_missing_platform_credential_does_not_call_adapter(
    seedream_request,
) -> None:
    from pattern_reborn.generation.service import (
        GenerationService,
        ProviderConfigCredentialResolver,
    )

    config = ProviderConfig.model_validate(
        {
            "default_provider": "seedream",
            "providers": [
                {
                    "id": "seedream",
                    "display_name_zh": "即梦 Seedream",
                    "base_url": "https://ark.example",
                    "default_model": "doubao-seedream-4-0-250828",
                    "api_key_env": "SEEDREAM_API_KEY",
                    "base_url_env": "SEEDREAM_BASE_URL",
                    "model_env": "SEEDREAM_MODEL",
                    "size_options": ["1024x1024"],
                },
                {
                    "id": "qwen",
                    "display_name_zh": "通义千问图像",
                    "base_url": "https://qwen.example",
                    "default_model": "qwen-image-3.0-pro",
                    "api_key_env": "QWEN_API_KEY",
                    "base_url_env": "QWEN_BASE_URL",
                    "model_env": "QWEN_MODEL",
                    "size_options": ["1024x1024"],
                },
            ],
        }
    )
    seedream = RecordingAdapter(ProviderId.SEEDREAM)
    qwen = RecordingAdapter(ProviderId.QWEN)
    service = GenerationService(
        {ProviderId.SEEDREAM: seedream, ProviderId.QWEN: qwen},
        ProviderConfigCredentialResolver(config),
    )
    original = seedream_request.model_dump()
    with pytest.raises(GenerationFailure) as captured:
        service.generate(seedream_request, CredentialMode.PLATFORM)
    assert captured.value.kind is FailureKind.MISSING_CREDENTIAL
    assert captured.value.user_message_zh == "未配置平台访问凭证。"
    assert seedream.calls == []
    assert qwen.calls == []
    assert seedream_request.model_dump() == original


