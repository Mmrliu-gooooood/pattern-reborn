"""Versioned local settings. Windows credentials are bound to the current user by DPAPI.

The private file is outside project data and release manifests. Writes publish a
complete validated replacement; callers update live state only after success.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from .config import ProviderConfig, require_https_url
from .generation.base import CustomProtocol, ProviderId


class SettingsStoreError(ValueError):
    """Actionable local error, deliberately excluding file contents and secrets."""


def _dpapi(data: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise SettingsStoreError("保存密钥需要 Windows 当前用户加密服务；未保存任何明文密钥。")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming = Blob(len(data), buffer)
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        operation = crypt.CryptUnprotectData
        operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    else:
        operation = crypt.CryptProtectData
        operation.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(incoming), "Pattern Reborn local provider credential", None, None, None, 1, ctypes.byref(outgoing))
    operation.restype = wintypes.BOOL
    if not operation(*args):
        raise SettingsStoreError("Windows 无法加密或解密本地密钥；请使用原 Windows 用户，或备份并移走 .private/provider-settings.json 后重新设置。")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


class LocalProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str
    model: str = Field(min_length=1, max_length=150, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    protocol: CustomProtocol
    size_options: list[str] = Field(min_length=1, max_length=30)
    encrypted_key: str | None = None
    key_endpoint: str | None = None

    @field_validator("base_url", "key_endpoint")
    @classmethod
    def safe_url(cls, value):
        return require_https_url(value) if value is not None else None

    @field_validator("size_options")
    @classmethod
    def safe_sizes(cls, values):
        import re
        if any(not re.fullmatch(r"(?:\d+(?:\.\d+)?K|\d+x\d+)", item) or len(item) > 30 for item in values):
            raise ValueError("尺寸应为 1024x1024 或 2K 格式。")
        return list(dict.fromkeys(values))


class LocalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(default=1, ge=1, le=1)
    encryption: str = Field(default="windows-dpapi-current-user", pattern="^windows-dpapi-current-user$")
    default_provider: ProviderId
    providers: dict[ProviderId, LocalProvider]


class ProviderSettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> LocalSettings | None:
        if not self.path.exists():
            return None
        try:
            if self.path.stat().st_size > 256 * 1024:
                raise ValueError("large file")
            return LocalSettings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError, ValueError):
            raise SettingsStoreError("本地服务设置无法读取。原文件已保留；请备份并检查 .private/provider-settings.json，或移走该文件后重启并重新设置。") from None

    def credentials(self, settings: LocalSettings | None) -> dict[ProviderId, SecretStr]:
        keys = {}
        if settings:
            try:
                for identifier, provider in settings.providers.items():
                    if provider.encrypted_key:
                        if provider.key_endpoint != provider.base_url:
                            raise ValueError("credential destination mismatch")
                        raw = base64.b64decode(provider.encrypted_key, validate=True)
                        keys[identifier] = SecretStr(_dpapi(raw, decrypt=True).decode("utf-8"))
            except (ValueError, UnicodeError):
                raise SettingsStoreError("本地密钥无法解密。原文件已保留；请使用原 Windows 用户，或备份并移走 .private/provider-settings.json 后重新设置。") from None
        return keys

    @staticmethod
    def encrypt(key: SecretStr) -> str:
        return base64.b64encode(_dpapi(key.get_secret_value().encode("utf-8"))).decode("ascii")

    def save(self, settings: LocalSettings) -> None:
        payload = settings.model_dump_json(indent=2)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise SettingsStoreError("本地服务设置保存失败；原设置和密钥未更改。请检查磁盘空间与 .private 目录权限后重试。") from None
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def apply_local(config: ProviderConfig, settings: LocalSettings | None) -> ProviderConfig:
    result = config.model_copy(deep=True)
    if settings:
        result.default_provider = settings.default_provider
        for provider in result.providers:
            override = settings.providers.get(provider.id)
            if override:
                provider.base_url = override.base_url
                provider.default_model = override.model
                provider.protocol = override.protocol
                provider.size_options = override.size_options
    return result
