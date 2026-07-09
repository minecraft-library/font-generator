from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.file_io import build_glyph_map, collect_pack_providers, parse_json_providers, slice_provider_tiles

from helpers import FakeSource, block, font_json_bytes, make_png_bytes


def _bitmap(file, chars, ascent=7, height=8):
    return {"type": "bitmap", "file": file, "ascent": ascent, "height": height, "chars": chars}


def _vanilla():
    # "A" is 8px wide, the check mark is 1px wide
    return FakeSource("vanilla", vanilla=True, fonts={
        "minecraft:include/default": font_json_bytes([_bitmap("minecraft:font/base.png", ["A✔"])]),
    }, textures={
        "minecraft:font/base.png": make_png_bytes(16, 8, block(0, 0, 8, 8) + block(8, 0, 1, 8)),
    })


def _build(stack, unifont=None):
    vanilla_raw = stack.sources[0].get_font_json("minecraft:include/default")
    providers = parse_json_providers(vanilla_raw, stack, layer_name="vanilla")
    slice_provider_tiles(providers)
    providers += collect_pack_providers(stack)
    return build_glyph_map(providers, unifont, stack)


def test_pack_beats_vanilla_and_vanilla_remains_fallback():
    pack = FakeSource("pack1", fonts={
        "minecraft:default": font_json_bytes([_bitmap("sky:icons.png", ["✔"])]),
    }, textures={
        "sky:icons.png": make_png_bytes(16, 8, block(0, 0, 3, 8) + block(8, 0, 2, 8)),
    })
    glyph_map = _build(AssetStack([_vanilla(), pack]))

    assert glyph_map["Regular"][0x2714]["pixels"]["width"] == 3  # pack override
    assert glyph_map["Regular"][0x2714]["layer"] == "pack1"
    assert glyph_map["Regular"][ord("A")]["pixels"]["width"] == 8  # vanilla fallback
    assert glyph_map["Regular"][0xE000]["pixels"]["width"] == 2  # new pack codepoint


def test_later_pack_beats_earlier_pack():
    def pack(name, ink_width):
        return FakeSource(name, fonts={
            "minecraft:default": font_json_bytes([_bitmap(f"{name}:icons.png", ["✔"])]),
        }, textures={
            f"{name}:icons.png": make_png_bytes(8, 8, block(0, 0, ink_width, 8)),
        })

    glyph_map = _build(AssetStack([_vanilla(), pack("pack1", 4), pack("pack2", 6)]))
    assert glyph_map["Regular"][0x2714]["pixels"]["width"] == 6
    assert glyph_map["Regular"][0x2714]["layer"] == "pack2"


def test_intra_pack_first_provider_wins():
    pack = FakeSource("pack1", fonts={
        "minecraft:default": font_json_bytes([
            _bitmap("pack1:first.png", [""]),
            _bitmap("pack1:second.png", [""]),
        ]),
    }, textures={
        "pack1:first.png": make_png_bytes(8, 8, block(0, 0, 2, 8)),
        "pack1:second.png": make_png_bytes(8, 8, block(0, 0, 5, 8)),
    })
    glyph_map = _build(AssetStack([_vanilla(), pack]))
    assert glyph_map["Regular"][0xE001]["pixels"]["width"] == 2


def test_pack_include_layer_participates_but_loses_to_default_layers():
    pack = FakeSource("pack1", fonts={
        "minecraft:include/default": font_json_bytes([_bitmap("pack1:inc.png", ["✔"])]),
        "minecraft:default": font_json_bytes([_bitmap("pack1:def.png", ["✔"])]),
    }, textures={
        "pack1:inc.png": make_png_bytes(16, 8, block(0, 0, 4, 8) + block(8, 0, 3, 8)),
        "pack1:def.png": make_png_bytes(8, 8, block(0, 0, 6, 8)),
    })
    glyph_map = _build(AssetStack([_vanilla(), pack]))

    assert glyph_map["Regular"][0x2714]["pixels"]["width"] == 6  # default.json layer wins
    assert glyph_map["Regular"][0xE002]["pixels"]["width"] == 3  # include layer still contributes


def test_unifont_still_only_fills_gaps():
    pack = FakeSource("pack1", fonts={
        "minecraft:default": font_json_bytes([_bitmap("sky:icons.png", ["✔"])]),
    }, textures={
        "sky:icons.png": make_png_bytes(8, 8, block(0, 0, 3, 8)),
    })
    unifont_rows = [[1] * 8 for _ in range(16)]
    glyph_map = _build(AssetStack([_vanilla(), pack]), unifont={0x2714: unifont_rows, 0x00C0: unifont_rows})

    assert glyph_map["Regular"][0x2714]["source"] == "provider"
    assert glyph_map["Regular"][0x00C0]["source"] == "unifont"


def test_unknown_font_ids_are_reported(capsys):
    pack = FakeSource("pack1", fonts={
        "hypixel:custom": font_json_bytes([]),
    })
    collect_pack_providers(AssetStack([_vanilla(), pack]))
    assert "hypixel:custom" in capsys.readouterr().out


def test_malformed_pack_font_json_is_skipped(capsys):
    bad_pack = FakeSource("badpack", fonts={
        "minecraft:default": b"{not json",
    })
    good_pack = FakeSource("goodpack", fonts={
        "minecraft:default": font_json_bytes([_bitmap("goodpack:icons.png", ["✔"])]),
    }, textures={
        "goodpack:icons.png": make_png_bytes(8, 8, block(0, 0, 4, 8)),
    })

    providers = collect_pack_providers(AssetStack([_vanilla(), bad_pack, good_pack]))

    assert len(providers) == 1
    assert providers[0]["layer"] == "goodpack"
    assert len(providers[0]["tiles"]) > 0
    assert "badpack" in capsys.readouterr().out
