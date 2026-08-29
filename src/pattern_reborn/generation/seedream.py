# -*- coding: utf-8 -*-
"""Volcengine Ark Seedream image generation adapter."""

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

_GENERATION_PATH = "/api/v3/images/generations"


class SeedreamAdapter:
    provider = ProviderId.SEEDREAM

    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        output_dir: Path,
    ) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}{_GENERATION_PATH}"
        self._output_dir = output_dir

    def generate(
        self, request: GenerationRequest, credential: SecretStr
    ) -> RemoteGenerationResult:
        payload: dict[str, object] = {
            "model": request.model,
            "prompt": request.prompt,
            "image": encode_data_url(request.reference_path),
            "size": request.size,
            "response_format": "b64_json",
        }
        response = post_json(self._client, self._url, payload, credential)
        try:
            body = response.json()
        except ValueError:
            raise_mapped(FailureKind.MALFORMED)
        items = body.get("data") if isinstance(body, dict) else None
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            raise_mapped(FailureKind.MALFORMED)
        item = items[0]
        raw = item.get("b64_json") or item.get("url")
        if not isinstance(raw, str) or not raw.strip():
            raise_mapped(FailureKind.MALFORMED)
        image_bytes = decode_image_value(raw, self._client)
        stored = persist_generated_png(image_bytes, self._output_dir, "seedream")
        return RemoteGenerationResult(
            provider=self.provider,
            model=request.model,
            prompt=request.prompt,
            local_files=[stored],
        )

