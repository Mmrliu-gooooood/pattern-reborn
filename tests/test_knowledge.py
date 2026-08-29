import json
from pathlib import Path

import pytest

from pattern_reborn.domain import CategoryId, ProfileId
from pattern_reborn.knowledge import CatalogLoadError, KnowledgeCatalog


KNOWLEDGE_DIR = Path(__file__).parents[1] / "data" / "knowledge"


@pytest.fixture
def catalog() -> KnowledgeCatalog:
    return KnowledgeCatalog.load(KNOWLEDGE_DIR)


def test_catalog_contains_exact_nine_category_to_profile_mappings(
    catalog: KnowledgeCatalog,
) -> None:
    assert {
        category.id: category.profile
        for category in catalog.categories
    } == {
        CategoryId.PAPER_CUTTING: ProfileId.SILHOUETTE,
        CategoryId.EMBROIDERY_BROCADE: ProfileId.TEXTILE,
        CategoryId.DYEING_TEXTILE: ProfileId.TEXTILE,
        CategoryId.CERAMIC_ORNAMENT: ProfileId.ARTIFACT_PHOTO,
        CategoryId.LACQUER_ORNAMENT: ProfileId.FLAT_COLOR,
        CategoryId.FOLK_PAINTING: ProfileId.FLAT_COLOR,
        CategoryId.ARCHITECTURAL_ORNAMENT: ProfileId.FLAT_COLOR,
        CategoryId.METAL_JEWELRY: ProfileId.ARTIFACT_PHOTO,
        CategoryId.FOLK_CRAFTS: ProfileId.SILHOUETTE,
    }
    assert {profile.id for profile in catalog.profiles} == set(ProfileId)


def test_every_category_and_profile_has_explicit_parameters_and_extraction_limitations(
    catalog: KnowledgeCatalog,
) -> None:
    for category in catalog.categories:
        assert category.display_name_zh
        assert category.default_parameters.threshold_mode
        assert "提取" in category.limitations_zh
        assert "非遗" not in category.cultural_note_zh

    for profile in catalog.profiles:
        assert profile.parameters.threshold_mode
        assert "提取" in profile.limitations_zh


def test_profile_for_returns_explicit_profile_parameters(catalog: KnowledgeCatalog) -> None:
    profile = catalog.profile_for(CategoryId.CERAMIC_ORNAMENT)

    assert profile.id is ProfileId.ARTIFACT_PHOTO
    assert profile.parameters.manual_region_required is True
    assert profile.parameters.threshold_mode == "grabcut_box"


def test_traditional_colors_are_cited_platform_approximations_with_unique_slugs(
    catalog: KnowledgeCatalog,
) -> None:
    assert len(catalog.colors) >= 12
    assert len({color.slug for color in catalog.colors}) == len(catalog.colors)
    for color in catalog.colors:
        assert color.name_zh
        assert color.hex_value.startswith("#")
        assert len(color.hex_value) == 7
        assert color.reference_title
        assert color.reference_url or color.reference_bibliography
        assert "平台近似" in color.digital_value_note_zh


def test_load_reports_filename_and_json_location_for_schema_errors(tmp_path: Path) -> None:
    categories = {
        "profiles": [],
        "categories": [],
        "unexpected": True,
    }
    colors = {"colors": []}
    (tmp_path / "categories.json").write_text(
        json.dumps(categories), encoding="utf-8"
    )
    (tmp_path / "traditional_colors.json").write_text(
        json.dumps(colors), encoding="utf-8"
    )

    with pytest.raises(CatalogLoadError) as raised:
        KnowledgeCatalog.load(tmp_path)

    message = str(raised.value)
    assert "categories.json" in message
    assert "JSON 位置" in message
    assert "$" in message
    assert "Traceback" not in message


def test_load_reports_filename_and_line_column_for_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "categories.json").write_text("{invalid", encoding="utf-8")
    (tmp_path / "traditional_colors.json").write_text(
        '{"colors": []}', encoding="utf-8"
    )

    with pytest.raises(CatalogLoadError) as raised:
        KnowledgeCatalog.load(tmp_path)

    message = str(raised.value)
    assert "categories.json" in message
    assert "第 1 行，第 2 列" in message
    assert "Traceback" not in message


def test_load_rejects_duplicate_category_ids_with_source_and_location(tmp_path: Path) -> None:
    categories = json.loads((KNOWLEDGE_DIR / "categories.json").read_text(encoding="utf-8"))
    categories["categories"].append(categories["categories"][0])
    (tmp_path / "categories.json").write_text(
        json.dumps(categories, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "traditional_colors.json").write_text(
        (KNOWLEDGE_DIR / "traditional_colors.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(CatalogLoadError) as raised:
        KnowledgeCatalog.load(tmp_path)

    message = str(raised.value)
    assert "categories.json" in message
    assert "JSON 位置" in message
    assert "$" in message


def test_load_rejects_missing_required_category_with_source_and_location(
    tmp_path: Path,
) -> None:
    categories = json.loads((KNOWLEDGE_DIR / "categories.json").read_text(encoding="utf-8"))
    categories["categories"] = [
        category
        for category in categories["categories"]
        if category["id"] != CategoryId.PAPER_CUTTING.value
    ]
    _write_catalog_copy(tmp_path, categories)

    with pytest.raises(CatalogLoadError) as raised:
        KnowledgeCatalog.load(tmp_path)

    message = str(raised.value)
    assert "categories.json" in message
    assert "JSON 位置" in message
    assert "$.categories" in message


def test_load_rejects_missing_required_profile_with_source_and_location(
    tmp_path: Path,
) -> None:
    categories = json.loads((KNOWLEDGE_DIR / "categories.json").read_text(encoding="utf-8"))
    categories["profiles"] = [
        profile
        for profile in categories["profiles"]
        if profile["id"] != ProfileId.TEXTILE.value
    ]
    for category in categories["categories"]:
        if category["profile"] == ProfileId.TEXTILE.value:
            category["profile"] = ProfileId.FLAT_COLOR.value
    _write_catalog_copy(tmp_path, categories)

    with pytest.raises(CatalogLoadError) as raised:
        KnowledgeCatalog.load(tmp_path)

    message = str(raised.value)
    assert "categories.json" in message
    assert "JSON 位置" in message
    assert "$.profiles" in message


def _write_catalog_copy(tmp_path: Path, categories: dict[str, object]) -> None:
    (tmp_path / "categories.json").write_text(
        json.dumps(categories, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "traditional_colors.json").write_text(
        (KNOWLEDGE_DIR / "traditional_colors.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
