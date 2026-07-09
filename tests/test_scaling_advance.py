from collections import OrderedDict

import numpy as np

from minecraft_fontgen.file_io import _trace_bitmap_contours2, precompute_glyph_scaling
from minecraft_fontgen.glyph.glyph import Glyph


def _tile(grid_rows, grid_cols, ink_cols, ink_rows, display_height, ascent, source="provider"):
    grid = np.zeros((grid_rows, grid_cols), dtype=np.uint8)
    for y in ink_rows:
        for x in ink_cols:
            grid[y, x] = 1
    tile = {
        "unicode": "",
        "codepoint": 0xE000,
        "size": (grid_cols, grid_rows),
        "ascent": ascent,
        "pixels": _trace_bitmap_contours2(grid),
        "svg": None,
        "source": source,
    }
    if display_height is not None:
        tile["display_height"] = display_height
    return tile


def _scaled(tile):
    precompute_glyph_scaling({"Regular": OrderedDict({tile["codepoint"]: tile})})
    return tile


def _top_y(tile):
    return max(y for path in tile["scaled"]["outer"] for _x, y in path)


def test_one_to_one_tiles_match_legacy_math():
    tile = _scaled(_tile(7, 7, range(3), range(7), display_height=7, ascent=7))
    assert tile["units_per_pixel"] == 128
    assert _top_y(tile) == 896.0
    assert tile["advance_units"] == 512  # (floor(0.5 + 3) + 1) * 128


def test_hd_tiles_scale_down():
    tile = _scaled(_tile(14, 12, range(6), range(14), display_height=7, ascent=7))
    assert tile["units_per_pixel"] == 64
    assert _top_y(tile) == 896.0
    assert tile["advance_units"] == 512  # (floor(0.5 + 6 * 0.5) + 1) * 128


def test_vanilla_shaped_2x_tile_scales_down():
    tile = _scaled(_tile(16, 16, range(6), range(16), display_height=8, ascent=7))
    assert tile["units_per_pixel"] == 64
    assert _top_y(tile) == 896.0
    assert tile["advance_units"] == 512  # (floor(0.5 + 6 * 0.5) + 1) * 128


def test_zero_ascent_sits_on_baseline():
    tile = _scaled(_tile(8, 8, range(2), range(8), display_height=8, ascent=0))
    assert _top_y(tile) == 0.0


def test_negative_ascent_hangs_below_baseline():
    tile = _scaled(_tile(8, 8, range(2), range(8), display_height=8, ascent=-2))
    assert _top_y(tile) == -256.0


def test_empty_tile_gets_one_display_pixel_advance():
    tile = _scaled(_tile(7, 3, [], [], display_height=7, ascent=7))
    assert tile["pixels"]["empty"] is True
    assert tile["advance_units"] == 128
    assert tile["scaled"] == {"outer": [], "holes": []}


def test_unifont_tiles_keep_legacy_scale_and_no_advance_units():
    tile = _scaled(_tile(16, 8, range(4), range(16), display_height=None, ascent=15, source="unifont"))
    assert abs(tile["units_per_pixel"] - 896 / 15) < 1e-9
    assert "advance_units" not in tile


def test_glyph_prefers_advance_units():
    tile = _scaled(_tile(7, 7, range(3), range(7), display_height=7, ascent=7))
    glyph = Glyph(tile, use_cff=True)
    assert glyph.advance_units == 512

    unifont_tile = _scaled(_tile(16, 8, range(4), range(16), display_height=None, ascent=15, source="unifont"))
    assert Glyph(unifont_tile, use_cff=True).advance_units is None
