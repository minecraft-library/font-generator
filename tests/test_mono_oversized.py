"""A mono glyph whose scaled outline runs past the int16 glyf/CFF range - e.g. a
320px default-font pack cell, which --color-glyphs forces through the TrueType mono
path - is dropped from the mono font instead of aborting the whole save. glyf stores
point coordinates and their point-to-point deltas as int16, so such an outline cannot
be encoded at all; the faithful art still ships in the colour font. Ordinary glyphs are
untouched, so a build that already compiled is byte-for-byte unchanged."""
import os

import minecraft_fontgen.config as config
from fontTools.ttLib import TTFont

from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.config import FONT_STYLES, INT16_MAX
from minecraft_fontgen.file_io import build_glyph_map, collect_pack_providers
from minecraft_fontgen.font_creator import create_font_files

from helpers import FakeSource, block, font_json_bytes, make_png_bytes


def _regular_only():
    return [dict(s) for s in FONT_STYLES if s["name"] == "Regular"]


def _wide_pack():
    # 0xE000 is a 320px-wide default-font cell -> 40960 font units, far past int16.
    # 0xE001 is an ordinary 5px glyph that must survive the same font.
    return FakeSource("wide", fonts={
        "minecraft:default": font_json_bytes([
            {"type": "bitmap", "file": "sky:wide.png", "ascent": 7, "height": 8, "chars": [chr(0xE000)]},
            {"type": "bitmap", "file": "sky:ok.png", "ascent": 7, "height": 8, "chars": [chr(0xE001)]},
        ]),
    }, textures={
        "sky:wide.png": make_png_bytes(320, 8, block(0, 0, 320, 8)),
        "sky:ok.png": make_png_bytes(8, 8, block(0, 0, 5, 6)),
    })


def test_oversized_mono_glyph_skipped_not_fatal(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(config, "SILENT_LOG", False)
    stack = AssetStack([FakeSource("vanilla", vanilla=True), _wide_pack()])
    glyph_map = build_glyph_map(collect_pack_providers(stack), None, stack)

    # TrueType output is the mode --color-glyphs coerces the mono styles into.
    files, _ = create_font_files(glyph_map, False, _regular_only(), str(tmp_path),
                                 "Minecraft", "ttf")

    # the save completed and produced the mono TrueType font
    assert files and os.path.basename(files[0]) == "Minecraft-Regular.ttf"
    assert "Skipping U+E000" in capsys.readouterr().out

    font = TTFont(files[0])
    cmap = font.getBestCmap()
    assert 0xE000 not in cmap  # the oversized glyph was dropped
    assert 0xE001 in cmap      # the ordinary glyph survived
    # head bbox stays inside the int16 range because nothing oversized reached it
    head = font["head"]
    assert head.xMax <= INT16_MAX and head.yMax <= INT16_MAX


def test_oversized_mono_glyph_also_skipped_for_opentype(tmp_path):
    # The same outline cannot be written to CFF either (head's FontBBox is int16), so
    # the skip is format-agnostic: an OpenType build with the same wide cell survives.
    stack = AssetStack([FakeSource("vanilla", vanilla=True), _wide_pack()])
    glyph_map = build_glyph_map(collect_pack_providers(stack), None, stack)

    files, _ = create_font_files(glyph_map, True, _regular_only(), str(tmp_path),
                                 "Minecraft", "otf")

    assert files and os.path.basename(files[0]) == "Minecraft-Regular.otf"
    cmap = TTFont(files[0]).getBestCmap()
    assert 0xE000 not in cmap
    assert 0xE001 in cmap
