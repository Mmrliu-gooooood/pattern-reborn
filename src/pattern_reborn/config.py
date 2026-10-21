# -*- coding: utf-8 -*-
"""Load editable, non-secret provider configuration."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from pattern_reborn.generation.base import CustomProtocol, GenerationRequest, ProviderId


class ConfigError(ValueError):
    """提供商配置无法安全加载或验证。"""


class MissingPlatformCredentialError(ConfigError):
    """本地环境未配置平台访问凭证。"""


def require_https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError("仅允许 https 地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ConfigError("服务地址不能包含认证信息、查询参数或片段。")
    try:
        _ = parsed.port
    except ValueError:
        raise ConfigError("服务地址端口无效。") from None
    return value


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: ProviderId
    display_name_zh: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    default_model: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    base_url_env: str = Field(min_length=1)
    model_env: str = Field(min_length=1)
    size_options: list[str] = Field(min_length=1)
    protocol: CustomProtocol = CustomProtocol.OPENAI_IMAGES_EDITS

    @field_validator("base_url")
    @classmethod
    def require_https_base_url(cls, value: str) -> str:
        return require_https_url(value)

    @field_validator("api_key_env", "base_url_env", "model_env")
    @classmethod
    def require_env_name(cls, value: str) -> str:
        if "=" in value or " " in value:
            raise ValueError("配置只能保存环境变量名称。")
        return value


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    default_provider: ProviderId
    providers: list[ProviderSettings] = Field(min_length=2)

    @field_validator("providers")
    @classmethod
    def require_seedream_and_qwen(
        cls, value: list[ProviderSettings]
    ) -> list[ProviderSettings]:
        identifiers = [item.id for item in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("提供商标识不能重复。")
        if not {ProviderId.SEEDREAM, ProviderId.QWEN}.issubset(identifiers):
            raise ValueError("必须同时配置 Seedream 与 Qwen。")
        if ProviderId.CUSTOM not in identifiers:
            value = [*value, default_custom_settings()]
        if ProviderId.OPENROUTER not in identifiers:
            value = [*value, default_openrouter_settings()]
        return value

    def provider(self, provider_id: ProviderId) -> ProviderSettings:
        for item in self.providers:
            if item.id is provider_id:
                return item
        raise ConfigError(f"未配置提供商：{provider_id.value}。")

    def validate_request(self, request: GenerationRequest) -> None:
        settings = self.provider(request.provider)
        if request.size not in settings.size_options:
            raise ConfigError(f"输出尺寸不受支持：{request.size}。")

    def platform_credential(self, provider_id: ProviderId) -> SecretStr:
        settings = self.provider(provider_id)
        value = os.environ.get(settings.api_key_env)
        if value is None or not str(value).strip():
            raise MissingPlatformCredentialError(
                f"未配置平台访问凭证。请在本地 .env 中设置 {settings.api_key_env}。"
            )
        return SecretStr(str(value))


def default_custom_settings() -> ProviderSettings:
    return ProviderSettings(id=ProviderId.CUSTOM, display_name_zh="第三方 / 自定义 API",
        base_url="https://api.example.com/v1/images/edits", default_model="your-image-model",
        api_key_env="CUSTOM_API_KEY", base_url_env="CUSTOM_BASE_URL", model_env="CUSTOM_MODEL",
        size_options=["1024x1024"], protocol=CustomProtocol.OPENAI_IMAGES_EDITS)


def default_openrouter_settings() -> ProviderSettings:
    return ProviderSettings(id=ProviderId.OPENROUTER, display_name_zh="OpenRouter",
        base_url="https://openrouter.ai/api/v1/images", default_model="qwen/qwen-image-2.1-turbo",
        api_key_env="OPENROUTER_API_KEY", base_url_env="OPENROUTER_BASE_URL", model_env="OPENROUTER_MODEL",
        size_options=["1K", "2K"], protocol=CustomProtocol.OPENROUTER_IMAGES)


def load_provider_config(
    path: Path, environ: Mapping[str, str] | None = None
) -> ProviderConfig:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"无法读取提供商配置文件 {path.name}。") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"提供商配置文件 {path.name} 无效（JSON 位置：第 {error.lineno} 行）。"
        ) from None
    try:
        config = ProviderConfig.model_validate(payload)
    except ValidationError as error:
        detail = error.errors()[0]
        raise ConfigError(f"提供商配置文件 {path.name} 无效：{detail['msg']}") from None
    env = os.environ if environ is None else environ
    updated: list[ProviderSettings] = []
    for provider in config.providers:
        base_override = str(env.get(provider.base_url_env, "")).strip()
        model_override = str(env.get(provider.model_env, "")).strip()
        base_url = require_https_url(base_override) if base_override else provider.base_url
        default_model = model_override or provider.default_model
        updated.append(
            provider.model_copy(update={"base_url": base_url, "default_model": default_model})
        )
    return config.model_copy(update={"providers": updated})
