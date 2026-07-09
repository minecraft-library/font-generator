import os
from collections import OrderedDict

import minecraft_fontgen.file_io as file_io
from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.config import FONT_STYLES
from minecraft_fontgen.file_io import _process_alternate_font, build_glyph_map, slice_provider_tiles

from helpers import FakeSource, block, font_json_bytes, make_png_bytes


ALT_CONFIG = {"name": "Galactic", "font_id": "minecraft:alt", "map_lowercase": True}


def _regular_map():
    return OrderedDict({
        ord("A"): {"codepoint": ord("A"), "source": "provider"},
        ord("B"): {"codepoint": ord("B"), "source": "provider"},
        ord("a"): {"codepoint": ord("a"), "source": "provider"},
    })


def _vanilla_alt_source():
    return FakeSource("vanilla", vanilla=True, fonts={
        "minecraft:alt": font_json_bytes([
            {"type": "bitmap", "file": "minecraft:font/alt.png", "ascent": 7, "height": 8, "chars": ["A"]},
            {"type": "bitmap", "file": "minecraft:font/alt2.png", "ascent": 7, "height": 8, "chars": ["B"]},
        ]),
    }, textures={
        "minecraft:font/alt.png": make_png_bytes(8, 8, block(0, 0, 2, 8)),
        "minecraft:font/alt2.png": make_png_bytes(8, 8, block(0, 0, 4, 8)),
    })


def test_reads_all_providers_and_maps_lowercase():
    stack = AssetStack([_vanilla_alt_source()])
    overlay = _process_alternate_font(ALT_CONFIG, _regular_map(), stack)

    assert overlay[ord("A")]["source"] == "alternate"
    assert overlay[ord("B")]["source"] == "alternate"  # second provider no longer dropped
    assert overlay[ord("a")]["source"] == "alternate"  # map_lowercase copy
    assert overlay[ord("A")]["pixels"]["width"] == 2


def test_pack_layer_overrides_and_new_codepoints_are_appended():
    pack = FakeSource("skypack", fonts={
        "minecraft:alt": font_json_bytes([
            {"type": "bitmap", "file": "sky:alt.png", "ascent": 7, "height": 8, "chars": ["A"]},
        ]),
    }, textures={
        "sky:alt.png": make_png_bytes(16, 8, block(0, 0, 5, 8) + block(8, 0, 3, 8)),
    })
    stack = AssetStack([_vanilla_alt_source(), pack])
    overlay = _process_alternate_font(ALT_CONFIG, _regular_map(), stack)

    assert overlay[ord("A")]["pixels"]["width"] == 5  # pack beats vanilla alt
    assert overlay[0xE000]["pixels"]["width"] == 3  # new codepoint kept, not dropped
    assert list(overlay) == sorted(overlay)


def test_returns_none_when_no_layer_defines_the_font():
    stack = AssetStack([FakeSource("vanilla", vanilla=True)])
    assert _process_alternate_font(ALT_CONFIG, _regular_map(), stack) is None


def test_font_styles_carry_font_ids():
    by_name = {s["name"]: s for s in FONT_STYLES}
    assert by_name["Galactic"]["font_id"] == "minecraft:alt"
    assert by_name["Illageralt"]["font_id"] == "minecraft:illageralt"
    assert "json_file" not in by_name["Galactic"]


# ==========================================
# === build_glyph_map: BOLD_PACK_GLYPHS ===
# ==========================================

def _bold_pack_providers():
    """A vanilla-layer 'V' provider and a pack-layer 'P' provider, each holding a
    single 3px-wide bar glyph (columns 0-2, rows 2-5 of an 8x8 tile). Bold tracing
    expands the bar 1px rightward, so regular width == 3 and bold width == 4 —
    a cheap, reliable way to tell which trace a Bold entry actually carries."""
    os.makedirs("work/glyphs/vanilla_bp", exist_ok=True)
    os.makedirs("work/glyphs/pack_bp", exist_ok=True)
    with open("work/vanilla_bp.png", "wb") as f:
        f.write(make_png_bytes(128, 8, block(0, 2, 3, 4)))
    with open("work/pack_bp.png", "wb") as f:
        f.write(make_png_bytes(128, 8, block(0, 2, 3, 4)))

    vanilla_provider = {
        "ascent": 7,
        "height": 8,
        "rows": 1,
        "columns": 16,
        "chars": ["V"] + ["\x00"] * 15,
        "file_name": "vanilla_bp.png",
        "file_path": "work/vanilla_bp.png",
        "name": "vanilla_bp",
        "output": "work/glyphs/vanilla_bp",
        "layer": "vanilla",
        "tiles": [],
    }
    pack_provider = {
        "ascent": 7,
        "height": 8,
        "rows": 1,
        "columns": 16,
        "chars": ["P"] + ["\x00"] * 15,
        "file_name": "pack_bp.png",
        "file_path": "work/pack_bp.png",
        "name": "pack_bp",
        "output": "work/glyphs/pack_bp",
        "layer": "pack",
        "tiles": [],
    }
    return vanilla_provider, pack_provider


def test_bold_pack_glyphs_flag_swaps_pack_layer_trace_only(monkeypatch):
    vanilla_provider, pack_provider = _bold_pack_providers()
    slice_provider_tiles([vanilla_provider, pack_provider])

    # Default (BOLD_PACK_GLYPHS=True): both vanilla and pack Bold entries carry the bold trace.
    glyph_map = build_glyph_map([vanilla_provider, pack_provider], None)
    assert glyph_map["Bold"][ord("V")]["pixels"]["width"] == 4
    assert glyph_map["Bold"][ord("P")]["pixels"]["width"] == 4

    # BOLD_PACK_GLYPHS=False: the pack-layer Bold entry falls back to the regular
    # trace (un-smeared); the vanilla-layer Bold entry is unaffected.
    monkeypatch.setattr(file_io, "BOLD_PACK_GLYPHS", False)
    glyph_map = build_glyph_map([vanilla_provider, pack_provider], None)
    assert glyph_map["Bold"][ord("V")]["pixels"]["width"] == 4
    assert glyph_map["Bold"][ord("P")]["pixels"]["width"] == 3


# ==========================================
# === build_glyph_map: stack-aware wiring ===
# ==========================================

def _regular_provider_for_stack_test():
    """A minimal vanilla provider with two ASCII glyphs ('A', 'B'), for exercising
    build_glyph_map(..., stack=...) without pulling in the whole pipeline."""
    os.makedirs("work/glyphs/stack_regular", exist_ok=True)
    png = make_png_bytes(128, 8, block(0, 0, 4, 8) + block(8, 0, 4, 8))
    with open("work/stack_regular.png", "wb") as f:
        f.write(png)
    return {
        "ascent": 7,
        "height": 8,
        "rows": 1,
        "columns": 16,
        "chars": ["A", "B"] + ["\x00"] * 14,
        "file_name": "stack_regular.png",
        "file_path": "work/stack_regular.png",
        "name": "stack_regular",
        "output": "work/glyphs/stack_regular",
        "layer": "vanilla",
        "tiles": [],
    }


def test_build_glyph_map_wires_stack_for_alternate_fonts():
    provider = _regular_provider_for_stack_test()
    slice_provider_tiles([provider])
    # Only "minecraft:alt" (Galactic) is defined in this stack; "minecraft:illageralt" is not.
    stack = AssetStack([_vanilla_alt_source()])

    glyph_map = build_glyph_map([provider], None, stack=stack)

    # Galactic overlay is present, with the alternate trace overriding 'A' and the
    # lowercase codepoint mapped from the uppercase glyph per map_lowercase.
    assert "Galactic" in glyph_map
    assert glyph_map["Galactic"][ord("A")]["source"] == "alternate"
    assert glyph_map["Galactic"][ord("A")]["pixels"]["width"] == 2
    assert glyph_map["Galactic"][ord("a")]["source"] == "alternate"

    # Illageralt's font_id has no layer in the stack, so it is gracefully skipped.
    assert "Illageralt" not in glyph_map

    # Base Regular/Bold maps are present and unpolluted by the overlay.
    assert glyph_map["Regular"][ord("A")]["source"] == "provider"
    assert glyph_map["Regular"][ord("B")]["source"] == "provider"
    assert glyph_map["Bold"][ord("A")]["source"] == "provider"
    assert glyph_map["Bold"][ord("B")]["source"] == "provider"
