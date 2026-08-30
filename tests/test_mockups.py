# -*- coding: utf-8 -*-
import json
from pathlib import Path
import threading
import time

from PIL import Image
import pytest

import pattern_reborn.images as images_module
import pattern_reborn.mockups as mockups_module
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
    interrupted = tmp_path / ".bookmark.bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.mockup-txn"
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


def test_save_composed_mockup_recovers_after_a_crash_during_png_published_journal_advance(
    mockup_catalog,
    ai_pattern: ArtworkRef,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a crash replacing the journal after the PNG has reached its public path."""
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    destination = tmp_path / "bookmark.png"
    real_replace = images_module.os.replace

    def crash_before_advancing_png_journal(source: object, target: object) -> None:
        source_path = Path(source)
        target_path = Path(target)
        if (
            target_path.name == "journal.json"
            and source_path.name.startswith(".journal.")
            and '"png_published"' in source_path.read_text(encoding="utf-8")
        ):
            raise KeyboardInterrupt("simulated process crash")
        real_replace(source, target)

    monkeypatch.setattr(images_module.os, "replace", crash_before_advancing_png_journal)
    with pytest.raises(KeyboardInterrupt):
        save_composed_mockup(result, destination)

    monkeypatch.setattr(images_module.os, "replace", real_replace)
    save_composed_mockup(result, destination)

    with Image.open(destination) as saved:
        assert saved.size == result.image.size
    assert json.loads(destination.with_suffix(".json").read_text(encoding="utf-8")) == {"ai_assisted": True}


def test_save_composed_mockup_rejects_forged_transaction_directory_without_deleting_it(
    mockup_catalog, ai_pattern: ArtworkRef, tmp_path: Path
) -> None:
    """Catches recovery recursively deleting unrecognised content under a matching directory."""
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    destination = tmp_path / "bookmark.png"
    forged = tmp_path / ".bookmark.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.mockup-txn"
    forged.mkdir()
    sentinel = forged / "do-not-delete.txt"
    sentinel.write_text("keep", encoding="utf-8")
    (forged / "journal.json").write_text(
        json.dumps(
            {
                "destination": destination.name,
                "sidecar": destination.with_suffix(".json").name,
                "previous": {"png": False, "json": False},
                "state": "committed",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MockupError, match="事务"):
        save_composed_mockup(result, destination)

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_save_composed_mockup_reports_cleanup_failure_without_discarding_backups(
    mockup_catalog,
    ai_pattern: ArtworkRef,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches cleanup silently losing recovery material when backup deletion fails."""
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    destination = tmp_path / "bookmark.png"
    destination.write_bytes(b"old png")
    destination.with_suffix(".json").write_bytes(b'{"ai_assisted": false}\n')
    real_unlink = Path.unlink

    def reject_previous_png_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "previous.png":
            raise PermissionError("backup cleanup denied")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", reject_previous_png_unlink)

    with pytest.raises(MockupError, match="清理"):
        save_composed_mockup(result, destination)

    transaction = next(tmp_path.glob(".bookmark.*.mockup-txn"))
    assert (transaction / "previous.png").exists()
    assert json.loads((transaction / "journal.json").read_text(encoding="utf-8"))["state"] == "committed"


def test_save_composed_mockup_rejects_non_png_destination(
    mockup_catalog, ai_pattern: ArtworkRef, tmp_path: Path
) -> None:
    """Catches a sidecar path aliasing the requested public artifact path."""
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)

    with pytest.raises(MockupError, match="PNG"):
        save_composed_mockup(result, tmp_path / "bookmark.json")

    assert not (tmp_path / "bookmark.json").exists()


def test_save_composed_mockup_serializes_concurrent_publication_of_one_pair(
    mockup_catalog,
    ai_pattern: ArtworkRef,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches two publishers entering the recovery-to-publication window together."""
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    destination = tmp_path / "bookmark.png"
    first_staging_started = threading.Event()
    allow_first_to_continue = threading.Event()
    second_staging_started = threading.Event()
    real_stage_png = mockups_module._write_staged_png

    def pause_first_staging(image: Image.Image, path: Path) -> None:
        if threading.current_thread().name == "first-publisher":
            first_staging_started.set()
            assert allow_first_to_continue.wait(timeout=2)
        else:
            second_staging_started.set()
        real_stage_png(image, path)

    monkeypatch.setattr(mockups_module, "_write_staged_png", pause_first_staging)
    failures: list[BaseException] = []

    def publish() -> None:
        try:
            save_composed_mockup(result, destination)
        except BaseException as error:  # pragma: no cover - asserted below
            failures.append(error)

    first = threading.Thread(target=publish, name="first-publisher")
    second = threading.Thread(target=publish, name="second-publisher")
    first.start()
    assert first_staging_started.wait(timeout=2)
    second.start()
    time.sleep(0.1)
    assert not second_staging_started.is_set()
    allow_first_to_continue.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive() and not second.is_alive()
    assert failures == []
    assert second_staging_started.is_set()
