"""M6: per-pack colour compilation. One merged sbix TrueType per source pack, stored
codepoints allocated over the (font_id, original_codepoint) pairs, pack-wide content
dedup, and the Regular-only colour emission that rides the shared create_font_files
loop without the mono four-style fan-out."""
import os

import pytest
from fontTools.ttLib import TTFont

from helpers import build_one_color_font, color_cell, flat_two_color_cell, make_raster_tile
from minecraft_fontgen.config import OUTPUT_FONT_NAME, STORED_CP_START
from minecraft_fontgen.file_io import build_color_glyph_map, group_color_space_rows
from minecraft_fontgen.font_creator import create_font_files

MERGED_NAME = f"{OUTPUT_FONT_NAME}-Testpack.ttf"


@pytest.fixture(autouse=True)
def _fixed_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _providers(*tiles):
    """Wraps tiles in a provider dict shaped like slice_provider_tiles emits."""
    return [{"tiles": list(tiles)}]


def _rows_by_pair(storage):
    return {(r["font_id"], r["codepoint"]): r for r in storage.sidecar_rows}


# ---------------------------------------------------------------------------
# build_color_glyph_map
# ---------------------------------------------------------------------------

def test_build_color_glyph_map_groups_by_font_id_sorted():
    t1 = make_raster_tile(0xE002, flat_two_color_cell(8, 8), 8, 7, font_id="wy:a")
    t2 = make_raster_tile(0xE001, flat_two_color_cell(8, 8), 8, 7, font_id="wy:a")
    t3 = make_raster_tile(0xE000, flat_two_color_cell(8, 8), 8, 7, font_id="wy:b")

    color_map = build_color_glyph_map(_providers(t1, t2, t3))

    assert set(color_map) == {"wy:a", "wy:b"}
    # codepoints sorted within a bucket
    assert list(color_map["wy:a"]) == [0xE001, 0xE002]
    assert list(color_map["wy:b"]) == [0xE000]


def test_build_color_glyph_map_skips_mono_and_space():
    raster = make_raster_tile(0xE000, flat_two_color_cell(8, 8), 8, 7, font_id="wy:a")
    mono = {"font_id": "wy:a", "codepoint": 0x0041, "render_mode": "mono"}
    space_provider = {"type": "space", "advances": [(0xE050, -8.0)], "font_id": "wy:a"}

    color_map = build_color_glyph_map([{"tiles": [raster, mono]}, space_provider])
    assert list(color_map["wy:a"]) == [0xE000]


def test_build_color_glyph_map_empty_when_no_raster():
    mono = {"font_id": "wy:a", "codepoint": 0x0041, "render_mode": "mono"}
    assert build_color_glyph_map([{"tiles": [mono]}]) == {}


def test_build_color_glyph_map_last_wins_within_font():
    first = make_raster_tile(0xE000, flat_two_color_cell(8, 8), 8, 7, font_id="wy:a")
    second = make_raster_tile(0xE000, color_cell(8, 8, {(0, 0): (9, 9, 9, 255)}), 8, 7, font_id="wy:a")
    color_map = build_color_glyph_map(_providers(first, second))
    assert color_map["wy:a"][0xE000] is second


def test_alternates_contain_no_raster():
    # The classifier stamps raster/mono; build_color_glyph_map only ever selects
    # raster tiles, so the mono map the Galactic/Illageralt overlays clone stays
    # raster-free. A tile the classifier left mono is never pulled into colour.
    raster = make_raster_tile(0xE000, flat_two_color_cell(8, 8), 8, 7, font_id="minecraft:illageralt")
    mono = {"font_id": "minecraft:illageralt", "codepoint": 0x0041, "render_mode": "mono"}
    color_map = build_color_glyph_map([{"tiles": [raster, mono]}])
    assert 0x0041 not in color_map["minecraft:illageralt"]


def test_group_color_space_rows():
    p1 = {"type": "space", "advances": [(0xE010, -16384), (0xE011, 4.0)], "font_id": "wy:s"}
    p2 = {"type": "space", "advances": [(0xE012, 0.0)], "font_id": "wy:t"}
    raster = {"tiles": [make_raster_tile(0xE000, flat_two_color_cell(8, 8), 8, 7, font_id="wy:s")]}

    rows = group_color_space_rows([p1, p2, raster])
    assert rows == {"wy:s": [(0xE010, -16384), (0xE011, 4.0)], "wy:t": [(0xE012, 0.0)]}


# ---------------------------------------------------------------------------
# per-pack colour font (one merged file per source pack)
# ---------------------------------------------------------------------------

def _distinct_cell(seed):
    """An 8x8 opaque cell whose pixels depend on `seed`, so distinct seeds do not
    dedup onto one glyph."""
    return color_cell(8, 8, {(x, y): ((seed * 37 + x) % 256, (seed * 53 + y) % 256, 90, 255)
                             for x in range(8) for y in range(8)})


def _one_font_map(font_id, *codepoints):
    # Distinct art per codepoint so each mints its own glyph (identical art would
    # dedup to a single gid, which is correct but hides per-glyph counts).
    tiles = [make_raster_tile(cp, _distinct_cell(cp), 8, 7, font_id=font_id)
             for cp in codepoints]
    return build_color_glyph_map(_providers(*tiles))


def test_no_color_fonts_emits_nothing(tmp_path):
    # An art-free pack contributes no colour spec (collect_color_fonts drops it), so
    # create_font_files with no colour fonts and no mono styles writes nothing.
    files, color_results = create_font_files(
        {}, False, [], str(tmp_path), OUTPUT_FONT_NAME, "ttf", color_fonts=[])
    assert files == []
    assert color_results == []
    assert os.listdir(tmp_path) == []


def test_single_merged_file_carries_all_font_ids(tmp_path):
    # Same PUA codepoint under two font ids with DIFFERENT art -> ONE file whose cmap
    # carries two distinct stored codepoints, one per pair, mapping to two glyphs.
    art_a = flat_two_color_cell(8, 8, left=(200, 0, 0, 255), right=(0, 0, 200, 255))
    art_b = flat_two_color_cell(8, 8, left=(0, 200, 0, 255), right=(200, 200, 0, 255))
    color_map = build_color_glyph_map(_providers(
        make_raster_tile(0xE000, art_a, 8, 7, font_id="packA:icons"),
        make_raster_tile(0xE000, art_b, 8, 7, font_id="packB:icons"),
    ))

    color_file, storage = build_one_color_font(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)

    assert os.path.basename(color_file) == MERGED_NAME
    assert [f for f in os.listdir(tmp_path) if f.endswith(".ttf")] == [MERGED_NAME]

    rows = _rows_by_pair(storage)
    stored_a = rows[("packA:icons", 0xE000)]["stored_codepoint"]
    stored_b = rows[("packB:icons", 0xE000)]["stored_codepoint"]
    # the colliding original codepoint got two distinct stored codepoints
    assert stored_a != stored_b
    assert stored_a >= STORED_CP_START and stored_b >= STORED_CP_START

    font = TTFont(color_file)
    assert "sbix" in font
    cmap = font.getBestCmap()
    # the merged cmap carries the stored codepoints, not the original PUA one
    assert stored_a in cmap and stored_b in cmap
    assert 0xE000 not in cmap
    # distinct art -> distinct glyphs
    assert cmap[stored_a] != cmap[stored_b]


def test_stored_codepoints_assigned_in_sorted_pair_order(tmp_path):
    # Deterministic allocation: sort (font_id, codepoint) pairs, assign linearly from
    # U+F0000. "wy:a" sorts before "wy:b"; within a font id, codepoints ascend.
    color_map = {}
    color_map.update(_one_font_map("wy:b", 0xE000))
    color_map.update(_one_font_map("wy:a", 0xE001, 0xE000))

    _, storage = build_one_color_font(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)
    rows = _rows_by_pair(storage)

    assert rows[("wy:a", 0xE000)]["stored_codepoint"] == STORED_CP_START
    assert rows[("wy:a", 0xE001)]["stored_codepoint"] == STORED_CP_START + 1
    assert rows[("wy:b", 0xE000)]["stored_codepoint"] == STORED_CP_START + 2


def test_color_mode_regular_only(tmp_path):
    # One pack yields exactly one file (no bold/italic/alternate fan-out).
    color_map = _one_font_map("wy:a", 0xE000, 0xE001)
    color_file, storage = build_one_color_font(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)
    assert color_file is not None
    assert storage is not None
    ttfs = [f for f in os.listdir(tmp_path) if f.endswith(".ttf")]
    assert ttfs == [MERGED_NAME]


def test_gid_ceiling_scoped(tmp_path):
    # The glyph set is seeded from the packs' raster tiles + .notdef only: no
    # vanilla/unifont clone, so numGlyphs stays tiny and far under 65535.
    color_map = {}
    color_map.update(_one_font_map("wy:a", 0xE000, 0xE001, 0xE002))
    color_map.update(_one_font_map("wy:b", 0xE009))  # distinct seed -> distinct art
    color_file, _ = build_one_color_font(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)
    font = TTFont(color_file)
    # 4 distinct raster glyphs + .notdef
    assert font["maxp"].numGlyphs == 5
    assert font["maxp"].numGlyphs < 65535


def test_cross_font_id_dedup_shares_one_gid(tmp_path):
    # Identical art under two different font ids collapses to ONE glyph (pack-wide
    # dedup), but each pair keeps its own stored codepoint and sidecar row.
    same = flat_two_color_cell(8, 8)
    color_map = build_color_glyph_map(_providers(
        make_raster_tile(0xE000, same, 8, 7, font_id="wy:a"),
        make_raster_tile(0xE000, flat_two_color_cell(8, 8), 8, 7, font_id="wy:b"),
    ))
    color_file, storage = build_one_color_font(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)
    rows = _rows_by_pair(storage)

    row_a = rows[("wy:a", 0xE000)]
    row_b = rows[("wy:b", 0xE000)]
    assert row_a["glyphName"] == row_b["glyphName"]           # one shared glyph
    assert row_a["stored_codepoint"] != row_b["stored_codepoint"]  # distinct stored cps

    name_to_gid = storage.name_to_gid()
    assert name_to_gid[row_a["glyphName"]] == name_to_gid[row_b["glyphName"]]

    font = TTFont(color_file)
    # 1 shared raster glyph + .notdef
    assert font["maxp"].numGlyphs == 2
    cmap = font.getBestCmap()
    # both stored codepoints resolve to the one shared glyph
    assert cmap[row_a["stored_codepoint"]] == cmap[row_b["stored_codepoint"]]


def test_space_only_pack_no_file_but_keeps_rows(tmp_path):
    # A pack with only space advances mints no glyph and no .ttf, but its storage
    # still carries the sidecar rows so they are not lost.
    color_file, storage = build_one_color_font(
        {}, {"wy:spacing": [(0xE100, -16384)]}, str(tmp_path), OUTPUT_FONT_NAME)
    assert color_file is None
    assert storage is not None
    rows = storage.sidecar_rows
    assert [(r["codepoint"], r["advance"]) for r in rows] == [(0xE100, -16384)]
    assert rows[0]["stored_codepoint"] is None
    assert [f for f in os.listdir(tmp_path) if f.endswith(".ttf")] == []


def test_space_rows_ride_in_the_merged_storage(tmp_path):
    # Space rows ride in the single storage beside the raster art; they mint no glyph.
    color_map = _one_font_map("wy:a", 0xE000)
    color_file, storage = build_one_color_font(
        color_map, {"wy:a": [(0xE100, -8.0)]}, str(tmp_path), OUTPUT_FONT_NAME)
    assert color_file is not None
    codepoints = {r["codepoint"] for r in storage.sidecar_rows}
    assert {0xE000, 0xE100} <= codepoints
    # the space row has no stored codepoint and minted no glyph
    space_row = next(r for r in storage.sidecar_rows if r["codepoint"] == 0xE100)
    assert space_row["stored_codepoint"] is None
    assert space_row["glyphName"] is None


def test_per_pack_color_font_deterministic(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    def _build(outdir):
        color_map = {}
        color_map.update(_one_font_map("wy:b", 0xE000))
        color_map.update(_one_font_map("wy:a", 0xE000, 0xE001))
        path, _ = build_one_color_font(color_map, {}, str(outdir), OUTPUT_FONT_NAME)
        with open(path, "rb") as f:
            return f.read()

    assert _build(dir_a) == _build(dir_b)
