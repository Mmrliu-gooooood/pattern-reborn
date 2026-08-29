# -*- coding: utf-8 -*-
from pathlib import Path

from PIL import Image
import pytest

from pattern_reborn.mockups import ArtworkRef, MockupOptions, compose_mockup, load_mockup_catalog
from tests.fixtures.images import write_image


@pytest.fixture
def mockup_catalog() -> dict:
    return load_mockup_catalog()


@pytest.fixture
def ai_pattern(tmp_path: Path) -> ArtworkRef:
    path = write_image(tmp_path / "ai-pattern.png", image_format="PNG", mode="RGBA", size=(24, 24))
    return ArtworkRef(path=path, ai_assisted=True)


def test_mockup_preserves_template_and_labels_ai_input(mockup_catalog, ai_pattern) -> None:
    template_bytes = mockup_catalog["bookmark"].path.read_bytes()
    artwork_bytes = ai_pattern.path.read_bytes()

    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)

    assert result.image.size == mockup_catalog["bookmark"].canvas_size
    assert result.ai_assisted is True
    assert mockup_catalog["bookmark"].path.read_bytes() == template_bytes
    assert ai_pattern.path.read_bytes() == artwork_bytes


def test_catalog_covers_three_original_templates(mockup_catalog) -> None:
    assert set(mockup_catalog) == {"bookmark", "tote_bag", "phone_case"}
    for template_id, template in mockup_catalog.items():
        assert template.id == template_id
        assert template.path.name == f"{template_id}.png"
        assert template.path.is_file()
        assert template.creator == "Pattern Reborn team"
        assert template.license == "project-original"
        assert template.date
        assert template.canvas_size[0] > 0 and template.canvas_size[1] > 0
        assert len(template.placement_polygon) >= 4
        with Image.open(template.path) as image:
            assert image.size == template.canvas_size


def test_non_ai_artwork_is_not_labeled_assisted(mockup_catalog, tmp_path: Path) -> None:
    path = write_image(tmp_path / "motif.png", image_format="PNG", mode="RGBA", size=(16, 16))
    result = compose_mockup(
        mockup_catalog["tote_bag"],
        ArtworkRef(path=path, ai_assisted=False),
        MockupOptions(),
    )
    assert result.ai_assisted is False
    assert result.image.size == mockup_catalog["tote_bag"].canvas_size


def test_compose_keeps_template_pixels_outside_placement(mockup_catalog, tmp_path: Path) -> None:
    template = mockup_catalog["phone_case"]
    path = write_image(tmp_path / "fill.png", image_format="PNG", mode="RGBA", size=(12, 12))
    result = compose_mockup(template, ArtworkRef(path=path, ai_assisted=False))

    with Image.open(template.path) as original:
        original_rgba = original.convert("RGBA")
        assert result.image.getpixel((0, 0)) == original_rgba.getpixel((0, 0))
        assert result.image.getpixel((result.image.width - 1, 0)) == original_rgba.getpixel(
            (original_rgba.width - 1, 0)
        )
