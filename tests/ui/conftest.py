# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from pattern_reborn.domain import CategoryId, ProfileId, ProvenanceClass
from pattern_reborn.generation.service import GenerationService
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.projects import ProjectRepository
from pattern_reborn.workflow import CreateProjectCommand, ExtractCommand, PatternRebornService
from tests.workflow_fixtures import FakeGenerationAdapter, StaticCredentialResolver

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "app.py"
KNOWLEDGE_DIR = REPO_ROOT / "data" / "knowledge"

STEP_LABELS = [
    "上传与分类",
    "智能提取",
    "纹样分析",
    "参数化重组",
    "AI 创意生成",
    "导出与溯源",
]


def all_text(app: AppTest) -> str:
    chunks: list[str] = []
    for attr in (
        "markdown",
        "title",
        "header",
        "subheader",
        "caption",
        "text",
        "info",
        "warning",
        "error",
        "success",
    ):
        for node in getattr(app, attr):
            value = getattr(node, "value", None)
            if value:
                chunks.append(str(value))
    for button in app.button:
        chunks.append(button.label)
    for image in app.image:
        chunks.extend(image.captions)
    return "\n".join(chunks)


def session_get(app: AppTest, key: str):
    try:
        return app.session_state[key]
    except KeyError:
        return None


def radio_option_labels(radio) -> list[str]:
    return [getattr(item, "label", item) for item in radio.options]


def widget_disabled(widget) -> bool:
    proto_disabled = bool(getattr(widget.proto, "disabled", False))
    attr_disabled = getattr(widget, "disabled", proto_disabled)
    return bool(attr_disabled or proto_disabled)


@pytest.fixture
def fake_adapters(tmp_path: Path) -> dict:
    output_dir = tmp_path / "fake-generated"
    output_dir.mkdir()
    from pattern_reborn.generation.base import ProviderId

    return {
        ProviderId.SEEDREAM: FakeGenerationAdapter(ProviderId.SEEDREAM, output_dir),
        ProviderId.QWEN: FakeGenerationAdapter(ProviderId.QWEN, output_dir),
    }


@pytest.fixture
def studio_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_adapters) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    demo_root = tmp_path / "demo"
    demo_root.mkdir()
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv("PATTERN_REBORN_WORKSPACE", str(workspace))
    monkeypatch.setenv("PATTERN_REBORN_OUTPUTS", str(outputs))
    monkeypatch.setenv("PATTERN_REBORN_DEMO_ROOT", str(demo_root))
    monkeypatch.delenv("SEEDREAM_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.setattr("pattern_reborn.capabilities.probe_online", lambda: True)

    def _fake_build_generation_service(*_args, **_kwargs):
        return GenerationService(fake_adapters, StaticCredentialResolver())

    monkeypatch.setattr(
        "pattern_reborn.generation.service.build_generation_service",
        _fake_build_generation_service,
        raising=False,
    )
    return workspace


@pytest.fixture
def source_image(tmp_path: Path) -> Path:
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    pixels = image.load()
    for y in range(16, 48):
        for x in range(16, 40):
            pixels[x, y] = (180, 40, 45)
        for x in range(40, 48):
            pixels[x, y] = (40, 60, 160)
    path = tmp_path / "motif.png"
    image.save(path, format="PNG")
    return path


def seed_extracted_project(workspace: Path, source: Path, fake_adapters) -> str:
    repository = ProjectRepository(workspace)
    generation = GenerationService(fake_adapters, StaticCredentialResolver())
    service = PatternRebornService(
        repository,
        knowledge=KnowledgeCatalog.load(KNOWLEDGE_DIR),
        generation=generation,
        export_root=workspace.parent / "outputs",
    )
    project = service.create_project(
        CreateProjectCommand(
            name="工坊项目",
            source=source,
            category=CategoryId.PAPER_CUTTING,
            provenance=ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
        )
    )
    extraction = service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    service.confirm_extraction(project.id, extraction.artifact_id)
    return project.id


@pytest.fixture
def studio_test(studio_workspace: Path) -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.session_state["route"] = "studio"
    return app


@pytest.fixture
def studio_at_extraction(
    studio_workspace: Path, source_image: Path, fake_adapters
) -> AppTest:
    project_id = seed_extracted_project(studio_workspace, source_image, fake_adapters)
    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.session_state["route"] = "studio"
    app.session_state["project_id"] = project_id
    app.session_state["studio_step"] = "智能提取"
    return app


@pytest.fixture
def studio_at_generation(
    studio_workspace: Path, source_image: Path, fake_adapters
) -> AppTest:
    project_id = seed_extracted_project(studio_workspace, source_image, fake_adapters)
    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.session_state["route"] = "studio"
    app.session_state["project_id"] = project_id
    app.session_state["studio_step"] = "AI 创意生成"
    return app
