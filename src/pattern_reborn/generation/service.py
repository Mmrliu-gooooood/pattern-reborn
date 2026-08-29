# -*- coding: utf-8 -*-
"""Credential resolution and explicit provider dispatch for image generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pydantic import SecretStr

from pattern_reborn.config import MissingPlatformCredentialError, ProviderConfig
from pattern_reborn.generation.base import (
    CredentialMode,
    FailureKind,
    GenerationAdapter,
    GenerationFailure,
    GenerationRequest,
    ProviderId,
    RemoteGenerationResult,
)
from pattern_reborn.generation.http import USER_MESSAGE_ZH, mapped_failure

GenerationResult = RemoteGenerationResult


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
    ) -> None:
        self._adapters = dict(adapters)
        self._resolver = credential_resolver

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
        credential = self._resolver.resolve(request.provider, mode, byok)
        return adapter.generate(request, credential)

