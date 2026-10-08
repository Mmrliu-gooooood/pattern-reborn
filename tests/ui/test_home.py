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
from pattern_reborn.ui.home import load_validated_demos

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


def test_home_demo_cards_show_creator_and_license(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo_root = tmp_path / "demo"
    case = demo_root / "lotus"
    case.mkdir(parents=True)
    Image.new("RGB", (8, 8), (20, 80, 40)).save(case / "source.png")
    (case / "metadata.json").write_text(
        json.dumps(
            {
                "title": "莲纹剪纸演示",
                "creator_institution": "Sean Chiu",
                "license": "CC BY-SA 4.0",
                "category": "paper_cutting",
                "provenance": "traditional_reference",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (demo_root / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "lotus-paper-cut",
                        "title_zh": "莲纹剪纸演示",
                        "source": "lotus/source.png",
                    }
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
    assert "Sean Chiu" in text
    assert "CC BY-SA" in text


def test_demo_cases_carry_their_documented_processing_region(tmp_path: Path) -> None:
    """The bundled cases document the region worth extracting; load it.

    Without this, a judge opening the ceramic or architectural case meets
    「器物照片配置需要有效 ROI」 with nothing to act on.
    """
    demo_root = tmp_path / "demo"
    for case_id, defaults in (
        ("with-roi", {"roi": [0.02, 0.08, 0.22, 0.62], "manual_box": [0.3, 0.3, 0.6, 0.6]}),
        ("with-manual-box", {"manual_box": [0.28, 0.18, 0.62, 0.72]}),
        ("with-named-roi", {"beam_roi": [0.18, 0.22, 0.82, 0.62]}),
        ("without-region", {"craft_preset": "none"}),
    ):
        case = demo_root / case_id
        case.mkdir(parents=True)
        Image.new("RGB", (8, 8), (20, 80, 40)).save(case / "source.png")
        (case / "metadata.json").write_text(
            json.dumps(
                {
                    "title": case_id,
                    "creator_institution": "演示",
                    "license": "Public Domain",
                    "category": "ceramic_ornament",
                    "provenance": "traditional_reference",
                    "processing_defaults": defaults,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    (demo_root / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {"id": case_id, "title_zh": case_id, "source": f"{case_id}/source.png"}
                    for case_id in (
                        "with-roi",
                        "with-manual-box",
                        "with-named-roi",
                        "without-region",
                    )
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    regions = {case.id: case.hint_box for case in load_validated_demos(demo_root)}

    # `roi` is the documented primary region; it outranks the others.
    assert regions["with-roi"] == (0.02, 0.08, 0.22, 0.62)
    assert regions["with-manual-box"] == (0.28, 0.18, 0.62, 0.72)
    assert regions["with-named-roi"] == (0.18, 0.22, 0.82, 0.62)
    assert regions["without-region"] is None


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


def test_home_explains_each_optional_capability(app_test: AppTest, monkeypatch) -> None:
    """A missing extra must be explained, not silently omitted."""
    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", lambda name: None)
    app_test.run()
    assert not app_test.exception
    text = _all_text(app_test)
    for label in ("SVG 矢量导出", "MobileSAM 引导分割", "可绘制画布"):
        assert label in text, label
    assert "不可用" in text
    # The reason string must reach the user, so "not installed" is distinguishable.
    assert "VTracer" in text or "画布" in text


def test_home_does_not_expose_default_api_secret(
    app_test: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEEDREAM_API_KEY", SECRET)
    app_test.run()
    assert not app_test.exception
    assert SECRET not in _all_text(app_test)
    assert SECRET not in repr(app_test)


def test_home_never_shows_raw_enum_values_in_project_cards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Project cards must speak Chinese, not expose CategoryId/StepId values."""
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
    project.processing_parameters["current_step"] = "extraction"
    repository.save(project)

    app = AppTest.from_file(APP_PATH, default_timeout=15)
    app.run()
    assert not app.exception
    text = _all_text(app)
    assert "可打开项目" in text
    assert "剪纸" in text
    assert "轮廓提取" in text
    assert "paper_cutting" not in text
    assert "user_supplied_unverified" not in text


def test_hero_demo_button_toggles_the_demo_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The button used to write a session key that nothing ever read."""
    demo_root = tmp_path / "demo"
    case = demo_root / "lotus"
    case.mkdir(parents=True)
    Image.new("RGB", (8, 8), (20, 80, 40)).save(case / "source.png")
    (demo_root / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "lotus-paper-cut",
                        "title_zh": "莲纹剪纸演示",
                        "source": "lotus/source.png",
                    }
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
    assert "莲纹剪纸演示" in _all_text(app)

    collapse = next(button for button in app.button if button.label == "收起演示案例")
    collapse.click().run()
    assert not app.exception
    assert "莲纹剪纸演示" not in _all_text(app)

    expand = next(button for button in app.button if button.label == "查看演示案例")
    expand.click().run()
    assert not app.exception
    assert "莲纹剪纸演示" in _all_text(app)


def test_home_category_names_are_not_duplicated(app_test: AppTest) -> None:
    """Each category name appears once, as the card's actionable title."""
    catalog = KnowledgeCatalog.load(KNOWLEDGE_DIR)
    app_test.run()
    assert not app_test.exception
    markdown = "\n".join(str(node.value) for node in app_test.markdown)
    labels = [button.label for button in app_test.button]
    for category in catalog.categories:
        name = category.display_name_zh
        assert name in labels
        assert name not in markdown


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
