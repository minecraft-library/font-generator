import hashlib
import io
import os

import numpy as np
from PIL import Image, PngImagePlugin

import minecraft_fontgen.file_io as file_io
from minecraft_fontgen.file_io import (
    classify_render_mode,
    encode_cell_png,
    normalized_cell_bytes,
    raster_cell_hash,
    slice_provider_tiles,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _solid(width, height, color):
    arr = np.zeros((height, width, 4), np.uint8)
    arr[:, :] = color
    return Image.fromarray(arr, "RGBA")


def _cell(width, height, spec):
    """Lays out (count, color) runs row-major over a width*height canvas; any
    remaining pixels stay fully transparent."""
    arr = np.zeros((height * width, 4), np.uint8)
    i = 0
    for count, color in spec:
        arr[i:i + count] = color
        i += count
    return Image.fromarray(arr.reshape(height, width, 4), "RGBA")


def _distinct_opaque_colors(cell):
    arr = np.asarray(cell)
    opaque = arr[arr[:, :, 3] == 255]
    return {tuple(px[:3]) for px in opaque}


def _png_chunk_types(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    types = []
    i = 8
    while i < len(data):
        length = int.from_bytes(data[i:i + 4], "big")
        types.append(data[i + 4:i + 8].decode("ascii"))
        i += 12 + length
    return types


# ---------------------------------------------------------------------------
# classifier truth table
# ---------------------------------------------------------------------------

def test_classify_truth_table():
    transparent = _solid(8, 8, (0, 0, 0, 0))
    white_pill = _cell(8, 8, [(20, (255, 255, 255, 255))])
    single_colour = _solid(8, 8, (200, 40, 40, 255))
    two_colour = _cell(8, 8, [(32, (220, 40, 40, 255)), (32, (40, 60, 220, 255))])
    huge_single = _solid(256, 256, (255, 255, 255, 255))
    antialiased = _cell(8, 8, [(32, (220, 40, 40, 255)), (32, (40, 60, 220, 128))])

    # a socket with twelve flat, significant opaque colours and no anti-aliasing
    socket = _cell(16, 16, [(20, (i * 20, 0, 0, 255)) for i in range(12)])

    # an emblem carrying 83 distinct opaque colours: two dominant flat regions
    # plus 81 single-pixel accents (only the dominant pair are significant)
    emblem_arr = np.zeros((40, 40, 4), np.uint8)
    emblem_arr[:, :20] = (30, 180, 60, 255)
    emblem_arr[:, 20:] = (200, 120, 30, 255)
    for i in range(81):
        emblem_arr[i // 40, i % 40] = (i + 1, 250 - i, (i * 3) % 200, 255)
    emblem = Image.fromarray(emblem_arr, "RGBA")

    assert classify_render_mode(transparent) == "mono"
    assert classify_render_mode(white_pill) == "mono"
    assert classify_render_mode(single_colour) == "mono"
    assert classify_render_mode(two_colour) == "raster"
    assert classify_render_mode(huge_single) == "raster"
    assert classify_render_mode(antialiased) == "raster"
    assert classify_render_mode(socket) == "raster"
    assert classify_render_mode(emblem) == "raster"

    # the fixtures genuinely carry the colour counts their names claim
    assert len(_distinct_opaque_colors(socket)) == 12
    assert len(_distinct_opaque_colors(emblem)) == 83


def test_classify_thresholds_config_driven(monkeypatch):
    # a flat two-colour cell is raster by default (two significant colours)
    two_colour = _cell(8, 8, [(32, (220, 40, 40, 255)), (32, (40, 60, 220, 255))])
    assert classify_render_mode(two_colour) == "raster"

    # raising the significant-colour requirement flips the same cell to mono
    monkeypatch.setattr(file_io, "COLOR_CLASSIFY_MIN_SIG_COLORS", 3)
    assert classify_render_mode(two_colour) == "mono"

    # a near-uniform cell with a single anti-aliased fringe pixel is mono by default
    fringe = _cell(8, 8, [(63, (200, 40, 40, 255)), (1, (200, 40, 40, 128))])
    assert classify_render_mode(fringe) == "mono"

    # lowering the dimension gate makes even this small cell raster
    monkeypatch.setattr(file_io, "COLOR_CLASSIFY_MAX_MONO_DIM", 4)
    assert classify_render_mode(fringe) == "raster"


# ---------------------------------------------------------------------------
# deterministic encode
# ---------------------------------------------------------------------------

def test_encode_determinism():
    cell = _cell(8, 8, [(32, (220, 40, 40, 255)), (32, (40, 60, 220, 255))])

    # two encodes of the same cell are byte-identical
    assert encode_cell_png(cell) == encode_cell_png(cell)

    # a cell decoded from a source carrying icc/dpi/tEXt encodes to the same
    # bytes as the clean pixels: the reconstruct-from-array drops all metadata
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "from a busy pack export")
    buffer = io.BytesIO()
    cell.save(buffer, "PNG", dpi=(300, 300), pnginfo=info)
    reopened = Image.open(io.BytesIO(buffer.getvalue()))
    assert reopened.info  # the source really does carry ancillary metadata

    clean = Image.fromarray(np.asarray(cell.convert("RGBA")), "RGBA")
    assert encode_cell_png(reopened) == encode_cell_png(clean)


def test_encode_no_ancillary_chunks():
    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "noise")
    buffer = io.BytesIO()
    _cell(8, 8, [(64, (10, 20, 30, 255))]).save(buffer, "PNG", dpi=(72, 72), pnginfo=info)
    reopened = Image.open(io.BytesIO(buffer.getvalue()))

    chunks = _png_chunk_types(encode_cell_png(reopened))
    assert chunks[0] == "IHDR"
    assert chunks[-1] == "IEND"
    assert set(chunks) <= {"IHDR", "IDAT", "IEND"}


# ---------------------------------------------------------------------------
# canonicalization + content hash
# ---------------------------------------------------------------------------

def test_transparent_rgb_canonicalized():
    # identical alpha, different RGB hidden under fully transparent pixels
    a = _cell(8, 8, [(32, (220, 40, 40, 255)), (32, (11, 22, 33, 0))])
    b = _cell(8, 8, [(32, (220, 40, 40, 255)), (32, (250, 200, 150, 0))])

    # the invisible RGB difference collapses in both the hash and the bytes
    assert raster_cell_hash(a) == raster_cell_hash(b)
    assert encode_cell_png(a) == encode_cell_png(b)
    assert normalized_cell_bytes(a) == normalized_cell_bytes(b)


def test_dedup_hash_on_normalized_not_png():
    cell = _cell(8, 8, [(20, (30, 180, 60, 255)), (20, (200, 120, 30, 255))])

    # the content hash is taken over the normalized RGBA bytes, not the PNG bytes
    assert raster_cell_hash(cell) == hashlib.sha256(normalized_cell_bytes(cell)).hexdigest()
    assert raster_cell_hash(cell) != hashlib.sha256(encode_cell_png(cell)).hexdigest()

    # the digest input folds in the dimensions so a byte-prefix clash can't collide
    assert normalized_cell_bytes(cell).startswith(b"\x00\x00\x00\x08\x00\x00\x00\x08")


# ---------------------------------------------------------------------------
# slice raster branch
# ---------------------------------------------------------------------------

def _raster_provider(sheet):
    os.makedirs("work/glyphs/slice/tiles", exist_ok=True)
    path = "work/slice.png"
    sheet.save(path, "PNG")
    return {
        "file_path": path,
        "name": "slice",
        "output": "work/glyphs/slice",
        "file_name": "slice.png",
        "columns": 2,
        "rows": 1,
        "height": 8,
        "ascent": 7,
        "layer": "pack",
        "chars": ["A", "B"],
    }


def test_slice_raster_branch_stamps_tile():
    # left cell: flat two-colour icon (raster); right cell: single-colour (mono)
    arr = np.zeros((8, 16, 4), np.uint8)
    arr[:, 0:4] = (220, 40, 40, 255)
    arr[:, 4:8] = (40, 60, 220, 255)
    arr[:, 8:16] = (200, 200, 200, 255)
    provider = _raster_provider(Image.fromarray(arr, "RGBA"))

    slice_provider_tiles([provider], color_mode=True)
    tiles = {t["codepoint"]: t for t in provider["tiles"]}
    raster = tiles[ord("A")]
    mono = tiles[ord("B")]

    # the raster cell carries the flat raster fields and skips the trace entirely
    assert raster["render_mode"] == "raster"
    assert raster["raster_size"] == (8, 8)
    assert raster["content_hash"] == raster_cell_hash(
        Image.fromarray(arr[:, 0:8], "RGBA"))
    assert raster["raster_png"] == encode_cell_png(Image.fromarray(arr[:, 0:8], "RGBA"))
    assert "pixels" not in raster

    # the mono cell falls through to the outline path unchanged
    assert mono["render_mode"] == "mono"
    assert "pixels" in mono


def test_slice_mono_path_untouched_without_color_mode():
    arr = np.zeros((8, 16, 4), np.uint8)
    arr[:, 0:4] = (220, 40, 40, 255)
    arr[:, 4:8] = (40, 60, 220, 255)
    provider = _raster_provider(Image.fromarray(arr, "RGBA"))

    slice_provider_tiles([provider])  # color_mode defaults False

    for tile in provider["tiles"]:
        # the mono path never classifies or stamps raster fields
        assert "render_mode" not in tile
        assert "raster_png" not in tile
        assert "pixels" in tile
