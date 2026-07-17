"""M6: per-font-id colour compilation, glyph-map grouping, and the single-Regular,
GID-ceiling-scoped emission that never touches the mono four-style fan-out."""
import os

import pytest
from fontTools.ttLib import TTFont

from helpers import color_cell, flat_two_color_cell, make_raster_tile
from minecraft_fontgen.config import OUTPUT_FONT_NAME
from minecraft_fontgen.file_io import build_color_glyph_map, group_color_space_rows
from minecraft_fontgen.font_creator import create_color_font_files


@pytest.fixture(autouse=True)
def _fixed_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _providers(*tiles):
    """Wraps tiles in a provider dict shaped like slice_provider_tiles emits."""
    return [{"tiles": list(tiles)}]


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
# create_color_font_files
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


def test_empty_map_emits_nothing(tmp_path):
    files, storages = create_color_font_files({}, {}, str(tmp_path), OUTPUT_FONT_NAME)
    assert files == []
    assert storages == []
    assert os.listdir(tmp_path) == []


def test_per_fontid_files_no_collision(tmp_path):
    # Same PUA codepoint under two font ids with different art -> two files, each
    # carrying its own glyph; neither overwrites the other.
    color_map = {}
    color_map.update(_one_font_map("packA:icons", 0xE000))
    color_map.update(_one_font_map("packB:icons", 0xE000))

    files, storages = create_color_font_files(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)

    assert len(files) == 2
    assert {fid for _, fid in files} == {"packA:icons", "packB:icons"}
    basenames = {os.path.basename(path) for path, _ in files}
    assert basenames == {
        f"{OUTPUT_FONT_NAME}-Color-packA_icons.ttf",
        f"{OUTPUT_FONT_NAME}-Color-packB_icons.ttf",
    }
    for path, _ in files:
        font = TTFont(path)
        assert "sbix" in font
        assert 0xE000 in font.getBestCmap()


def test_color_filename_sanitize_collision(tmp_path):
    # Two distinct font ids that sanitize to the same base get distinct filenames
    # (the later one gains a short stable sha1 suffix).
    color_map = {}
    color_map.update(_one_font_map("wy:icons", 0xE000))
    color_map.update(_one_font_map("wy/icons", 0xE001))

    files, _ = create_color_font_files(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)
    basenames = {os.path.basename(p) for p, _ in files}
    assert len(basenames) == 2
    plain = f"{OUTPUT_FONT_NAME}-Color-wy_icons.ttf"
    assert plain in basenames
    # the other file keeps the same base plus a short hex suffix before .ttf
    other = (basenames - {plain}).pop()
    assert other.startswith(f"{OUTPUT_FONT_NAME}-Color-wy_icons-")
    assert other.endswith(".ttf")


def test_color_mode_regular_only(tmp_path):
    # One font id yields exactly one file (no bold/italic/alternate fan-out).
    color_map = _one_font_map("wy:a", 0xE000, 0xE001)
    files, storages = create_color_font_files(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)
    assert len(files) == 1
    assert len(storages) == 1
    ttfs = [f for f in os.listdir(tmp_path) if f.endswith(".ttf")]
    assert len(ttfs) == 1


def test_gid_ceiling_scoped(tmp_path):
    # The glyph set is seeded from this font id's raster tiles + .notdef only:
    # no vanilla/unifont clone, so numGlyphs stays tiny and far under 65535.
    color_map = _one_font_map("wy:a", 0xE000, 0xE001, 0xE002)
    files, storages = create_color_font_files(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)
    font = TTFont(files[0][0])
    # 3 raster glyphs + .notdef
    assert font["maxp"].numGlyphs == 4
    assert font["maxp"].numGlyphs < 65535


def test_space_only_font_id_no_file_but_keeps_rows(tmp_path):
    # A font id with only space advances mints no glyph and no .ttf, but its
    # storage still carries the sidecar rows so they are not lost.
    files, storages = create_color_font_files(
        {}, {"wy:spacing": [(0xE100, -16384)]}, str(tmp_path), OUTPUT_FONT_NAME)
    assert files == []
    assert len(storages) == 1
    rows = storages[0].sidecar_rows
    assert [(r["codepoint"], r["advance"]) for r in rows] == [(0xE100, -16384)]
    assert [f for f in os.listdir(tmp_path) if f.endswith(".ttf")] == []


def test_space_rows_routed_to_matching_font_storage(tmp_path):
    # Space rows for a font id that also has raster art ride in that font's storage.
    color_map = _one_font_map("wy:a", 0xE000)
    files, storages = create_color_font_files(
        color_map, {"wy:a": [(0xE100, -8.0)]}, str(tmp_path), OUTPUT_FONT_NAME)
    assert len(files) == 1
    codepoints = {r["codepoint"] for r in storages[0].sidecar_rows}
    assert {0xE000, 0xE100} <= codepoints
    # the space codepoint minted no glyph
    assert 0xE100 not in TTFont(files[0][0]).getBestCmap()


def test_create_color_font_files_deterministic(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    files_a, _ = create_color_font_files(
        _one_font_map("wy:a", 0xE000, 0xE001), {}, str(dir_a), OUTPUT_FONT_NAME)
    files_b, _ = create_color_font_files(
        _one_font_map("wy:a", 0xE000, 0xE001), {}, str(dir_b), OUTPUT_FONT_NAME)
    with open(files_a[0][0], "rb") as f:
        bytes_a = f.read()
    with open(files_b[0][0], "rb") as f:
        bytes_b = f.read()
    assert bytes_a == bytes_b
