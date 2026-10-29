from fractions import Fraction

import numpy as np

from minecraft_fontgen.config import SNAP_COARSE_PPEM, SNAP_EDGE_MARGIN
from minecraft_fontgen.file_io import _trace_bitmap_contours2
from minecraft_fontgen.glyph.glyph import Glyph

from helpers import (CELL_A_GRAVE, CELL_DIAGONAL, CELL_EM_DASH, CELL_FULL, CELL_O, bitmap_tile, client_coverage,
                     first_ink_column, fragile_centres, glyph_contours, ink_grid, outline_coverage, scaled,
                     stored_advance, unifont_tile)


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
    return stored_advance(scaled(tile), italic)


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


def _comb(width, rows, inked_rows):
    """A cell of `rows` rows whose given rows hold five pixels of ink each and touch nothing."""
    return [("#####" + "." * (width - 5)) if r in inked_rows else "." * width for r in range(rows)]


def test_the_slant_is_a_quarter_pixel_per_pixel_about_384_units():
    """The client shifts each row of an italic glyph by 1 - y / 4 GUI pixels, y its depth below the line
    top, which sits 7 pixels above the baseline: a quarter of a pixel per pixel of height, and nothing 3
    pixels above the baseline. In font units that is x + (y - 384) / 4, whatever cell the glyph came
    from, because the shift depends only on where a point is drawn."""
    for name, tile in (
        ("ascii cell", bitmap_tile(_comb(8, 8, (1, 3, 5, 7)))),
        ("accented cell", bitmap_tile(_comb(9, 12, (0, 2, 4, 6, 8, 10)), ascent=10)),
        ("unifont cell", unifont_tile(_comb(8, 16, range(1, 16, 2)))),
    ):
        scaled(tile)
        upright, italic = Glyph(tile), Glyph(tile)
        upright.scale(italic=False)
        italic.scale(italic=True)
        unsheared = {(round(x - (y - 384) / 4, 6), round(y, 6))
                     for contour in italic.outer_scaled + italic.holes_scaled for x, y in contour}
        assert unsheared == {(round(x, 6), round(y, 6))
                             for contour in upright.outer_scaled + upright.holes_scaled for x, y in contour}, name


def test_an_italic_glyph_covers_what_the_client_samples():
    """At every GUI scale up to 4, the Italic face's outline covers exactly the pixel centres the client's
    slanted quad samples ink at, once the generator's left-padding trim is put back - and from 24 px/em,
    where FreeType places an edge's crossing of a pixel row only to about a 64th of a pixel, no edge
    passes nearer a pixel centre than SNAP_EDGE_MARGIN output pixels."""
    for name, rows, ascent in (
        ("full cell", CELL_FULL, 7),
        ("o", CELL_O, 7),
        ("one-pixel diagonal", CELL_DIAGONAL, 7),
        ("ink in the last column", CELL_EM_DASH, 7),
        ("accented cell", CELL_A_GRAVE, 10),
    ):
        contours = glyph_contours(scaled(bitmap_tile(rows, ascent=ascent)), italic=True)
        for gui_scale in (1, 2, 3, 4):
            trim = first_ink_column(rows) * gui_scale
            drawn = {(i + trim, j) for i, j in outline_coverage(contours, gui_scale)}
            wanted = client_coverage(ink_grid(rows), ascent, len(rows), italic=True, gui_scale=gui_scale)
            assert drawn == wanted, f"{name} at GUI scale {gui_scale}: outline only {sorted(drawn - wanted)}, " \
                                    f"client only {sorted(wanted - drawn)}"
            if 8 * gui_scale >= SNAP_COARSE_PPEM:
                margin = Fraction(SNAP_EDGE_MARGIN) * Fraction(128, gui_scale)
                assert not fragile_centres(contours, gui_scale, margin), f"{name} at GUI scale {gui_scale}"


def _winding(contours, px, py):
    """Nonzero winding number of the contours at a point, by a ray cast towards +x."""
    winding = 0
    for contour in contours:
        for k, (x0, y0) in enumerate(contour):
            x1, y1 = contour[(k + 1) % len(contour)]
            if (y0 <= py < y1 or y1 <= py < y0) and x0 + (py - y0) * (x1 - x0) / (y1 - y0) > px:
                winding += 1 if y1 > y0 else -1
    return winding


def test_a_diagonal_pinch_is_a_gap_not_a_bridge():
    """Where two ink texels of 'o' touch only at a corner - texel corner (1, 3), font point (128, 512),
    slanted to (160, 512) - the client samples nothing between them, and neither may the outline.

    The slant puts that corner on a pixel-centre column at 16 px/em. A traced outline joins the ring and
    its counter there, and a rasterizer with dropout control fills a counter pixel across the join; the
    Italic face must leave a gap the corner's two sides do not span."""
    contours = glyph_contours(scaled(bitmap_tile(CELL_O)), italic=True)
    assert _winding(contours, 160, 512) == 0


def test_stacked_runs_meet_along_the_edge_they_share():
    """The client's slanted quad has no gap between texel rows, so where a run of ink sits on a run in the
    row below, the Italic outline covers the boundary between them - half a unit above it and half a
    unit below, under every column both rows ink. Only a corner where two runs touch diagonally is
    inset, and an antialiasing renderer draws any other inset as a seam across the glyph."""
    for name, rows, ascent in (
        ("full cell", CELL_FULL, 7),
        ("o", CELL_O, 7),
        ("accented cell", CELL_A_GRAVE, 10),
    ):
        contours = glyph_contours(scaled(bitmap_tile(rows, ascent=ascent)), italic=True)
        ink, trim = ink_grid(rows), first_ink_column(rows)
        for r in range(len(rows) - 1):
            for c in range(len(rows[0])):
                if not (ink[r][c] and ink[r + 1][c]):
                    continue
                boundary = (ascent - r - 1) * 128
                for y in (boundary - 0.5, boundary + 0.5):
                    x = (c + 0.5 - trim) * 128 + (y - 384) / 4
                    assert _winding(contours, x, y) != 0, f"{name}: a gap between rows {r} and {r + 1}, column {c}"
