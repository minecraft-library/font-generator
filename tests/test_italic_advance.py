from collections import OrderedDict

import numpy as np
from fontTools.ttLib import TTFont

from minecraft_fontgen.file_io import _trace_bitmap_contours2, precompute_glyph_scaling
from minecraft_fontgen.table.glyph_mappings import create_font_mapping_table
from minecraft_fontgen.table.header import create_font_header_table
from minecraft_fontgen.table.horizontal_header import create_font_hheader_table
from minecraft_fontgen.table.horizontal_metrics import create_font_hmetrics_table
from minecraft_fontgen.table.maximum_profile import create_font_mprofile_table
from minecraft_fontgen.table.name import create_font_name_table
from minecraft_fontgen.table.opentype import create_ot_font_tables
from minecraft_fontgen.table.os2_metrics import create_font_metrics_table
from minecraft_fontgen.table.postscript import create_font_pscript_table
from minecraft_fontgen.glyph.glyph_storage import GlyphStorage


def _tile(codepoint, ink_cols, ink_rows, grid=8):
    """A tile whose ink fills the given columns and rows of an 8x8 cell."""
    bitmap = np.zeros((grid, grid), dtype=np.uint8)
    for y in ink_rows:
        for x in ink_cols:
            bitmap[y, x] = 1
    return {
        "unicode": "",
        "codepoint": codepoint,
        "size": (grid, grid),
        "ascent": grid,
        "pixels": _trace_bitmap_contours2(bitmap),
        "svg": None,
        "source": "provider",
    }


def _advance(tile, italic):
    """Stores one glyph into a fresh font and returns the advance it was given."""
    precompute_glyph_scaling({"Regular": OrderedDict({tile["codepoint"]: tile})})

    font = TTFont()
    create_font_header_table(font, True)
    create_font_hheader_table(font, True)
    create_font_mprofile_table(font, True)
    create_font_pscript_table(font, True)
    create_font_hmetrics_table(font)
    create_font_name_table(font, False, italic)
    create_font_metrics_table(font)
    create_font_mapping_table(font)
    create_ot_font_tables(font, False, italic)

    storage = GlyphStorage(font, use_cff=True)
    glyph = storage.create_glyph(tile)
    glyph.scale(italic=italic)
    glyph.draw()
    storage.add(glyph)
    return storage.hmtx[glyph.name][0]


def test_a_shear_does_not_move_the_pen():
    """A sheared glyph advances exactly as its upright self does.

    The game reads one advance per codepoint plus a flag for the weight and applies the slant as it
    draws, so italic text is as wide as upright text and its glyphs lean into one another.
    """
    for name, cols, rows in (
        ("full height", range(5), range(8)),
        ("cap height", range(5), range(1, 7)),
        ("x height", range(5), range(3, 7)),
        ("one pixel", range(1), range(7, 8)),
    ):
        upright = _advance(_tile(0xE000, cols, rows), italic=False)
        sheared = _advance(_tile(0xE000, cols, rows), italic=True)
        assert sheared == upright, f"{name}: sheared {sheared} vs upright {upright}"


def test_a_tall_glyph_is_where_the_shear_reached_furthest():
    """The tallest ink leaned the furthest, so it is where widening the advance cost the most."""
    tall = _tile(0xE000, range(5), range(8))
    short = _tile(0xE001, range(5), range(7, 8))

    # Both are five pixels of ink, so both advance by six pixels whatever their height.
    assert _advance(tall, italic=True) == _advance(short, italic=True)
