"""Explicit image API protocols. The configured endpoint is used verbatim.

No path guessing, automatic protocol fallback or extra generation request is
performed. Only one local reference and one output are supported.
"""
from pathlib import Path

import httpx
from pydantic import SecretStr

from .base import CustomProtocol, FailureKind, GenerationRequest, ProviderId, RemoteGenerationResult
from .http import bounded_request, decode_image_value, encode_data_url, persist_generated_png, post_json, raise_mapped
from pattern_reborn.images import probe_image


class CustomImageAdapter:
    def __init__(self, client: httpx.Client, endpoint: str, output_dir: Path,
                 protocol: CustomProtocol, provider: ProviderId = ProviderId.CUSTOM):
        self._client, self._url, self._output_dir = client, endpoint, Path(output_dir)
        self._protocol, self.provider = protocol, provider

    def generate(self, request: GenerationRequest, credential: SecretStr) -> RemoteGenerationResult:
        payload = {"model": request.model, "prompt": request.prompt, "size": request.size, "n": 1}
        if self._protocol is CustomProtocol.OPENAI_IMAGES_EDITS:
            reference = request.reference_path
            # Validate reference before reading; httpx chooses a valid boundary.
            info = probe_image(reference)
            mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(info.format, "application/octet-stream")
            with reference.open("rb") as stream:
                response = bounded_request(self._client, "POST", self._url,
                    data={name: str(value) for name, value in payload.items()},
                    files={"image": ("reference" + reference.suffix.lower(), stream, mime)}, timeout=180.0,
                    headers={"Authorization": f"Bearer {credential.get_secret_value()}"})
        else:
            image = encode_data_url(request.reference_path)
            if self._protocol is CustomProtocol.OPENROUTER_IMAGES:
                payload.update(input_references=[{"type": "image_url", "image_url": {"url": image}}], output_format="png")
            else:
                payload["image"] = image
            response = post_json(self._client, self._url, payload, credential, timeout=180.0)
        try:
            body = response.json()
            items = body.get("data") if isinstance(body, dict) else None
            if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
                raise ValueError("invalid image response")
            raw = items[0].get("b64_json") or items[0].get("url")
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("missing image")
        except (ValueError, TypeError):
            raise_mapped(FailureKind.MALFORMED)
        stored = persist_generated_png(decode_image_value(raw, self._client), self._output_dir, self.provider.value)
        return RemoteGenerationResult(provider=self.provider, model=request.model, prompt=request.prompt, local_files=[stored])
