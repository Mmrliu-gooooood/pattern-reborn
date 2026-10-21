"""Explicit public image-model discovery. Never sends credentials or project data."""
import re

import httpx

from .base import FailureKind
from .http import bounded_request, raise_mapped

CATALOG_URL = "https://openrouter.ai/api/v1/images/models"


def image_models(client: httpx.Client) -> list[dict]:
    response = bounded_request(client, "GET", CATALOG_URL)
    try:
        body = response.json()
        entries = body.get("data") if isinstance(body, dict) else None
        if not isinstance(entries, list) or len(entries) > 5000:
            raise ValueError("invalid model catalog")
        result = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            identifier, name = entry.get("id"), entry.get("name")
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,149}", identifier):
                continue
            architecture = entry.get("architecture") or {}
            if "image" not in architecture.get("input_modalities", []) or "image" not in architecture.get("output_modalities", []):
                continue
            parameters = entry.get("supported_parameters") or {}
            references = parameters.get("input_references")
            if not isinstance(references, dict) or not (references.get("min", 0) <= 1 <= references.get("max", 0)):
                continue
            formats = parameters.get("output_format", {}).get("values")
            if isinstance(formats, list) and "png" not in formats:
                continue
            sizes = parameters.get("resolution", {}).get("values", [])
            sizes = [s for s in sizes if isinstance(s, str) and re.fullmatch(r"\d+(?:\.\d+)?K|\d+x\d+", s)]
            result.append({"id": identifier, "name": name[:200] if isinstance(name, str) else identifier,
                           "size_options": sizes})
        return sorted(result, key=lambda item: item["name"].casefold())
    except (ValueError, TypeError, AttributeError):
        raise_mapped(FailureKind.MALFORMED)
