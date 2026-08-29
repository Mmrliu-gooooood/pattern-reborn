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
