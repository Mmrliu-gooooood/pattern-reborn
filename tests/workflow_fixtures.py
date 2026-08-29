# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PIL import Image
from pydantic import SecretStr
import pytest

from pattern_reborn.generation.base import (
    FailureKind,
    GenerationFailure,
    GenerationRequest,
    ProviderId,
    RemoteGenerationResult,
)
from pattern_reborn.generation.service import GenerationService
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.projects import ProjectRepository
from pattern_reborn.workflow import PatternRebornService

_KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "data" / "knowledge"


class StaticCredentialResolver:
    def resolve(self, provider_id: ProviderId, mode: object, byok: SecretStr | None) -> SecretStr:
        _ = provider_id, mode
        if byok is not None and byok.get_secret_value().strip():
            return byok
        return SecretStr("test-credential")


class FakeGenerationAdapter:
    def __init__(self, provider: ProviderId, output_dir: Path) -> None:
        self.provider = provider
        self.output_dir = output_dir
        self.fail = False
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest, credential: SecretStr) -> RemoteGenerationResult:
        _ = credential
        self.calls.append(request)
        if self.fail:
            raise GenerationFailure(FailureKind.TIMEOUT, "生成请求超时，请稍后重试。")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / f"{self.provider.value}.png"
        Image.new("RGB", (8, 8), (18, 72, 54)).save(destination, format="PNG")
        return RemoteGenerationResult(
            provider=self.provider,
            model=request.model,
            prompt=request.prompt,
            local_files=[destination],
        )


@pytest.fixture
def source_fixture(tmp_path: Path) -> Path:
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    pixels = image.load()
    for y in range(16, 48):
        for x in range(16, 40):
            pixels[x, y] = (180, 40, 45)
    for y in range(16, 48):
        for x in range(40, 48):
            pixels[x, y] = (40, 60, 160)
    path = tmp_path / "motif.png"
    image.save(path, format="PNG")
    return path


@pytest.fixture
def generation_adapters(tmp_path: Path) -> dict[ProviderId, FakeGenerationAdapter]:
    output_dir = tmp_path / "fake-generated"
    output_dir.mkdir()
    return {
        ProviderId.SEEDREAM: FakeGenerationAdapter(ProviderId.SEEDREAM, output_dir),
        ProviderId.QWEN: FakeGenerationAdapter(ProviderId.QWEN, output_dir),
    }


@pytest.fixture
def app_service(
    tmp_path: Path, generation_adapters: dict[ProviderId, FakeGenerationAdapter]
) -> PatternRebornService:
    repository = ProjectRepository(tmp_path / "workspace")
    generation = GenerationService(generation_adapters, StaticCredentialResolver())
    return PatternRebornService(
        repository,
        knowledge=KnowledgeCatalog.load(_KNOWLEDGE_DIR),
        generation=generation,
        export_root=tmp_path / "outputs",
    )
