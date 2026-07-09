import os

from minecraft_fontgen.file_io import build_glyph_map, slice_provider_tiles

from helpers import block, make_png_bytes


def _golden_provider():
    """A vanilla-shaped provider: 16-column grid, 8px tiles, height == tile height.

    Tile A (0,0): full 8x8 square. Tile B (1,0): 3px-wide bar, rows 2..5.
    """
    os.makedirs("work/glyphs/golden", exist_ok=True)
    png = make_png_bytes(128, 16, block(0, 0, 8, 8) + block(8, 2, 3, 4))
    with open("work/golden.png", "wb") as f:
        f.write(png)
    rows = ["AB" + "\x00" * 14, "\x00" * 16]
    return {
        "ascent": 7,
        "height": 8,
        "rows": 2,
        "columns": 16,
        "chars": [char for row in rows for char in row],
        "file_name": "golden.png",
        "file_path": "work/golden.png",
        "name": "golden",
        "output": "work/glyphs/golden",
        "layer": "vanilla",
        "tiles": [],
    }


def test_vanilla_slicing_and_scaling_are_pinned():
    provider = _golden_provider()
    slice_provider_tiles([provider])
    glyph_map = build_glyph_map([provider], None)

    a = glyph_map["Regular"][ord("A")]
    assert a["units_per_pixel"] == 128
    assert a["pixels"]["width"] == 8
    assert a["pixels"]["lsb"] == 0
    a_corners = sorted(pt for path in a["scaled"]["outer"] for pt in path)
    assert a_corners == [(0.0, -128.0), (0.0, 896.0), (1024.0, -128.0), (1024.0, 896.0)]

    b = glyph_map["Regular"][ord("B")]
    assert b["pixels"]["width"] == 3
    assert b["pixels"]["lsb"] == 0
    b_corners = sorted(pt for path in b["scaled"]["outer"] for pt in path)
    assert b_corners == [(0.0, 128.0), (0.0, 640.0), (384.0, 128.0), (384.0, 640.0)]

    b_bold = glyph_map["Bold"][ord("B")]
    assert b_bold["pixels"]["width"] == 4


def test_unifont_fallback_scale_is_pinned():
    rows = [[0] * 8 for _ in range(16)]
    for y in range(4, 12):
        for x in range(2, 6):
            rows[y][x] = 1
    glyph_map = build_glyph_map([], {0x00C0: rows})

    tile = glyph_map["Regular"][0x00C0]
    assert tile["source"] == "unifont"
    assert abs(tile["units_per_pixel"] - 896 / 15) < 1e-9


def test_provider_beats_unifont_for_same_codepoint():
    provider = _golden_provider()
    slice_provider_tiles([provider])
    unifont_rows = [[1] * 8 for _ in range(16)]
    glyph_map = build_glyph_map([provider], {ord("A"): unifont_rows, 0x00C0: unifont_rows})

    assert glyph_map["Regular"][ord("A")]["source"] == "provider"
    assert glyph_map["Regular"][0x00C0]["source"] == "unifont"
