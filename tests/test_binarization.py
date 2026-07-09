import io
import os

from PIL import Image

from minecraft_fontgen.file_io import binarize_provider_bitmap

from helpers import block, make_png_bytes


def _provider_for(png_bytes, name="binp"):
    os.makedirs(f"work/glyphs/{name}", exist_ok=True)
    path = f"work/{name}.png"
    with open(path, "wb") as f:
        f.write(png_bytes)
    return {"file_path": path, "name": name, "output": f"work/glyphs/{name}"}


def _ink_pixels(binary_image):
    return {(x, y) for y in range(binary_image.height) for x in range(binary_image.width)
            if binary_image.getpixel((x, y)) == 0}


def test_dark_colored_pixels_survive_alpha_coverage():
    png = make_png_bytes(4, 4, block(0, 0, 2, 2), color=(40, 0, 0, 255))
    binary = binarize_provider_bitmap(_provider_for(png))
    assert _ink_pixels(binary) == set(block(0, 0, 2, 2))


def test_fully_opaque_image_falls_back_to_luminance():
    img = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    for x, y in block(1, 1, 2, 2):
        img.putpixel((x, y), (255, 255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    binary = binarize_provider_bitmap(_provider_for(buf.getvalue(), name="opaque"))
    assert _ink_pixels(binary) == set(block(1, 1, 2, 2))


def test_missing_texture_returns_none():
    provider = _provider_for(make_png_bytes(2, 2, []), name="gone")
    os.remove(provider["file_path"])
    assert binarize_provider_bitmap(provider) is None
