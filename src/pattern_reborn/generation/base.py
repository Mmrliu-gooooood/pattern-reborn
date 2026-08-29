# -*- coding: utf-8 -*-
"""Provider-neutral image generation contracts without credential fields."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ProviderId(str, Enum):
    SEEDREAM = "seedream"
    QWEN = "qwen"


class CredentialMode(str, Enum):
    PLATFORM = "platform"
    BYOK = "byok"


class StructureLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TargetApplication(str, Enum):
    PACKAGING = "packaging"
    BOOKMARK = "bookmark"
    TEXTILE = "textile"
    POSTER = "poster"
    PHONE_CASE = "phone_case"


class FailureKind(str, Enum):
    AUTH = "auth"
    QUOTA = "quota"
    MODERATION = "moderation"
    TIMEOUT = "timeout"
    MALFORMED = "malformed"
    MISSING_CREDENTIAL = "missing_credential"


_SAFE_PROVIDER_CODE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_SECRET_SHAPED = re.compile(
    r"(?i)(?:api[_-]?key|\bauthorization\b|\bbearer\b|\bbasic\s+\S+|sk-[A-Za-z0-9._-]+)"
)


def redact_provider_code(value: str | None) -> str | None:
    """Keep short safe codes; redact headers, keys, and arbitrary provider dumps."""
    if value is None or value == "":
        return None
    if _SECRET_SHAPED.search(value) or not _SAFE_PROVIDER_CODE.fullmatch(value):
        return "[REDACTED]"
    return value


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prompt: str = Field(min_length=1)
    reference_path: Path
    model: str = Field(min_length=1)
    provider: ProviderId
    size: str = Field(pattern=r"^(?:\d+K|\d+x\d+)$")
    count: Literal[1] = 1
    structure_level: StructureLevel
    target_application: TargetApplication
    colors: list[str] = Field(default_factory=list)
    negative_constraints: str = ""

    @field_validator("reference_path", mode="before")
    @classmethod
    def require_exactly_one_reference(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            if len(value) != 1:
                raise ValueError("生成请求必须恰好包含一张本地参考图。")
            value = value[0]
        if value is None or value == "":
            raise ValueError("生成请求必须恰好包含一张本地参考图。")
        return value


class RemoteGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    provider: ProviderId
    model: str
    prompt: str
    local_files: list[Path]


class GenerationFailure(Exception):
    """Mapped generation failure with a Chinese message and redacted provider code."""

    def __init__(
        self,
        kind: FailureKind,
        user_message_zh: str,
        provider_code: str | None = None,
    ) -> None:
        self.kind = kind
        self.user_message_zh = user_message_zh
        self.provider_code = redact_provider_code(provider_code)
        message = user_message_zh
        if self.provider_code:
            message = f"{user_message_zh}（{self.provider_code}）"
        super().__init__(message)


class GenerationAdapter(Protocol):
    provider: ProviderId

    def generate(
        self, request: GenerationRequest, credential: SecretStr
    ) -> RemoteGenerationResult: ...
