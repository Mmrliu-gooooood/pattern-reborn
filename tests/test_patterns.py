from PIL import Image
import pytest

from pattern_reborn.patterns import LayoutKind, PatternRequest, compose_pattern


@pytest.fixture
def motif_rgba() -> Image.Image:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(8, 24):
        for x in range(8, 24):
            pixels[x, y] = (180, 40, 45, 255)
    return image


@pytest.fixture
def seamless_motif() -> Image.Image:
    """An 8x8 tile whose opposite edges already match, so repeats stay seamless."""
    image = Image.new("RGBA", (8, 8))
    pixels = image.load()
    for y in range(8):
        for x in range(8):
            red = (x * 31 + y * 7) % 200 + 20
            green = (x * 13 + y * 29) % 200 + 20
            blue = (x * 17 + y * 19) % 200 + 20
            pixels[x, y] = (red, green, blue, 255)
    for y in range(8):
        pixels[7, y] = pixels[0, y]
    for x in range(8):
        pixels[x, 7] = pixels[x, 0]
    pixels[7, 7] = pixels[0, 0]
    return image


def _assert_opposite_edges_match(image: Image.Image) -> None:
    pixels = image.load()
    width, height = image.size
    for x in range(width):
        assert pixels[x, 0] == pixels[x, height - 1]
    for y in range(height):
        assert pixels[0, y] == pixels[width - 1, y]


@pytest.mark.parametrize("layout", list(LayoutKind))
def test_layout_is_repeatable_for_same_seed(layout, motif_rgba) -> None:
    request = PatternRequest(layout=layout, canvas=(512, 512), seed=17)
    assert compose_pattern(motif_rgba, request).tobytes() == compose_pattern(motif_rgba, request).tobytes()


@pytest.mark.parametrize("layout", list(LayoutKind))
def test_layouts_return_rgba_at_requested_canvas(layout, motif_rgba) -> None:
    request = PatternRequest(layout=layout, canvas=(64, 48), seed=3)
    result = compose_pattern(motif_rgba, request)
    assert result.mode == "RGBA"
    assert result.size == (64, 48)


@pytest.mark.parametrize("layout", [LayoutKind.TWO_WAY, LayoutKind.FOUR_WAY])
def test_two_way_and_four_way_are_seamless_for_repeat_fixture(layout, seamless_motif) -> None:
    request = PatternRequest(layout=layout, canvas=(32, 32), seed=0, spacing=0, scale=1.0, angle=0.0)
    result = compose_pattern(seamless_motif, request)
    assert result.mode == "RGBA"
    assert result.size == (32, 32)
    _assert_opposite_edges_match(result)


def test_compose_pattern_does_not_mutate_source(motif_rgba) -> None:
    before = motif_rgba.tobytes()
    compose_pattern(motif_rgba, PatternRequest(layout=LayoutKind.MIRROR, canvas=(64, 64), seed=1))
    assert motif_rgba.tobytes() == before
    assert motif_rgba.size == (32, 32)


def test_pattern_request_persists_composition_parameters() -> None:
    request = PatternRequest(
        layout=LayoutKind.RADIAL,
        canvas=(256, 128),
        seed=17,
        spacing=4,
        scale=0.5,
        angle=15.0,
        palette_substitutions={"#B4282D": "#1F6B4A"},
    )
    dumped = request.model_dump()
    assert dumped["layout"] is LayoutKind.RADIAL or dumped["layout"] == LayoutKind.RADIAL
    assert dumped["canvas"] == (256, 128)
    assert dumped["seed"] == 17
    assert dumped["spacing"] == 4
    assert dumped["scale"] == 0.5
    assert dumped["angle"] == 15.0
    assert dumped["palette_substitutions"] == {"#B4282D": "#1F6B4A"}


def test_palette_substitutions_recolor_motif_without_mutating_source() -> None:
    motif = Image.new("RGBA", (8, 8), (180, 40, 45, 255))
    before = motif.tobytes()
    request = PatternRequest(
        layout=LayoutKind.TWO_WAY,
        canvas=(16, 16),
        seed=0,
        palette_substitutions={"#B4282D": "#1F6B4A"},
    )

    result = compose_pattern(motif, request)

    assert motif.tobytes() == before
    assert (180, 40, 45, 255) not in set(result.getdata())
    assert (31, 107, 74, 255) in set(result.getdata())
