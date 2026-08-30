# -*- coding: utf-8 -*-
import json
from pathlib import Path

from PIL import Image
import pytest

import pattern_reborn.images as images_module
from pattern_reborn.mockups import (
    ArtworkRef,
    MockupError,
    MockupOptions,
    compose_mockup,
    load_mockup_catalog,
    save_composed_mockup,
)
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


def test_compose_persists_ai_assisted_provenance_sidecar(mockup_catalog, ai_pattern, tmp_path: Path) -> None:
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    destination = tmp_path / "bookmark.png"

    save_composed_mockup(result, destination)

    sidecar = json.loads(destination.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["ai_assisted"] is True


def test_compose_persists_non_ai_provenance_sidecar(mockup_catalog, tmp_path: Path) -> None:
    path = write_image(tmp_path / "motif.png", image_format="PNG", mode="RGBA", size=(16, 16))
    result = compose_mockup(
        mockup_catalog["tote_bag"],
        ArtworkRef(path=path, ai_assisted=False),
        MockupOptions(),
    )
    destination = tmp_path / "tote_bag.png"

    save_composed_mockup(result, destination)

    sidecar = json.loads(destination.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["ai_assisted"] is False


def test_compose_mockup_rejects_decompression_bomb_as_typed_chinese_error(
    mockup_catalog, ai_pattern: ArtworkRef, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches a direct Pillow decode that leaks a decompression-bomb error."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 4)

    with pytest.raises(MockupError, match="图像"):
        compose_mockup(mockup_catalog["bookmark"], ai_pattern)


@pytest.mark.parametrize("has_previous_pair", [False, True])
def test_save_composed_mockup_restores_the_previous_pair_when_json_replace_fails(
    mockup_catalog,
    ai_pattern: ArtworkRef,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    has_previous_pair: bool,
) -> None:
    """Catches a partial publication when only the sidecar replacement fails."""
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    destination = tmp_path / "bookmark.png"
    sidecar = destination.with_suffix(".json")
    old_png = b"old png"
    old_json = b'{"ai_assisted": false}\n'
    if has_previous_pair:
        destination.write_bytes(old_png)
        sidecar.write_bytes(old_json)

    real_replace = images_module.os.replace
    calls = 0

    def fail_on_second_replace(source: object, target: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("sidecar replace denied")
        real_replace(source, target)

    monkeypatch.setattr(images_module.os, "replace", fail_on_second_replace)

    with pytest.raises(MockupError, match="保存"):
        save_composed_mockup(result, destination)

    if has_previous_pair:
        assert destination.read_bytes() == old_png
        assert sidecar.read_bytes() == old_json
    else:
        assert not destination.exists()
        assert not sidecar.exists()


def test_save_composed_mockup_discards_an_interrupted_preparation_before_publishing(
    mockup_catalog, ai_pattern: ArtworkRef, tmp_path: Path
) -> None:
    """Catches recovery treating an unpublished transaction as a partial publish."""
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    destination = tmp_path / "bookmark.png"
    sidecar = destination.with_suffix(".json")
    destination.write_bytes(b"old png")
    sidecar.write_text('{"ai_assisted": false}\n', encoding="utf-8")
    interrupted = tmp_path / ".bookmark.interrupted.mockup-txn"
    interrupted.mkdir()
    (interrupted / "journal.json").write_text(
        json.dumps(
            {
                "destination": destination.name,
                "sidecar": sidecar.name,
                "previous": {"png": True, "json": True},
                "state": "preparing",
            }
        ),
        encoding="utf-8",
    )

    save_composed_mockup(result, destination)

    with Image.open(destination) as saved:
        assert saved.size == result.image.size
    assert json.loads(sidecar.read_text(encoding="utf-8")) == {"ai_assisted": True}
    assert not interrupted.exists()


def test_save_composed_mockup_can_retry_recovery_after_the_second_rollback_fails(
    mockup_catalog,
    ai_pattern: ArtworkRef,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches rollback moving the only PNG backup before the JSON rollback fails."""
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    destination = tmp_path / "bookmark.png"
    sidecar = destination.with_suffix(".json")
    destination.write_bytes(b"old png")
    sidecar.write_bytes(b'{"ai_assisted": false}\n')
    real_replace = images_module.os.replace
    calls = 0

    def fail_sidecar_publish_and_json_rollback(source: object, target: object) -> None:
        nonlocal calls
        calls += 1
        if calls in {2, 4}:
            raise PermissionError("replace denied")
        real_replace(source, target)

    monkeypatch.setattr(images_module.os, "replace", fail_sidecar_publish_and_json_rollback)
    with pytest.raises(MockupError, match="保存"):
        save_composed_mockup(result, destination)

    monkeypatch.setattr(images_module.os, "replace", real_replace)
    save_composed_mockup(result, destination)

    with Image.open(destination) as saved:
        assert saved.size == result.image.size
    assert json.loads(sidecar.read_text(encoding="utf-8")) == {"ai_assisted": True}
