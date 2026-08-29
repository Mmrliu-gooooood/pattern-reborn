from pathlib import Path

import pytest

from pattern_reborn.vectorize import Vectorizer, VectorSettings, find_vtracer
from tests.fixtures.images import write_image


def test_vectorizer_reports_unavailable_without_breaking_png(monkeypatch) -> None:
    monkeypatch.setattr("pattern_reborn.vectorize.find_vtracer", lambda: None)
    result = Vectorizer().vectorize(Path("motif.png"), Path("motif.svg"))
    assert result.available is False
    assert result.reason_zh


def test_vectorizer_capability_reports_unavailable_when_missing(monkeypatch) -> None:
    monkeypatch.setattr("pattern_reborn.vectorize.find_vtracer", lambda: None)
    status = Vectorizer().capability()
    assert status.available is False
    assert status.reason_zh


def test_successful_vectorize_writes_svg_atomically_without_mutating_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_image(tmp_path / "motif.png", image_format="PNG", mode="RGBA", size=(8, 8))
    destination = tmp_path / "motif.svg"
    before = source.read_bytes()

    class Present:
        @staticmethod
        def convert_image_to_svg_py(image_path: str, out_path: str, **kwargs: object) -> None:
            assert Path(image_path).read_bytes() == before
            Path(out_path).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"></svg>',
                encoding="utf-8",
            )

    monkeypatch.setattr("pattern_reborn.vectorize.find_vtracer", lambda: Present)

    result = Vectorizer().vectorize(source, destination, VectorSettings())

    assert result.available is True
    assert result.destination == destination
    assert destination.is_file()
    assert "<svg" in destination.read_text(encoding="utf-8").lower()
    assert source.read_bytes() == before
    assert not list(tmp_path.glob(".motif.svg.*.tmp"))


def test_malformed_vtracer_output_returns_typed_error_and_keeps_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_image(tmp_path / "motif.png", image_format="PNG", size=(8, 8))
    destination = tmp_path / "motif.svg"
    destination.write_text("previous", encoding="utf-8")
    before = source.read_bytes()

    class Malformed:
        @staticmethod
        def convert_image_to_svg_py(image_path: str, out_path: str, **kwargs: object) -> None:
            Path(out_path).write_text("not-an-svg", encoding="utf-8")

    monkeypatch.setattr("pattern_reborn.vectorize.find_vtracer", lambda: Malformed)

    result = Vectorizer().vectorize(source, destination)

    assert result.available is False
    assert result.reason_zh
    assert result.destination is None
    assert destination.read_text(encoding="utf-8") == "previous"
    assert source.read_bytes() == before
    assert not list(tmp_path.glob(".motif.svg.*.tmp"))


def test_absent_vtracer_output_returns_typed_error_and_keeps_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_image(tmp_path / "motif.png", image_format="PNG", size=(8, 8))
    destination = tmp_path / "motif.svg"
    before = source.read_bytes()

    class Silent:
        @staticmethod
        def convert_image_to_svg_py(image_path: str, out_path: str, **kwargs: object) -> None:
            return None

    monkeypatch.setattr("pattern_reborn.vectorize.find_vtracer", lambda: Silent)

    result = Vectorizer().vectorize(source, destination)

    assert result.available is False
    assert result.reason_zh
    assert result.destination is None
    assert not destination.exists()
    assert source.read_bytes() == before
    assert not list(tmp_path.glob(".motif.svg.*.tmp"))


def test_find_vtracer_is_the_single_discovery_hook() -> None:
    discovered = find_vtracer()
    assert discovered is None or hasattr(discovered, "convert_image_to_svg_py")


def test_installed_vtracer_writes_svg_atomically_without_mutating_png(tmp_path: Path) -> None:
    if find_vtracer() is None:
        pytest.skip("VTracer is not installed in this environment")

    source = write_image(tmp_path / "motif.png", image_format="PNG", mode="RGBA", size=(8, 8))
    destination = tmp_path / "motif.svg"
    before = source.read_bytes()

    result = Vectorizer().vectorize(source, destination)

    assert result.available is True
    assert result.destination == destination
    assert destination.is_file()
    assert "<svg" in destination.read_text(encoding="utf-8").lower()
    assert source.read_bytes() == before
    assert not list(tmp_path.glob(".motif.svg.*.tmp"))
