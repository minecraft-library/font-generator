import os
from fractions import Fraction

from minecraft_fontgen.config import SNAP_COARSE_PPEM, SNAP_EDGE_MARGIN
from minecraft_fontgen.file_io import _seam_bridges, _snap_edge, build_glyph_map, slice_provider_tiles

from helpers import (CELL_BANG, CELL_DELTA, CELL_DOLLAR, CELL_EM_DASH, CELL_FULL, CELL_O, CELL_QUOTE, CELL_SHHA,
                     block, client_coverage, column_gaps, first_ink_column, fragile_centres, glyph_contours, ink_grid,
                     make_png_bytes, outline_coverage, scanline_gaps, stored_advance)


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

    # Bold draws Regular's pixels twice, one GUI pixel apart, each on the client's quad: the whole cell
    # thickened by 0.1 pixel (12.8 units) on every side, its texels inset 0.01. Columns 0-3 and rows 2-6
    # of the cell land at -12.8 + 1049.6 * (u - 0.01) / 7.98 and 908.8 - 1049.6 * (v - 0.01) / 7.98.
    b_bold = glyph_map["Bold"][ord("B")]
    assert b_bold["pixels"]["width"] == 3
    copy_0, copy_1 = b_bold["scaled"]["copies"]
    corners_0 = sorted((round(x, 2), round(y, 2)) for path in copy_0["outer"] for x, y in path)
    assert corners_0 == [(-12.8, 120.94), (-12.8, 647.06), (380.47, 120.94), (380.47, 647.06)]
    corners_1 = sorted((round(x - 128, 2), round(y, 2)) for path in copy_1["outer"] for x, y in path)
    assert corners_1 == corners_0


def test_unifont_fallback_scale_is_pinned():
    rows = [[0] * 8 for _ in range(16)]
    for y in range(4, 12):
        for x in range(2, 6):
            rows[y][x] = 1
    glyph_map = build_glyph_map([], {0x00C0: rows})

    tile = glyph_map["Regular"][0x00C0]
    assert tile["source"] == "unifont"
    assert abs(tile["units_per_pixel"] - 896 / 15) < 1e-9


def test_a_unifont_bold_entry_is_two_copies_half_a_pixel_apart():
    """build_glyph_map marks every unifont fallback's Bold entry, and only it, to draw the client's two
    copies, which advance half a GUI pixel (64 units) further than Regular."""
    rows = [[0] * 8 for _ in range(16)]
    for y in range(4, 12):
        for x in range(2, 6):
            rows[y][x] = 1
    glyph_map = build_glyph_map([], {0x00C0: rows})

    regular, bold = glyph_map["Regular"][0x00C0], glyph_map["Bold"][0x00C0]
    assert not regular["bold_copies"] and "copies" not in regular["scaled"]
    assert bold["bold_copies"] and len(bold["scaled"]["copies"]) == 2
    assert stored_advance(bold) == stored_advance(regular) + 64


def test_provider_beats_unifont_for_same_codepoint():
    provider = _golden_provider()
    slice_provider_tiles([provider])
    unifont_rows = [[1] * 8 for _ in range(16)]
    glyph_map = build_glyph_map([provider], {ord("A"): unifont_rows, 0x00C0: unifont_rows})

    assert glyph_map["Regular"][ord("A")]["source"] == "provider"
    assert glyph_map["Regular"][0x00C0]["source"] == "unifont"


_BOLD_CELLS = (
    ("A", CELL_FULL),
    ("B", ["........", "........", "###.....", "###.....", "###.....", "###.....", "........", "........"]),
    ("o", CELL_O),
    ("—", CELL_EM_DASH),
    ("һ", CELL_SHHA),
    ("Δ", CELL_DELTA),
    ('"', CELL_QUOTE),
    ("!", CELL_BANG),
    ("$", CELL_DOLLAR),
)


def _bold_provider():
    """A vanilla-shaped provider holding the _BOLD_CELLS in one row of 8x8 tiles."""
    os.makedirs("work/glyphs/bold_cells", exist_ok=True)
    pixels = [(8 * k + x, y) for k, (_, rows) in enumerate(_BOLD_CELLS)
              for y, row in enumerate(rows) for x, c in enumerate(row) if c == "#"]
    with open("work/bold_cells.png", "wb") as f:
        f.write(make_png_bytes(128, 8, pixels))
    return {
        "ascent": 7,
        "height": 8,
        "rows": 1,
        "columns": 16,
        "chars": [char for char, _ in _BOLD_CELLS] + ["\x00"] * (16 - len(_BOLD_CELLS)),
        "file_name": "bold_cells.png",
        "file_path": "work/bold_cells.png",
        "name": "bold_cells",
        "output": "work/glyphs/bold_cells",
        "layer": "vanilla",
        "tiles": [],
    }


def _bold_glyph_map():
    """The _BOLD_CELLS sliced and built into a glyph map."""
    provider = _bold_provider()
    slice_provider_tiles([provider])
    return build_glyph_map([provider], None)


def test_bold_faces_cover_what_the_client_draws():
    """At every GUI scale up to 4, the Bold face covers exactly the pixel centres the client's two
    thickened quads sample ink at, and BoldItalic exactly those of the two slanted ones - including the
    texel edges of U+04BB and U+0394 that sit 0.03 font units from a pixel centre, which a vertex rounded
    to the nearest unit moves across.

    From 24 px/em (GUI scale 3) FreeType places the crossing of a slanted edge with a pixel row only to
    within a 64th of a pixel or so, so there no edge of either face may pass nearer a pixel centre than
    SNAP_EDGE_MARGIN output pixels: '!' and '$' each had a BoldItalic edge a few hundredths of a unit
    from one."""
    glyph_map = _bold_glyph_map()

    for char, rows in _BOLD_CELLS:
        tile = glyph_map["Bold"][ord(char)]
        for italic in (False, True):
            contours = glyph_contours(tile, italic=italic)
            face = "BoldItalic" if italic else "Bold"
            for gui_scale in (1, 2, 3, 4):
                trim = first_ink_column(rows) * gui_scale
                drawn = {(i + trim, j) for i, j in outline_coverage(contours, gui_scale)}
                wanted = client_coverage(ink_grid(rows), 7, 8, bold=True, italic=italic, gui_scale=gui_scale)
                assert drawn == wanted, f"{face} U+{ord(char):04X} at GUI scale {gui_scale}: " \
                                        f"outline only {sorted(drawn - wanted)}, client only {sorted(wanted - drawn)}"
                if 8 * gui_scale >= SNAP_COARSE_PPEM:
                    margin = Fraction(SNAP_EDGE_MARGIN) * Fraction(128, gui_scale)
                    fragile = fragile_centres(contours, gui_scale, margin)
                    assert not fragile, f"{face} U+{ord(char):04X} at GUI scale {gui_scale}: an edge passes " \
                                        f"within {SNAP_EDGE_MARGIN} px of centres {sorted(fragile)}"


def test_the_bold_copies_leave_no_hairline_between_them():
    """Where a row of ink has a one-texel hole, the second bold copy fills all but a sliver of it: 3.5 units
    of an 8x8 cell, under 3% of a GUI pixel. Antialiasing renderers draw such a sliver as a hairline seam,
    so the Bold face closes every one no pixel centre at GUI scales 1-4 falls in - each in these cells:
    along the middle of every texel row, any stretch the outline leaves unfilled between filled ones is at
    least an eighth of a GUI pixel wide."""
    glyph_map = _bold_glyph_map()

    for char, rows in _BOLD_CELLS:
        contours = glyph_contours(glyph_map["Bold"][ord(char)])
        for r in range(len(rows)):
            narrow = [gap for gap in scanline_gaps(contours, (6.5 - r) * 128) if gap < 16]
            assert not narrow, f"Bold U+{ord(char):04X} row {r}: unfilled slivers {narrow} units wide"


def test_the_bold_copies_meet_where_rows_meet():
    """Where two texels touch only at a corner, the other bold copy's ink runs along the row boundary through
    that corner, as the client draws it. Insetting the corner, as Regular's shared vertices are, would open a
    wedge there that an antialiasing renderer draws as a seam: down every vertical line through the glyph,
    any stretch the Bold outline leaves unfilled between filled ones is at least an eighth of a GUI pixel."""
    glyph_map = _bold_glyph_map()

    for char, rows in _BOLD_CELLS:
        contours = glyph_contours(glyph_map["Bold"][ord(char)])
        xs = [x for contour in contours for x, _ in contour]
        for x in range(min(xs), max(xs), 2):
            narrow = [gap for gap in column_gaps(contours, x + 0.5) if gap < 16]
            assert not narrow, f"Bold U+{ord(char):04X} at x {x + 0.5}: unfilled slivers {narrow} units tall"


def test_a_sliver_stays_open_where_the_client_samples_a_pixel_centre():
    """A gap between two runs narrower than BOLD_SEAM_MAX_UNITS is bridged unless a pixel centre at a GUI
    scale in SNAP_GUI_SCALES lies in it, as the client leaves that pixel unlit; a wider gap stays. Each
    row here runs from y 0 to 128, a run ending at the gap's left side and another starting at its right;
    the centres sit at x = 16 + 32k at GUI scale 4, and none falls between 245 and 249 at any scale."""
    def row(gap_left, gap_right):
        return [(128, 0, [((-200, -200), (gap_left, gap_left)), ((gap_right, gap_right), (500, 500))])]

    assert _seam_bridges(row(245, 249)) == [[(245, 128), (245, 0), (249, 0), (249, 128)]]
    assert _seam_bridges(row(238, 242)) == []  # 240 is a centre at GUI scale 4
    assert _seam_bridges(row(100, 120)) == []  # 20 units: a gap the client draws at every scale


def test_a_centre_on_a_written_edge_is_inside_the_run():
    """FreeType lights a pixel whose centre lies exactly on an edge, left or right, so a BoldItalic edge
    whose nearest whole unit runs through a centre the client samples inside the run is written there;
    it would otherwise move a unit out. At GUI scale 2 the centres sit at 32 + 64k units."""
    pitches = [(Fraction(64), 0)]
    left = _snap_edge(Fraction(319, 10), Fraction(0), Fraction(64), Fraction(0), 64, 0, True, pitches)
    right = _snap_edge(Fraction(321, 10), Fraction(0), Fraction(64), Fraction(0), 64, 0, False, pitches)
    assert (left, right) == ((32, 32), (32, 32))
