import os
from collections import OrderedDict

import minecraft_fontgen.file_io as file_io
from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.config import (
    FONT_STYLES, VERSION, MANUFACTURER, DESIGNER, DESCRIPTION, COPYRIGHT,
    VENDOR_URL, DESIGNER_URL, SAMPLE_TEXT
)
from minecraft_fontgen.file_io import _process_alternate_font, build_glyph_map, slice_provider_tiles
from minecraft_fontgen.font_creator import _init_font

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


def test_malformed_pack_alt_font_json_is_skipped(capsys):
    bad_pack = FakeSource("badpack", fonts={
        "minecraft:alt": b"{not json",
    })
    stack = AssetStack([_vanilla_alt_source(), bad_pack])
    overlay = _process_alternate_font(ALT_CONFIG, _regular_map(), stack)

    assert overlay[ord("A")]["source"] == "alternate"  # vanilla alt layer still used
    assert overlay[ord("A")]["pixels"]["width"] == 2
    assert "badpack" in capsys.readouterr().out


def test_font_styles_carry_font_ids():
    by_name = {s["name"]: s for s in FONT_STYLES}
    assert by_name["Galactic"]["font_id"] == "minecraft:alt"
    assert by_name["Illageralt"]["font_id"] == "minecraft:illageralt"
    assert "json_file" not in by_name["Galactic"]


# ==========================================
# === name table: each font's identity ===
# ==========================================

# The (platformID, platEncID, langID) of every name record the generator writes:
# Unicode BMP, Mac Roman English, and Windows Unicode BMP en-US.
_NAME_PLATFORMS = {(0, 3, 0), (1, 0, 0), (3, 1, 0x409)}


def _name_records(spec):
    """Every name record of the font _init_font builds for one style spec, as
    platformID -> {nameID: text}. The records must cover exactly the three platforms
    the generator writes, with no nameID twice on one platform, so a dropped, added or
    doubled record fails here rather than slipping past a pinned dict."""
    records = _init_font(spec, True)["name"].names
    assert {(r.platformID, r.platEncID, r.langID) for r in records} == _NAME_PLATFORMS, spec["name"]
    by_platform = {}
    for r in records:
        names = by_platform.setdefault(r.platformID, {})
        assert r.nameID not in names, (spec["name"], r.platformID, r.nameID)
        names[r.nameID] = r.toUnicode()
    return by_platform


def _assert_name_table(spec, family, subfamily, full_name, ps_name, typo_family):
    """Pins the whole name table of one style on every platform: its identity strings
    and the metadata every font shares."""
    expected = {
        0: COPYRIGHT,
        1: family,
        2: subfamily,
        3: f"Version {VERSION};{MANUFACTURER};{full_name}",
        4: full_name,
        5: f"Version {VERSION}",
        6: ps_name,
        8: MANUFACTURER,
        9: DESIGNER,
        10: DESCRIPTION,
        11: VENDOR_URL,
        12: DESIGNER_URL,
        16: typo_family,
        17: subfamily,
        18: full_name,
        19: SAMPLE_TEXT,
    }
    for platform, names in _name_records(spec).items():
        assert names == expected, (spec["name"], platform)


def test_alternate_fonts_carry_their_own_name():
    """Galactic and Illageralt are Regular-weight, upright faces like Regular itself, so
    a name built from the weight and slope alone gives all three one identity - and a
    consumer that caches metrics by font name lays the alt fonts out at Regular's widths.
    The qualifier names the family and leaves the subfamily 'Regular', the way a face
    outside the four-style group keeps its distinction in the family name."""
    by_name = {s["name"]: s for s in FONT_STYLES}
    windows = {style: _name_records(by_name[style])[3] for style in ("Regular", "Galactic", "Illageralt")}

    # family, unique id, full name, PostScript name, typographic family, compatible full
    for name_id in (1, 3, 4, 6, 16, 18):
        assert len({names[name_id] for names in windows.values()}) == 3, name_id

    _assert_name_table(by_name["Galactic"], "Minecraft Galactic Font", "Regular",
                       "Minecraft Galactic Font Regular", "Minecraft-GalacticRegular",
                       "Minecraft Galactic")
    _assert_name_table(by_name["Illageralt"], "Minecraft Illageralt Font", "Regular",
                       "Minecraft Illageralt Font Regular", "Minecraft-IllageraltRegular",
                       "Minecraft Illageralt")


def test_no_two_font_styles_share_an_identity():
    """The keys an OS font install and AWT's font lookup collide on: family plus
    subfamily, the full name, the PostScript name, and the typographic pair, on each
    platform a reader may take them from."""
    names = {s["name"]: _name_records(s) for s in FONT_STYLES}
    for platform in sorted({p for p, _, _ in _NAME_PLATFORMS}):
        for key in ((1, 2), (4,), (6,), (16, 17)):
            seen = {}
            for style, by_platform in names.items():
                identity = tuple(by_platform[platform][name_id] for name_id in key)
                assert identity not in seen, \
                    f"{style} and {seen[identity]} share {key} on platform {platform}: {identity}"
                seen[identity] = style


def test_default_family_name_tables_are_unchanged():
    """The four default-family faces carry no qualifier, so each names the one shared
    family and tells itself apart by weight and slope alone, record for record on
    every platform."""
    by_name = {s["name"]: s for s in FONT_STYLES}
    for style in ("Regular", "Bold", "Italic", "BoldItalic"):
        _assert_name_table(by_name[style], "Minecraft Font", style,
                           f"Minecraft Font {style}", f"Minecraft{style}", "Minecraft")


# ==========================================
# === build_glyph_map: BOLD_PACK_GLYPHS ===
# ==========================================

def _bold_pack_providers():
    """A vanilla-layer 'V' provider and a pack-layer 'P' provider, each holding a
    single 3px-wide bar glyph (columns 0-2, rows 2-5 of an 8x8 tile). A Bold entry
    drawn as the client's two copies advances one pixel further than Regular, a
    cheap, reliable way to tell which a Bold entry actually carries."""
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

    # Default (BOLD_PACK_GLYPHS=True): both vanilla and pack Bold entries draw two copies.
    glyph_map = build_glyph_map([vanilla_provider, pack_provider], None)
    for char in "VP":
        assert len(glyph_map["Bold"][ord(char)]["scaled"]["copies"]) == 2
        assert glyph_map["Bold"][ord(char)]["advance_units"] == 640  # (3 + 1) * 128 + 128

    # BOLD_PACK_GLYPHS=False: the pack-layer Bold entry stays the single Regular
    # glyph at Regular's advance; the vanilla-layer Bold entry is unaffected.
    monkeypatch.setattr(file_io, "BOLD_PACK_GLYPHS", False)
    glyph_map = build_glyph_map([vanilla_provider, pack_provider], None)
    assert len(glyph_map["Bold"][ord("V")]["scaled"]["copies"]) == 2
    assert glyph_map["Bold"][ord("V")]["advance_units"] == 640
    assert "copies" not in glyph_map["Bold"][ord("P")]["scaled"]
    assert glyph_map["Bold"][ord("P")]["advance_units"] == 512


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
