import gc
import os
import weakref

import numpy as np
from PIL import Image

import minecraft_fontgen.file_io as file_io
from minecraft_fontgen.config import INK_ALPHA_THRESHOLD
from minecraft_fontgen.file_io import (
    binarize_provider_bitmap,
    binarize_rgba,
    crop_tile,
    crop_tile_rgba,
    load_provider_rgba,
    slice_provider_tiles,
    _tile_box,
)

from helpers import block, make_png_bytes


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _legacy_binarize(img):
    """Verbatim copy of the binarization body as it existed before the M1 split,
    so the refactor can be pinned byte-for-byte."""
    alpha = img.getchannel("A")
    if alpha.getextrema() == (255, 255):
        bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
        flat = Image.alpha_composite(bg, img).convert("L")
        flat = Image.eval(flat, lambda x: 255 - x)
        return flat.point(lambda x: 0 if x < 128 else 255, "1")
    return alpha.point(lambda a: 0 if a > INK_ALPHA_THRESHOLD else 255, "1")


def _provider_for(png_bytes, name="rgbap"):
    os.makedirs(f"work/glyphs/{name}", exist_ok=True)
    path = f"work/{name}.png"
    with open(path, "wb") as f:
        f.write(png_bytes)
    return {"file_path": path, "name": name, "output": f"work/glyphs/{name}"}


def _rgba_sheet(width, height, painter):
    arr = np.zeros((height, width, 4), np.uint8)
    painter(arr)
    return Image.fromarray(arr, "RGBA")


# ---------------------------------------------------------------------------
# binarize split equivalence (the no-mono-regression net)
# ---------------------------------------------------------------------------

def test_binarize_split_equivalence():
    # branch 1: fully-opaque image -> luminance threshold
    opaque = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    for x, y in block(1, 1, 2, 2):
        opaque.putpixel((x, y), (255, 255, 255, 255))

    # branch 2: partial transparency -> alpha threshold
    alpha_cov = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    for x, y in block(0, 0, 2, 2):
        alpha_cov.putpixel((x, y), (255, 255, 255, 255))

    # branch 3: dark colored opaque ink on transparency -> alpha threshold keeps it
    dark = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    for x, y in block(2, 2, 2, 2):
        dark.putpixel((x, y), (40, 0, 0, 255))

    for img in (opaque, alpha_cov, dark):
        assert binarize_rgba(img).tobytes() == _legacy_binarize(img).tobytes()


def test_load_decode_once(monkeypatch):
    png = make_png_bytes(16, 8, block(0, 0, 8, 8))
    provider = _provider_for(png)
    provider.update({"columns": 2, "rows": 1, "chars": ["A", "B"],
                     "height": 8, "file_name": "x.png"})

    opens = {"n": 0}
    real_open = file_io.Image.open

    def counting_open(*a, **k):
        opens["n"] += 1
        return real_open(*a, **k)

    monkeypatch.setattr(file_io.Image, "open", counting_open)
    slice_provider_tiles([provider], color_mode=True)
    # exactly one decode serves the whole provider; nothing re-opens the file
    assert opens["n"] == 1
    assert len(provider["tiles"]) == 2


def test_binarize_provider_bitmap_wrapper_unchanged():
    png = make_png_bytes(4, 4, block(0, 0, 2, 2), color=(40, 0, 0, 255))
    provider = _provider_for(png, name="wrap")
    binary = binarize_provider_bitmap(provider)

    ink = {(x, y) for y in range(binary.height) for x in range(binary.width)
           if binary.getpixel((x, y)) == 0}
    assert ink == set(block(0, 0, 2, 2))
    # the wrapper still emits both whole-sheet debug images
    assert os.path.isfile("work/glyphs/wrap/wrap.png")
    assert os.path.isfile("work/glyphs/wrap/wrap_grayscale.png")


def test_rgba_preserved():
    sheet = _rgba_sheet(16, 8, lambda a: (
        a.__setitem__((slice(None), slice(8, 12)), (220, 40, 40, 255)),
        a.__setitem__((slice(None), slice(12, 16)), (40, 60, 220, 255)),
    ))
    tile = {"location": (1, 0), "size": (8, 8)}
    cell = crop_tile_rgba(sheet, tile)

    assert cell.size == (8, 8)
    assert cell.getpixel((0, 0)) == (220, 40, 40, 255)
    assert cell.getpixel((7, 0)) == (40, 60, 220, 255)
    # two distinct opaque colours survive the crop unflattened
    assert cell.getpixel((0, 0)) != cell.getpixel((7, 0))


def test_tile_box_shared():
    sheet = _rgba_sheet(24, 16, lambda a: a.__setitem__(
        (slice(None), slice(None)), (10, 20, 30, 255)))
    binary = binarize_rgba(sheet)
    tile = {"location": (2, 1), "size": (8, 8), "output": "work/glyphs/t/tiles/x"}

    box = _tile_box(tile)
    assert box == (16, 8, 24, 16)

    rgba_cell = crop_tile_rgba(sheet, tile)
    binary_cell = crop_tile(binary, tile, save=False)["image"]
    # both crops resolve to the identical rectangle via _tile_box
    assert rgba_cell.tobytes() == sheet.crop(box).tobytes()
    assert binary_cell.tobytes() == binary.crop(box).tobytes()
    assert rgba_cell.size == binary_cell.size


def test_memory_released():
    sheet = _rgba_sheet(16, 8, lambda a: a.__setitem__(
        (1, 9), (10, 20, 30, 255)))
    tile = {"location": (1, 0), "size": (8, 8)}

    cell = crop_tile_rgba(sheet, tile)
    ref = weakref.ref(cell)
    # the crop is never attached to the tile; only the caller holds it
    assert "bitmap" not in tile
    assert "raster_png" not in tile

    del cell
    gc.collect()
    assert ref() is None
