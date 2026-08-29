# -*- coding: utf-8 -*-
"""Alibaba Model Studio Qwen Image generation adapter."""

from __future__ import annotations

from pathlib import Path

import httpx
from pydantic import SecretStr

from pattern_reborn.generation.base import (
    FailureKind,
    GenerationRequest,
    ProviderId,
    RemoteGenerationResult,
)
from pattern_reborn.generation.http import (
    decode_image_value,
    encode_data_url,
    persist_generated_png,
    post_json,
    raise_mapped,
)

_GENERATION_PATH = "/api/v1/services/aigc/multimodal-generation/generation"


def _generation_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}{_GENERATION_PATH}"


def _qwen_size(size: str) -> str:
    return size.replace("x", "*")


def _extract_image_value(body: object) -> str:
    if not isinstance(body, dict):
        raise_mapped(FailureKind.MALFORMED)
    output = body.get("output")
    if not isinstance(output, dict):
        raise_mapped(FailureKind.MALFORMED)
    choices = output.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise_mapped(FailureKind.MALFORMED)
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise_mapped(FailureKind.MALFORMED)
    content = message.get("content")
    if not isinstance(content, list) or not content or not isinstance(content[0], dict):
        raise_mapped(FailureKind.MALFORMED)
    image = content[0].get("image")
    if not isinstance(image, str) or not image.strip():
        raise_mapped(FailureKind.MALFORMED)
    return image


class QwenAdapter:
    provider = ProviderId.QWEN

    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        output_dir: Path,
    ) -> None:
        self._client = client
        self._url = _generation_url(base_url)
        self._output_dir = output_dir

    def generate(
        self, request: GenerationRequest, credential: SecretStr
    ) -> RemoteGenerationResult:
        payload: dict[str, object] = {
            "model": request.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"image": encode_data_url(request.reference_path)},
                            {"text": request.prompt},
                        ],
                    }
                ]
            },
            "parameters": {
                "negative_prompt": request.negative_constraints,
                "size": _qwen_size(request.size),
                "n": 1,
                "watermark": False,
                "prompt_extend": False,
            },
        }
        response = post_json(self._client, self._url, payload, credential)
        try:
            body = response.json()
        except ValueError:
            raise_mapped(FailureKind.MALFORMED)
        image_bytes = decode_image_value(_extract_image_value(body), self._client)
        stored = persist_generated_png(image_bytes, self._output_dir, "qwen")
        return RemoteGenerationResult(
            provider=self.provider,
            model=request.model,
            prompt=request.prompt,
            local_files=[stored],
        )

