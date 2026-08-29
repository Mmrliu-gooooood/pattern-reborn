from pathlib import Path

from PIL import Image


def write_image(path: Path, *, image_format: str, mode: str = "RGB", size: tuple[int, int] = (12, 8)) -> Path:
    """Write a small deterministic image without using external fixtures."""
    image = Image.new(mode, size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            red = (x * 31 + y * 7) % 256
            green = (x * 13 + y * 29) % 256
            blue = (x * 17 + y * 19) % 256
            if mode == "RGBA":
                pixels[x, y] = (red, green, blue, (x * 23 + y * 11) % 256)
            else:
                pixels[x, y] = (red, green, blue)
    image.save(path, format=image_format)
    return path


def write_paletted_png(path: Path, *, transparent: bool) -> Path:
    """Write a tiny hard-edged P-mode PNG whose Lanczos result differs from nearest-neighbor."""
    image = Image.new("P", (16, 8))
    image.putpalette(
        [0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (256 * 3 - 12)
    )
    image.putdata(
        [
            0 if x < 6 else 1 if x < 10 else 2 if (x + y) % 2 else 3
            for y in range(image.height)
            for x in range(image.width)
        ]
    )
    if transparent:
        image.info["transparency"] = 0
    image.save(path, format="PNG")
    return path
