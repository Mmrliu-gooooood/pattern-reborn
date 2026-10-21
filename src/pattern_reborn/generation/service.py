# -*- coding: utf-8 -*-
"""Credential resolution and explicit provider dispatch for image generation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import SecretStr

from pattern_reborn.config import ConfigError, MissingPlatformCredentialError, ProviderConfig
from pattern_reborn.generation.base import (
    CredentialMode,
    FailureKind,
    GenerationAdapter,
    GenerationFailure,
    GenerationRequest,
    ProviderId,
    RemoteGenerationResult,
    StructureLevel,
    TargetApplication,
)
from pattern_reborn.generation.http import USER_MESSAGE_ZH, mapped_failure

GenerationResult = RemoteGenerationResult

_STRUCTURE_ZH = {
    StructureLevel.LOW: "低",
    StructureLevel.MEDIUM: "中",
    StructureLevel.HIGH: "高",
}
_TARGET_ZH = {
    TargetApplication.PACKAGING: "包装",
    TargetApplication.BOOKMARK: "书签",
    TargetApplication.TEXTILE: "织物",
    TargetApplication.POSTER: "海报",
    TargetApplication.PHONE_CASE: "手机壳",
}
_SHARED_HTTP_CLIENT: httpx.Client | None = None


def compose_generation_prompt(request: GenerationRequest) -> str:
    parts = [
        f"结构保留 {request.structure_level.value}/{_STRUCTURE_ZH[request.structure_level]}",
        f"目标应用 {request.target_application.value}/{_TARGET_ZH[request.target_application]}",
    ]
    if request.colors:
        parts.append("色彩 " + ",".join(request.colors))
    line = "；".join(parts)
    prompt = request.prompt.rstrip()
    if line in prompt:
        return prompt
    return f"{prompt}\n{line}"


def _shared_http_client() -> httpx.Client:
    global _SHARED_HTTP_CLIENT
    if _SHARED_HTTP_CLIENT is None or _SHARED_HTTP_CLIENT.is_closed:
        _SHARED_HTTP_CLIENT = httpx.Client(timeout=60.0)
    return _SHARED_HTTP_CLIENT


class CredentialResolver(Protocol):
    def resolve(
        self,
        provider_id: ProviderId,
        mode: CredentialMode,
        byok: SecretStr | None,
    ) -> SecretStr: ...


class ProviderConfigCredentialResolver:
    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    def resolve(
        self,
        provider_id: ProviderId,
        mode: CredentialMode,
        byok: SecretStr | None,
    ) -> SecretStr:
        if mode is CredentialMode.BYOK:
            if byok is None or not byok.get_secret_value().strip():
                raise mapped_failure(FailureKind.MISSING_CREDENTIAL)
            return byok
        try:
            return self._config.platform_credential(provider_id)
        except MissingPlatformCredentialError as error:
            raise mapped_failure(FailureKind.MISSING_CREDENTIAL) from error


class GenerationService:
    def __init__(
        self,
        adapters: Mapping[ProviderId, GenerationAdapter],
        credential_resolver: CredentialResolver,
        *,
        config: ProviderConfig | None = None,
    ) -> None:
        self._adapters = dict(adapters)
        self._resolver = credential_resolver
        self._config = config

    def generate(
        self,
        request: GenerationRequest,
        mode: CredentialMode,
        byok: SecretStr | None = None,
    ) -> GenerationResult:
        try:
            adapter = self._adapters[request.provider]
        except KeyError:
            raise GenerationFailure(
                FailureKind.MALFORMED,
                USER_MESSAGE_ZH[FailureKind.MALFORMED],
            ) from None
        if self._config is not None:
            try:
                self._config.validate_request(request)
            except ConfigError as error:
                message = str(error).strip() or USER_MESSAGE_ZH[FailureKind.MALFORMED]
                raise GenerationFailure(FailureKind.MALFORMED, message) from error
        credential = self._resolver.resolve(request.provider, mode, byok)
        dispatched = request.model_copy(update={"prompt": compose_generation_prompt(request)})
        return adapter.generate(dispatched, credential)


def build_generation_service(*, config: ProviderConfig, output_dir: Path) -> GenerationService:
    from pattern_reborn.generation.qwen import QwenAdapter
    from pattern_reborn.generation.seedream import SeedreamAdapter
    from pattern_reborn.generation.custom import CustomImageAdapter

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    client = _shared_http_client()
    seedream = config.provider(ProviderId.SEEDREAM)
    qwen = config.provider(ProviderId.QWEN)
    adapters: dict[ProviderId, GenerationAdapter] = {
        ProviderId.SEEDREAM: SeedreamAdapter(client, seedream.base_url, destination),
        ProviderId.QWEN: QwenAdapter(client, qwen.base_url, destination),
    }
    for identifier in (ProviderId.CUSTOM, ProviderId.OPENROUTER):
        settings = config.provider(identifier)
        adapters[identifier] = CustomImageAdapter(client, settings.base_url, destination, settings.protocol, identifier)
    return GenerationService(adapters, ProviderConfigCredentialResolver(config), config=config)

