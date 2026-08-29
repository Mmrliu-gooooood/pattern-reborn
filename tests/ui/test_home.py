# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from pattern_reborn.domain import CategoryId, ProvenanceClass
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.projects import ProjectRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "app.py"
KNOWLEDGE_DIR = REPO_ROOT / "data" / "knowledge"
SECRET = "seedream-secret-value-never-display"


def _all_text(app: AppTest) -> str:
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
    return "\n".join(chunks)


@pytest.fixture
def app_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    demo_root = tmp_path / "demo"
    demo_root.mkdir()
    monkeypatch.setenv("PATTERN_REBORN_WORKSPACE", str(workspace))
    monkeypatch.setenv("PATTERN_REBORN_DEMO_ROOT", str(demo_root))
    monkeypatch.delenv("SEEDREAM_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    return AppTest.from_file(APP_PATH, default_timeout=15)


def test_home_shows_primary_action_recent_history_and_readiness(app_test: AppTest) -> None:
    app_test.run()
    assert not app_test.exception
    assert any(button.label == "开始新创作" for button in app_test.button)
    markdown = [node.value for node in app_test.markdown]
    assert any("最近项目" in value for value in markdown)
    assert any("本地处理可用" in value for value in markdown)


def test_home_shows_nine_category_labels(app_test: AppTest) -> None:
    catalog = KnowledgeCatalog.load(KNOWLEDGE_DIR)
    names = [category.display_name_zh for category in catalog.categories]
    assert len(names) == 9
    app_test.run()
    assert not app_test.exception
    labels = [button.label for button in app_test.button]
    for name in names:
        assert name in labels


def test_home_shows_at_most_three_recent_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    demo_root = tmp_path / "demo"
    demo_root.mkdir()
    monkeypatch.setenv("PATTERN_REBORN_WORKSPACE", str(workspace))
    monkeypatch.setenv("PATTERN_REBORN_DEMO_ROOT", str(demo_root))
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 8), (200, 40, 40)).save(source)
    repository = ProjectRepository(workspace)
    names = ["项目甲", "项目乙", "项目丙", "项目丁"]
    for index, name in enumerate(names):
        project = repository.create(
            name,
            source,
            CategoryId.PAPER_CUTTING,
            ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
        )
        project.updated_at = datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=index)
        repository.save(project)

    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.run()
    assert not app.exception
    text = _all_text(app)
    assert "项目甲" not in text
    assert "项目乙" in text
    assert "项目丙" in text
    assert "项目丁" in text
    recent_buttons = [button.label for button in app.button if button.label in set(names)]
    assert len(recent_buttons) == 3
    assert set(recent_buttons) == {"项目乙", "项目丙", "项目丁"}


def test_home_hides_demo_cards_when_assets_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo_root = tmp_path / "demo"
    present = demo_root / "lotus"
    present.mkdir(parents=True)
    Image.new("RGB", (8, 8), (20, 80, 40)).save(present / "source.png")
    (demo_root / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "lotus-paper-cut",
                        "title_zh": "莲纹剪纸演示",
                        "source": "lotus/source.png",
                    },
                    {
                        "id": "missing-case",
                        "title_zh": "缺失素材演示",
                        "source": "missing/source.png",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PATTERN_REBORN_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("PATTERN_REBORN_DEMO_ROOT", str(demo_root))
    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.run()
    assert not app.exception
    text = _all_text(app)
    assert "莲纹剪纸演示" in text
    assert "缺失素材演示" not in text


def test_home_does_not_expose_default_api_secret(
    app_test: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEEDREAM_API_KEY", SECRET)
    app_test.run()
    assert not app_test.exception
    assert SECRET not in _all_text(app_test)
    assert SECRET not in repr(app_test)


def test_recent_project_is_history_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    demo_root = tmp_path / "demo"
    demo_root.mkdir()
    monkeypatch.setenv("PATTERN_REBORN_WORKSPACE", str(workspace))
    monkeypatch.setenv("PATTERN_REBORN_DEMO_ROOT", str(demo_root))
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 8), (200, 40, 40)).save(source)
    repository = ProjectRepository(workspace)
    project = repository.create(
        "可打开项目",
        source,
        CategoryId.PAPER_CUTTING,
        ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
    )
    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.run()
    assert not app.exception
    opener = next(button for button in app.button if button.label == project.name)
    opener.click().run()
    assert not app.exception
    markdown = [node.value for node in app.markdown]
    assert any("创作工坊" in str(value) for value in markdown)
