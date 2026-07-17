"""M5: versioned single-file colour sidecar (schema v2) with stored codepoints,
signed advances, and deterministic output."""
import io
import json

import pytest
from fontTools.ttLib import TTFont

from helpers import (
    build_color_font_storage,
    compiled_font_bytes,
    flat_two_color_cell,
    make_raster_tile,
)
from minecraft_fontgen.colour_sidecar import build_sidecar, write_sidecar
from minecraft_fontgen.config import STORED_CP_START, UNITS_PER_EM, VERSION

MERGED_FILE = "Minecraft-Color.ttf"


@pytest.fixture(autouse=True)
def _fixed_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _demo_storage(font_id="test:demo", first_cp=0xE001):
    tiles = [
        make_raster_tile(first_cp, flat_two_color_cell(8, 8), 8, 7, font_id=font_id),
        make_raster_tile(first_cp + 1, flat_two_color_cell(16, 16), 8, 7, font_id=font_id),
    ]
    return build_color_font_storage(tiles)


def test_sidecar_schema_and_determinism():
    storage_a = _demo_storage()
    sidecar_a = build_sidecar(MERGED_FILE, storage_a, 1700000000)
    json_a = json.dumps(sidecar_a, ensure_ascii=False, indent=2)
    font_a = compiled_font_bytes(storage_a)

    storage_b = _demo_storage()
    sidecar_b = build_sidecar(MERGED_FILE, storage_b, 1700000000)
    json_b = json.dumps(sidecar_b, ensure_ascii=False, indent=2)
    font_b = compiled_font_bytes(storage_b)

    assert json_a == json_b
    assert font_a == font_b

    assert sidecar_a["schema_version"] == 2
    assert sidecar_a["generator_version"] == VERSION
    assert sidecar_a["source_date_epoch"] == 1700000000
    assert sidecar_a["units_per_em"] == UNITS_PER_EM
    assert sidecar_a["graphic_type"] == "png "
    # single top-level file reference, not a per-font-id map
    assert sidecar_a["file"] == MERGED_FILE
    assert "fonts" not in sidecar_a
    # glyphs sorted by (font_id, codepoint)
    cps = [g["codepoint"] for g in sidecar_a["glyphs"]]
    assert cps == sorted(cps)
    for glyph in sidecar_a["glyphs"]:
        assert set(glyph.keys()) == {
            "font_id", "codepoint", "stored_codepoint", "glyph_name", "gid",
            "advance", "origin", "strike_ppem",
        }
        # every raster row carries a plane-15/16 stored codepoint
        assert glyph["stored_codepoint"] >= STORED_CP_START


def test_sidecar_gid_matches_glyph_order():
    storage = _demo_storage()
    sidecar = build_sidecar(MERGED_FILE, storage, 1700000000)

    reopened = TTFont(io.BytesIO(compiled_font_bytes(storage)))
    order = reopened.getGlyphOrder()
    best = reopened.getBestCmap()
    for glyph in sidecar["glyphs"]:
        if glyph["gid"] is None:
            continue
        # post 3.0 renames on reload, so match by STORED codepoint -> cmap name at that gid
        assert order[glyph["gid"]] == best[glyph["stored_codepoint"]]


def test_sidecar_pua_disambiguation():
    # Same PUA codepoint under two font_ids with different art -> two rows, two stored
    # codepoints, one merged file.
    left = flat_two_color_cell(8, 8, left=(200, 0, 0, 255), right=(0, 0, 200, 255))
    right = flat_two_color_cell(8, 8, left=(0, 200, 0, 255), right=(200, 200, 0, 255))
    storage = build_color_font_storage([
        make_raster_tile(0xE000, left, 8, 7, font_id="packA:default"),
        make_raster_tile(0xE000, right, 8, 7, font_id="packB:default"),
    ])
    sidecar = build_sidecar(MERGED_FILE, storage, 1700000000)

    rows = [g for g in sidecar["glyphs"] if g["codepoint"] == 0xE000]
    assert len(rows) == 2
    assert {r["font_id"] for r in rows} == {"packA:default", "packB:default"}
    # the colliding original codepoint maps to two distinct stored codepoints
    assert len({r["stored_codepoint"] for r in rows}) == 2
    assert sidecar["file"] == MERGED_FILE


def test_negative_advance_from_space_provider():
    storage = _demo_storage()
    storage.add_space_row("test:demo", 0xE100, -16384)

    sidecar = build_sidecar(MERGED_FILE, storage, 1700000000)

    space_rows = [g for g in sidecar["glyphs"] if g["codepoint"] == 0xE100]
    assert len(space_rows) == 1
    row = space_rows[0]
    assert row["advance"] == -16384
    assert row["glyph_name"] is None
    assert row["gid"] is None
    assert row["strike_ppem"] is None
    assert row["stored_codepoint"] is None
    # no glyph was minted: the codepoint is absent from cmap and hmtx
    assert 0xE100 not in storage.font.getBestCmap()


def test_write_sidecar_roundtrip(tmp_path):
    storage = _demo_storage()
    sidecar = build_sidecar(MERGED_FILE, storage, 1700000000)

    path = write_sidecar(sidecar, str(tmp_path))
    assert path.endswith("colour-glyphs.json")
    with open(path, encoding="utf-8") as f:
        reloaded = json.load(f)
    assert reloaded == sidecar


def test_write_sidecar_fails_loud(tmp_path):
    sidecar = build_sidecar(MERGED_FILE, _demo_storage(), 1700000000)
    missing_dir = str(tmp_path / "does-not-exist")
    with pytest.raises(SystemExit):
        write_sidecar(sidecar, missing_dir)


def test_sidecar_file_none_for_space_only_pack():
    # A space-only pack writes no .ttf; the sidecar records file=None but keeps rows.
    from minecraft_fontgen.font_creator import create_color_font_files
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, storage = create_color_font_files({}, {"wy:s": [(0xE100, -16384)]}, tmp, "Minecraft")
    sidecar = build_sidecar(None, storage, 1700000000)
    assert sidecar["file"] is None
    assert [g["codepoint"] for g in sidecar["glyphs"]] == [0xE100]
