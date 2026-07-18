"""Per-source-pack colour output: collect_color_fonts composes one colour font spec
per pack, create_font_files emits Minecraft-<Namespace>.ttf + a matching sidecar per
pack, and every font stores the identity of the source it came from (pack_id)."""
import os

import pytest
from fontTools.ttLib import TTFont

from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.colour_sidecar import build_sidecar, sidecar_name, write_sidecar
from minecraft_fontgen.config import FONT_STYLES, OUTPUT_FONT_NAME, VANILLA_PACK_ID
from minecraft_fontgen.file_io import collect_color_fonts, color_font_namespace
from minecraft_fontgen.font_creator import create_font_files
from minecraft_fontgen.functions import resolve_source_date_epoch

from helpers import FakeSource, color_pack_source, two_color_block_png


@pytest.fixture(autouse=True)
def _fixed_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _raster_pack(name, font_id, codepoint=0xE000):
    # the texture ref namespace derives from the font id (always lowercase-valid) and
    # is unique per pack, so two packs never share a materialized texture path
    ref_ns = font_id.split(":", 1)[0]
    return color_pack_source(
        font_id, cells={f"{ref_ns}:icon.png": (chr(codepoint), two_color_block_png(8, 8))},
        name=name)


# ---------------------------------------------------------------------------
# collect_color_fonts
# ---------------------------------------------------------------------------

def test_namespace_capitalizes_first_char():
    assert color_font_namespace("aurora") == "Aurora"
    assert color_font_namespace("seaside") == "Seaside"
    # internal capitals are preserved (only the first char is forced upper)
    assert color_font_namespace("myPack") == "MyPack"


def test_collect_color_fonts_one_spec_per_pack():
    stack = AssetStack([
        FakeSource("vanilla", vanilla=True),
        _raster_pack("aurora", "wy:icons"),
        _raster_pack("seaside", "mcc:icons"),
    ])
    specs = collect_color_fonts(stack, color_glyphs=True)

    assert [s["name"] for s in specs] == ["Aurora", "Seaside"]
    assert [s["pack_id"] for s in specs] == ["aurora", "seaside"]
    # each spec only carries its own pack's font id
    assert set(specs[0]["color_map"]) == {"wy:icons"}
    assert set(specs[1]["color_map"]) == {"mcc:icons"}


def test_collect_color_fonts_drops_art_free_pack():
    from helpers import font_json_bytes

    # a pack whose only font file has no providers contributes no colour art
    empty = FakeSource("emptypack", fonts={"e:mono": font_json_bytes([])})
    stack = AssetStack([FakeSource("vanilla", vanilla=True), empty,
                        _raster_pack("aurora", "wy:icons")])
    specs = collect_color_fonts(stack, color_glyphs=True)
    assert [s["name"] for s in specs] == ["Aurora"]


def test_collect_color_fonts_off_returns_empty():
    stack = AssetStack([FakeSource("vanilla", vanilla=True), _raster_pack("aurora", "wy:icons")])
    assert collect_color_fonts(stack, color_glyphs=False) == []


def test_collision_disambiguated_with_suffix():
    # two DISTINCT pack ids that capitalize to the same namespace get distinct output
    # names, so N packs always yield N files
    stack = AssetStack([
        _raster_pack("aurora", "a:icons"),
        _raster_pack("Aurora", "b:icons"),
    ])
    specs = collect_color_fonts(stack, color_glyphs=True)
    assert [s["pack_id"] for s in specs] == ["aurora", "Aurora"]
    assert [s["name"] for s in specs] == ["Aurora", "Aurora2"]


# ---------------------------------------------------------------------------
# per-pack emission through create_font_files
# ---------------------------------------------------------------------------

def test_n_packs_emit_n_fonts_and_sidecars(tmp_path):
    stack = AssetStack([
        FakeSource("vanilla", vanilla=True),
        _raster_pack("aurora", "wy:icons"),
        _raster_pack("seaside", "mcc:icons"),
    ])
    color_fonts = collect_color_fonts(stack, color_glyphs=True)

    _, color_results = create_font_files(
        {}, False, [], str(tmp_path), OUTPUT_FONT_NAME, "ttf", color_fonts=color_fonts)

    # two distinct merged fonts, one per pack namespace
    names = sorted(os.path.basename(f) for _, f, _ in color_results)
    assert names == ["Minecraft-Aurora.ttf", "Minecraft-Seaside.ttf"]

    written = set()
    for spec, color_file, storage in color_results:
        assert storage.pack_id == spec["pack_id"]  # the font stores its source identity
        sidecar = build_sidecar(os.path.basename(color_file), storage, resolve_source_date_epoch())
        # each sidecar's top-level file reference names its own pack's font
        assert sidecar["file"] == f"{OUTPUT_FONT_NAME}-{spec['name']}.ttf"
        path = write_sidecar(sidecar, str(tmp_path), name=sidecar_name(spec["name"]))
        written.add(os.path.basename(path))

    assert written == {"Minecraft-Aurora.colour-glyphs.json",
                       "Minecraft-Seaside.colour-glyphs.json"}
    # the two fonts carry independent stored-codepoint allocations but distinct files
    fonts = {os.path.basename(f): TTFont(f) for _, f, _ in color_results}
    for font in fonts.values():
        assert "sbix" in font


def test_mono_font_stores_vanilla_pack_id(tmp_path, monkeypatch):
    # The mono styles inherit the vanilla source identity; capture the storage the
    # shared loop builds to prove the pack id is threaded onto the mono side too.
    captured = []
    real_init = create_font_files.__globals__["GlyphStorage"]

    class Probe(real_init):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured.append(self)

    monkeypatch.setitem(create_font_files.__globals__, "GlyphStorage", Probe)

    glyph_map = {"Regular": {}, "Bold": {}}
    styles = [dict(s) for s in FONT_STYLES if s["name"] == "Regular"]
    create_font_files(glyph_map, False, styles, str(tmp_path), OUTPUT_FONT_NAME, "ttf")

    assert captured, "expected the mono style to build a storage"
    assert all(storage.pack_id == VANILLA_PACK_ID for storage in captured)
