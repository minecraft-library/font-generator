from collections import OrderedDict

import numpy as np
import pytest

from minecraft_fontgen.file_io import _trace_bitmap_contours2, precompute_glyph_scaling
from minecraft_fontgen.glyph.glyph import Glyph

from helpers import charstring_width, stored_advance


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


def _diagonal_tile():
    """Two diagonally-touching pixels: their contours share a corner vertex."""
    grid = np.zeros((8, 8), dtype=np.uint8)
    grid[0, 0] = 1
    grid[1, 1] = 1
    return {
        "unicode": "",
        "codepoint": 0xE000,
        "size": (8, 8),
        "ascent": 7,
        "display_height": 8,
        "pixels": _trace_bitmap_contours2(grid),
        "svg": None,
        "source": "provider",
    }


def _contour_vertex_sets(tile):
    contours = tile["scaled"]["outer"] + tile["scaled"]["holes"]
    return [{(round(x), round(y)) for x, y in c} for c in contours]


def test_inset_enabled_breaks_shared_vertices():
    tile = _diagonal_tile()
    precompute_glyph_scaling({"Regular": OrderedDict({tile["codepoint"]: tile})})
    sets = _contour_vertex_sets(tile)
    assert len(sets) == 2
    assert not (sets[0] & sets[1])


def test_inset_disabled_keeps_shared_vertices():
    tile = _diagonal_tile()
    precompute_glyph_scaling({"Regular": OrderedDict({tile["codepoint"]: tile})},
                             inset_vertices=False)
    sets = _contour_vertex_sets(tile)
    assert len(sets) == 2
    assert sets[0] & sets[1]


def test_glyph_prefers_advance_units():
    tile = _scaled(_tile(7, 7, range(3), range(7), display_height=7, ascent=7))
    glyph = Glyph(tile, use_cff=True)
    assert glyph.advance_units == 512

    unifont_tile = _scaled(_tile(16, 8, range(4), range(16), display_height=None, ascent=15, source="unifont"))
    assert Glyph(unifont_tile, use_cff=True).advance_units is None


def _bold(tile):
    """Marks a tile as a Bold-style entry, drawn as the client's two bold copies."""
    tile["bold_copies"] = True
    return tile


def test_bold_adds_one_pixel_to_a_bitmap_advance():
    """The client advances a bold glyph by its advance plus getBoldOffset(), one GUI pixel for a bitmap
    glyph - a glyph inked to its cell's last column included."""
    regular = _scaled(_tile(7, 7, range(7), range(7), display_height=7, ascent=7))
    bold = _scaled(_bold(_tile(7, 7, range(7), range(7), display_height=7, ascent=7)))
    assert regular["advance_units"] == 1024  # (7 + 1) * 128
    assert bold["advance_units"] == 1152


def test_bold_adds_half_a_pixel_to_a_unifont_advance():
    """A unihex glyph's bold offset is half a GUI pixel, 64 units on top of Regular's advance."""
    bold = _scaled(_bold(_tile(16, 8, range(4), range(16), display_height=None, ascent=15, source="unifont")))
    assert bold["advance_units"] == round(5 * 896 / 15) + 64


def test_a_high_resolution_bold_copy_sits_one_display_pixel_right():
    """The second bold copy is drawn one GUI pixel right of the first: 128 units, which is two texels of a
    14x12 tile displayed 7 pixels tall, not one."""
    tile = _scaled(_bold(_tile(14, 12, range(6), range(14), display_height=7, ascent=7)))
    copy_0, copy_1 = tile["scaled"]["copies"]
    moved = [[(round(x + 128, 9), round(y, 9)) for x, y in path] for path in copy_0["outer"]]
    assert moved == [[(round(x, 9), round(y, 9)) for x, y in path] for path in copy_1["outer"]]


def test_a_unifont_bold_quad_spans_its_ink():
    """The client cuts a unihex glyph's quad to its ink columns, so a bold copy thickens the ink by 0.1
    GUI pixel (12.8 units) on each side, wherever in its 8-column cell the ink sits."""
    tile = _scaled(_bold(_tile(16, 8, range(2, 6), range(16), display_height=None, ascent=15, source="unifont")))
    copy_0, copy_1 = tile["scaled"]["copies"]
    xs = [x for path in copy_0["outer"] for x, _ in path]
    assert min(xs) == pytest.approx(-12.8)
    assert max(xs) == pytest.approx(4 * 896 / 15 + 12.8)

    # The second copy is the first moved the unihex bold offset, half a GUI pixel: 64 units.
    moved = [[(round(x + 64, 9), round(y, 9)) for x, y in path] for path in copy_0["outer"]]
    assert moved == [[(round(x, 9), round(y, 9)) for x, y in path] for path in copy_1["outer"]]


def test_a_unifont_bold_italic_copy_sits_half_a_pixel_right():
    """BoldItalic lays a unifont glyph's runs once per copy, the second set 64 units right of the first: the
    two copies' runs differ only where snapping a vertex to a whole unit chose differently, which moves
    each vertex less than three units from where the client's quad puts it."""
    tile = _scaled(_bold(_tile(16, 8, range(2, 6), range(16), display_height=None, ascent=15, source="unifont")))
    runs = tile["scaled"]["runs"]
    copy_0, copy_1 = runs[:len(runs) // 2], runs[len(runs) // 2:]
    assert len(copy_0) == len(copy_1) == 16
    for run_0, run_1 in zip(copy_0, copy_1):
        for (x0, y0), (x1, y1) in zip(run_0, run_1):
            assert y1 == y0 and abs(x1 - x0 - 64) < 6


def _space(bold, source="provider"):
    """A scaled U+0020 tile, inkless, from a bitmap provider or from unifont."""
    if source == "unifont":
        tile = _tile(16, 8, [], [], display_height=None, ascent=15, source="unifont")
    else:
        tile = _tile(8, 8, [], [], display_height=8, ascent=7)
    tile["unicode"], tile["codepoint"] = " ", 0x20
    return _scaled(_bold(tile) if bold else tile)


def test_bold_space_advances_five_pixels():
    """The client's space is four GUI pixels wide; bold adds its one-pixel offset as it does to any glyph.
    The generator draws every U+0020 as the space provider's space, so a space it took from unifont
    advances so too. The hmtx advance and the width written into the charstring agree."""
    for source in ("provider", "unifont"):
        for bold, advance in ((False, 512), (True, 640)):
            tile = _space(bold, source)
            assert stored_advance(tile) == advance, (source, bold)
            assert charstring_width(tile) == advance, (source, bold)
