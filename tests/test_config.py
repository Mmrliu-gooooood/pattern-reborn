# -*- coding: utf-8 -*-
import json
from pathlib import Path

from pydantic import SecretStr
import pytest

from pattern_reborn.config import (
    ConfigError,
    MissingPlatformCredentialError,
    ProviderConfig,
    load_provider_config,
    require_https_url,
)
from pattern_reborn.generation.base import ProviderId
from tests.test_generation_base import make_generation_request, reference_png  # noqa: F401


REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_JSON = REPO_ROOT / "config" / "providers.json"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


@pytest.fixture
def provider_config() -> ProviderConfig:
    return load_provider_config(PROVIDERS_JSON)


def test_provider_config_exposes_both_manual_choices(provider_config) -> None:
    assert provider_config.default_provider == ProviderId.SEEDREAM
    assert {p.id for p in provider_config.providers} == {
        ProviderId.SEEDREAM, ProviderId.QWEN, ProviderId.CUSTOM, ProviderId.OPENROUTER,
    }
    assert provider_config.provider(ProviderId.QWEN).default_model == "qwen-image-3.0-pro"


def test_providers_json_stores_environment_variable_names_only() -> None:
    raw = PROVIDERS_JSON.read_text(encoding="utf-8")
    payload = json.loads(raw)
    serialized = json.dumps(payload)
    assert "SEEDREAM_API_KEY" in serialized
    assert "QWEN_API_KEY" in serialized
    assert "sk-" not in serialized
    for provider in payload["providers"]:
        assert provider["api_key_env"].endswith("_API_KEY")
        assert not str(provider.get("api_key", "")).strip()


def test_env_example_documents_empty_credentials_and_overrides() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for name in (
        "SEEDREAM_API_KEY",
        "QWEN_API_KEY",
        "SEEDREAM_BASE_URL",
        "SEEDREAM_MODEL",
        "QWEN_BASE_URL",
        "QWEN_MODEL",
    ):
        assert f"{name}=" in text
        for line in text.splitlines():
            if line.startswith(f"{name}="):
                assert line.split("=", 1)[1] == ""


def test_provider_config_rejects_size_outside_provider_options(
    provider_config: ProviderConfig, reference_png: Path
) -> None:
    request = make_generation_request(reference_png, size="1x1")
    with pytest.raises(ConfigError, match="尺寸"):
        provider_config.validate_request(request)


def test_https_url_validation_rejects_non_https_schemes() -> None:
    with pytest.raises(ConfigError, match="https"):
        require_https_url("http://ark.example/api")
    with pytest.raises(ConfigError, match="https"):
        require_https_url("file:///etc/passwd")
    with pytest.raises(ConfigError, match="https"):
        require_https_url("ftp://dashscope.example")
    assert require_https_url("https://dashscope.aliyuncs.com") == "https://dashscope.aliyuncs.com"


def test_provider_config_rejects_non_https_base_url(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    path.write_text(
        json.dumps(
            {
                "default_provider": "seedream",
                "providers": [
                    {
                        "id": "seedream",
                        "display_name_zh": "即梦",
                        "base_url": "http://ark.example",
                        "default_model": "doubao-seedream-4-0-250828",
                        "api_key_env": "SEEDREAM_API_KEY",
                        "base_url_env": "SEEDREAM_BASE_URL",
                        "model_env": "SEEDREAM_MODEL",
                        "size_options": ["1024x1024"],
                    },
                    {
                        "id": "qwen",
                        "display_name_zh": "通义千问图像",
                        "base_url": "https://dashscope.aliyuncs.com",
                        "default_model": "qwen-image-3.0-pro",
                        "api_key_env": "QWEN_API_KEY",
                        "base_url_env": "QWEN_BASE_URL",
                        "model_env": "QWEN_MODEL",
                        "size_options": ["1024x1024"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="https"):
        load_provider_config(path)


def test_env_base_url_override_must_be_https(
    monkeypatch: pytest.MonkeyPatch, provider_config: ProviderConfig
) -> None:
    monkeypatch.setenv("SEEDREAM_BASE_URL", "http://insecure.example")
    with pytest.raises(ConfigError, match="https"):
        load_provider_config(PROVIDERS_JSON)


def test_absent_platform_credentials_are_typed_error_without_env_dump(
    monkeypatch: pytest.MonkeyPatch, provider_config: ProviderConfig
) -> None:
    monkeypatch.setenv("UNRELATED_SECRET", "env-dump-token")
    monkeypatch.delenv("SEEDREAM_API_KEY", raising=False)
    with pytest.raises(MissingPlatformCredentialError, match="凭证") as captured:
        provider_config.platform_credential(ProviderId.SEEDREAM)
    message = str(captured.value)
    assert "env-dump-token" not in message
    assert "UNRELATED_SECRET" not in message
    assert "os.environ" not in message


def test_platform_credential_is_secret_str(
    monkeypatch: pytest.MonkeyPatch, provider_config: ProviderConfig
) -> None:
    monkeypatch.setenv("SEEDREAM_API_KEY", "session-only-value")
    secret = provider_config.platform_credential(ProviderId.SEEDREAM)
    assert isinstance(secret, SecretStr)
    assert "session-only-value" not in repr(secret)
    assert secret.get_secret_value() == "session-only-value"
