from collections import OrderedDict

from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.config import FONT_STYLES
from minecraft_fontgen.file_io import _process_alternate_font

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
