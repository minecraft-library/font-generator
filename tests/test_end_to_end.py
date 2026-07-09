import os

from fontTools.ttLib import TTFont

from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.config import FONT_STYLES
from minecraft_fontgen.file_io import build_glyph_map, collect_pack_providers, parse_json_providers, slice_provider_tiles
from minecraft_fontgen.font_creator import create_font_files

from helpers import FakeSource, block, font_json_bytes, make_png_bytes


def test_pack_glyphs_flow_into_generated_fonts():
    vanilla = FakeSource("vanilla", vanilla=True, fonts={
        "minecraft:include/default": font_json_bytes([
            {"type": "bitmap", "file": "minecraft:font/base.png", "ascent": 7, "height": 8, "chars": ["A✔"]},
        ]),
    }, textures={
        "minecraft:font/base.png": make_png_bytes(16, 8, block(0, 0, 8, 8) + block(8, 0, 1, 8)),
    })
    pack = FakeSource("skypack", fonts={
        "minecraft:default": font_json_bytes([
            {"type": "bitmap", "file": "sky:gui/icons.png", "ascent": 7, "height": 7, "chars": ["✔"]},
            {"type": "bitmap", "file": "sky:gui/staff.png", "ascent": 7, "height": 7, "chars": ["ዞ"]},
        ]),
    }, textures={
        "sky:gui/icons.png": make_png_bytes(14, 7, block(0, 0, 5, 5) + block(7, 0, 3, 4)),
        "sky:gui/staff.png": make_png_bytes(3, 7, block(0, 0, 2, 7)),
    })
    stack = AssetStack([vanilla, pack])

    providers = parse_json_providers(
        vanilla.get_font_json("minecraft:include/default"), stack, layer_name="vanilla")
    slice_provider_tiles(providers)
    providers += collect_pack_providers(stack)
    glyph_map = build_glyph_map(providers, None, stack)

    styles = [dict(s) for s in FONT_STYLES if s["name"] in ("Regular", "Bold", "Italic")]
    os.makedirs("out", exist_ok=True)
    files = create_font_files(glyph_map, True, styles, "out", "Minecraft", "otf")

    assert sorted(os.path.basename(f) for f in files) == ["Minecraft-Bold.otf", "Minecraft-Italic.otf", "Minecraft-Regular.otf"]

    regular = TTFont(next(f for f in files if "Regular" in f))
    cmap = regular.getBestCmap()
    assert cmap[0xE000] == "uniE000"
    assert cmap[0x12DE] == "uni12DE"
    assert cmap[0x2714] == "uni2714"
    assert cmap[ord("A")] == "uni0041"

    hmtx = regular["hmtx"]
    assert hmtx["uni2714"][0] == 768   # pack's 5px check mark: (5 + 1) * 128, not vanilla's (1 + 1) * 128
    assert hmtx["uniE000"][0] == 512   # 3px icon: (3 + 1) * 128
    assert hmtx["uni12DE"][0] == 384   # 2px ink in the 3x7 tile: (2 + 1) * 128
    assert hmtx["uni0041"][0] == 1152  # vanilla 8px glyph: (8 + 1) * 128

    bold = TTFont(next(f for f in files if "Bold" in f))
    assert bold["hmtx"]["uniE000"][0] == 640  # 1px bold smear: (4 + 1) * 128

    italic = TTFont(next(f for f in files if "Italic" in f))
    italic_cmap = italic.getBestCmap()
    assert 0xE000 in italic_cmap and 0x12DE in italic_cmap
