# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from PIL import Image
from pydantic import SecretStr
import pytest

from pattern_reborn.domain import CategoryId, ProfileId, ProvenanceClass
from pattern_reborn.generation.base import (
    FailureKind,
    GenerationFailure,
    GenerationRequest,
    ProviderId,
    RemoteGenerationResult,
)
from pattern_reborn.generation.service import GenerationService
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.patterns import LayoutKind, PatternRequest
from pattern_reborn.projects import ProjectRepository
from pattern_reborn.ui.home import DemoCase, load_validated_demos
from pattern_reborn.workflow import PatternRebornService

_KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "data" / "knowledge"
DEMO_ROOT = Path(__file__).resolve().parents[1] / "data" / "demo"

# The canvas the studio offers by default, so the judge flow is exercised with
# the shipped defaults rather than with a hand-tuned request.
DEMO_CANVAS = (256, 256)

_LAYOUT_BY_PROFILE = {
    ProfileId.SILHOUETTE: LayoutKind.RADIAL,
    ProfileId.TEXTILE: LayoutKind.FOUR_WAY,
    ProfileId.FLAT_COLOR: LayoutKind.MIRROR,
    ProfileId.ARTIFACT_PHOTO: LayoutKind.BORDER,
}


@dataclass(frozen=True, slots=True)
class DemoWorkflowFixture:
    """One bundled demonstration case, opened exactly as the home page opens it."""

    case: DemoCase
    profile: ProfileId
    pattern_request: PatternRequest

    @property
    def id(self) -> str:
        return self.case.id

    @property
    def title(self) -> str:
        return self.case.title_zh

    @property
    def category(self) -> CategoryId:
        assert self.case.category is not None
        return self.case.category

    @property
    def provenance(self) -> ProvenanceClass:
        assert self.case.provenance is not None
        return self.case.provenance

    @property
    def source(self) -> Path:
        return self.case.source_path

    @property
    def hint_box(self) -> tuple[float, float, float, float] | None:
        return self.case.hint_box


def competition_case_ids(root: Path = DEMO_ROOT) -> list[str]:
    """Case ids as the application itself validates them, or an empty list."""
    return [case.id for case in load_validated_demos(root)]


def load_demo_fixture(root: Path, case_id: str) -> DemoWorkflowFixture:
    """Build a case fixture from the same loader the home page uses."""
    case = next((item for item in load_validated_demos(root) if item.id == case_id), None)
    if case is None:
        raise AssertionError(f"演示案例不可用：{case_id}")
    if case.category is None or case.provenance is None:
        raise AssertionError(f"演示案例权属信息不完整：{case_id}")
    metadata = json.loads((root / case_id / "metadata.json").read_text(encoding="utf-8"))
    profile = ProfileId(metadata["profile"])
    return DemoWorkflowFixture(
        case=case,
        profile=profile,
        pattern_request=_pattern_request(profile, metadata.get("processing_defaults") or {}),
    )


def _pattern_request(profile: ProfileId, defaults: dict) -> PatternRequest:
    """Derive a repeat layout from the case's own documented defaults."""
    layout = _LAYOUT_BY_PROFILE[profile]
    if isinstance(defaults.get("radial"), dict):
        layout = LayoutKind.RADIAL
    elif isinstance(defaults.get("tile"), dict):
        layout = LayoutKind.FOUR_WAY
    return PatternRequest(layout=layout, canvas=DEMO_CANVAS, seed=20260830)


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
