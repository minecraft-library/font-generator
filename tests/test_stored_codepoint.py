"""Deterministic stored-codepoint allocation over (font_id, codepoint) pairs, plus a
plane-15 cmap round-trip through a compiled merged font."""
import io

import pytest
from fontTools.ttLib import TTFont

from helpers import build_color_font_storage, compiled_font_bytes, flat_two_color_cell, make_raster_tile
from minecraft_fontgen.config import STORED_CP_START, STORED_CP_END
from minecraft_fontgen.stored_codepoint import (
    allocate_stored_codepoints, plane_budget, _is_noncharacter,
)


def test_allocation_is_linear_from_plane15_in_sorted_order():
    pairs = [("wy:b", 0xE000), ("wy:a", 0xE001), ("wy:a", 0xE000)]
    assignment = allocate_stored_codepoints(pairs)
    assert assignment[("wy:a", 0xE000)] == STORED_CP_START
    assert assignment[("wy:a", 0xE001)] == STORED_CP_START + 1
    assert assignment[("wy:b", 0xE000)] == STORED_CP_START + 2


def test_allocation_is_deterministic_regardless_of_input_order():
    a = allocate_stored_codepoints([("z:z", 1), ("a:a", 2), ("a:a", 1)])
    b = allocate_stored_codepoints([("a:a", 1), ("z:z", 1), ("a:a", 2)])
    assert a == b


def test_allocation_flows_into_plane16_and_skips_noncharacters():
    # Allocation never lands on a U+xFFFE / U+xFFFF noncharacter.
    pairs = [("f", cp) for cp in range(70000)]  # more than one plane's worth
    assignment = allocate_stored_codepoints(pairs)
    values = set(assignment.values())
    assert len(values) == len(pairs)                       # all distinct
    assert max(values) > 0xFFFFF                            # crossed into plane 16
    assert not any(_is_noncharacter(cp) for cp in values)  # no noncharacters
    assert 0xFFFE not in values and 0xFFFF not in values


def test_allocation_across_full_window_skips_all_four_plane_noncharacters():
    # Fill the entire plane-15+16 window so the cursor is forced past BOTH plane
    # ends: U+FFFFE/U+FFFFF (plane 15) and U+10FFFE/U+10FFFF (plane 16). The
    # 70000-pair test above only crosses into plane 16; this one reaches its end,
    # which is the only place the last two noncharacters can ever be hit.
    budget = plane_budget()
    pairs = [("f", cp) for cp in range(budget)]  # sorted key order == cp ascending
    assignment = allocate_stored_codepoints(pairs)

    values = list(assignment.values())
    assert len(values) == budget                      # every pair placed, none dropped
    assert len(set(values)) == budget                 # and all distinct

    four_noncharacters = {0xFFFFE, 0xFFFFF, 0x10FFFE, 0x10FFFF}
    assert four_noncharacters.isdisjoint(values)      # none of the four assigned
    assert min(values) == STORED_CP_START             # starts at U+F0000
    assert max(values) == 0x10FFFD                     # stops just before U+10FFFE

    # Ordering is deterministic and total: the assigned codepoints, in sorted-key
    # order, are exactly the window enumerated with the four noncharacters removed,
    # strictly ascending with no gaps beyond the skips.
    expected = [cp for cp in range(STORED_CP_START, STORED_CP_END + 1)
                if cp not in four_noncharacters]
    assert [assignment[("f", cp)] for cp in range(budget)] == expected
    assert allocate_stored_codepoints(pairs) == assignment  # stable across runs


def test_noncharacter_predicate():
    assert _is_noncharacter(0xFFFE)
    assert _is_noncharacter(0xFFFF)
    assert _is_noncharacter(0x10FFFE)
    assert _is_noncharacter(0x10FFFF)
    assert not _is_noncharacter(0xF0000)
    assert not _is_noncharacter(0x100000)


def test_plane_budget_is_131068():
    # planes 15 + 16 = 131072 codepoints, minus 4 noncharacters
    assert plane_budget() == 131068


def test_budget_exhaustion_raises():
    # A fake pair set larger than the budget must raise (never silently truncate).
    class _Huge:
        def __iter__(self):
            for cp in range(plane_budget() + 1):
                yield ("f", cp)
    with pytest.raises(ValueError, match="budget exhausted"):
        allocate_stored_codepoints(_Huge())


def test_plane15_cmap_roundtrip_through_compiled_font():
    # A stored codepoint in plane 15 survives compile -> reopen: present in the
    # format-12 subtable, absent from format-4, and resolves to its glyph.
    storage = build_color_font_storage([
        make_raster_tile(0xE001, flat_two_color_cell(8, 8), 8, 7, font_id="wy:a"),
    ])
    stored_cp = storage.sidecar_rows[0]["stored_codepoint"]
    assert STORED_CP_START <= stored_cp <= STORED_CP_END

    reopened = TTFont(io.BytesIO(compiled_font_bytes(storage)))
    # present in the SMP (format 12) subtable
    fmt12 = [t for t in reopened["cmap"].tables if t.format == 12]
    assert fmt12 and stored_cp in fmt12[0].cmap
    # absent from the BMP (format 4) subtable (stored codepoints are all > U+FFFF)
    for t in reopened["cmap"].tables:
        if t.format == 4:
            assert stored_cp not in t.cmap
    # resolves to a real glyph with an sbix strike
    name = reopened.getBestCmap()[stored_cp]
    assert any(name in strike.glyphs for strike in reopened["sbix"].strikes.values())
