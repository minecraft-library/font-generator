"""M7: colour end to end over a synthetic pack, plus the COLR/CBDT non-goal pins.

A synthetic pack (no real HD-pack assets) carries one colour font id with a mono
letter cell, a two-colour icon, a 256px cell, and a space provider. The colour
pass must drop the mono cell, raster the two colour cells into per-strike sbix
PNGs that round-trip pixel-for-pixel, and emit a deterministic sidecar whose gids
line up with the compiled glyph order. The mono OpenType product is built from the
same pack and stays free of the raster codepoints."""
import io
import json
import os

import numpy as np
from PIL import Image
from fontTools.ttLib import TTFont

import minecraft_fontgen.config as config
from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.colour_sidecar import build_sidecar, write_sidecar
from minecraft_fontgen.config import FONT_STYLES, OUTPUT_FONT_NAME
from minecraft_fontgen.file_io import (
    build_color_glyph_map,
    build_glyph_map,
    collect_color_providers,
    collect_pack_providers,
    group_color_space_rows,
)
from minecraft_fontgen.font_creator import create_color_font_files, create_font_files
from minecraft_fontgen.functions import resolve_source_date_epoch

from helpers import (
    FakeSource,
    block,
    color_pack_source,
    font_json_bytes,
    make_color_png_bytes,
    make_png_bytes,
    two_color_block_png,
)

CP_LETTER = 0x0041      # mono 'A' cell -> stays mono, no strike
CP_ICON = 0xE000        # two-colour icon -> raster, 8px strike
CP_TALL = 0xE001        # 256px cell -> raster, its own strike
CP_SPACE = 0xE100       # space provider advance -> sidecar-only


def _solid_png(size, rgba):
    return make_color_png_bytes(size, size, {(x, y): rgba for x in range(size) for y in range(size)})


def _demo_pack():
    """A pack whose 'sky:icons' colour font mixes a mono letter, two raster cells,
    and a space provider; its minecraft:default carries a plain mono letter."""
    icon_png = two_color_block_png(8, 8)
    tall_png = _solid_png(256, (30, 200, 90, 255))
    letter_png = make_png_bytes(8, 8, block(1, 0, 5, 8))  # single opaque colour -> mono

    icons = color_pack_source(
        "sky:icons",
        cells={
            "sky:icons/letter.png": (chr(CP_LETTER), letter_png),
            "sky:icons/icon.png": (chr(CP_ICON), icon_png),
            "sky:icons/tall.png": (chr(CP_TALL), tall_png),
        },
        space_advances={chr(CP_SPACE): -16384},
        name="skypack",
    )
    # add a default-font mono letter to the same source for the mono build
    icons.fonts["minecraft:default"] = font_json_bytes([
        {"type": "bitmap", "file": "sky:font/base.png", "ascent": 7, "height": 8, "chars": ["Z"]},
    ])
    icons.textures["sky:font/base.png"] = make_png_bytes(8, 8, block(0, 0, 6, 8))
    return icons


def _decode_strike(font, codepoint):
    """Returns the decoded RGBA image embedded for a codepoint's glyph, across strikes."""
    name = font.getBestCmap()[codepoint]
    for strike in font["sbix"].strikes.values():
        sbix_glyph = strike.glyphs.get(name)
        if sbix_glyph is not None and sbix_glyph.imageData:
            return Image.open(io.BytesIO(sbix_glyph.imageData)).convert("RGBA")
    raise AssertionError(f"no strike carried an image for U+{codepoint:04X}")


def test_color_end_to_end(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.setattr(config, "COLOR_GLYPHS", True)
    os.makedirs("out", exist_ok=True)

    pack = _demo_pack()
    stack = AssetStack([FakeSource("vanilla", vanilla=True), pack])

    # --- mono product (unchanged, additive): the letters build, no raster leaks ---
    mono_providers = collect_pack_providers(stack)
    glyph_map = build_glyph_map(mono_providers, None, stack)
    styles = [dict(s) for s in FONT_STYLES if s["name"] == "Regular"]
    mono_files = create_font_files(glyph_map, True, styles, "out", OUTPUT_FONT_NAME, "otf")
    mono = TTFont(mono_files[0])
    assert ord("Z") in mono.getBestCmap()
    assert "sbix" not in mono
    assert "COLR" not in mono

    # --- colour product ---
    color_providers = collect_color_providers(stack)
    color_map = build_color_glyph_map(color_providers)
    space_by_font_id = group_color_space_rows(color_providers)

    # the classifier dropped the mono letter; only the two raster cells remain
    assert set(color_map["sky:icons"]) == {CP_ICON, CP_TALL}

    color_files, storages = create_color_font_files(
        color_map, space_by_font_id, "out", OUTPUT_FONT_NAME)
    assert len(color_files) == 1
    path, font_id = color_files[0]
    assert font_id == "sky:icons"

    font = TTFont(path)
    assert "sbix" in font
    cmap = font.getBestCmap()
    assert CP_ICON in cmap and CP_TALL in cmap
    assert CP_LETTER not in cmap  # the mono cell minted no colour glyph

    # strikes round-trip pixel-for-pixel against the source cells
    assert np.array_equal(
        np.array(_decode_strike(font, CP_ICON)),
        np.array(Image.open(io.BytesIO(two_color_block_png(8, 8))).convert("RGBA")))
    assert np.array_equal(
        np.array(_decode_strike(font, CP_TALL)),
        np.array(Image.open(io.BytesIO(_solid_png(256, (30, 200, 90, 255)))).convert("RGBA")))

    # --- sidecar ---
    fonts = [{"font_id": fid, "file": os.path.basename(p)} for p, fid in color_files]
    sidecar = build_sidecar(fonts, storages, resolve_source_date_epoch())
    write_sidecar(sidecar, "out")

    by_cp = {g["codepoint"]: g for g in sidecar["glyphs"]}
    assert set(by_cp) == {CP_ICON, CP_TALL, CP_SPACE}
    # space row: no glyph, signed advance carried verbatim
    assert by_cp[CP_SPACE]["glyph_name"] is None
    assert by_cp[CP_SPACE]["gid"] is None
    assert by_cp[CP_SPACE]["advance"] == -16384
    # glyph rows: gid lines up with the compiled glyph order at that codepoint
    order = font.getGlyphOrder()
    for cp in (CP_ICON, CP_TALL):
        assert order[by_cp[cp]["gid"]] == cmap[cp]

    # sidecar on disk parses back to the same object
    with open("out/colour-glyphs.json", encoding="utf-8") as f:
        assert json.load(f) == sidecar


def test_color_end_to_end_deterministic(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.setattr(config, "COLOR_GLYPHS", True)

    def _build(outdir):
        os.makedirs(outdir, exist_ok=True)
        stack = AssetStack([FakeSource("vanilla", vanilla=True), _demo_pack()])
        color_providers = collect_color_providers(stack)
        color_map = build_color_glyph_map(color_providers)
        space = group_color_space_rows(color_providers)
        files, storages = create_color_font_files(color_map, space, outdir, OUTPUT_FONT_NAME)
        fonts = [{"font_id": fid, "file": os.path.basename(p)} for p, fid in files]
        sidecar = build_sidecar(fonts, storages, resolve_source_date_epoch())
        with open(files[0][0], "rb") as f:
            return f.read(), json.dumps(sidecar, ensure_ascii=False, indent=2)

    font_a, json_a = _build("a")
    font_b, json_b = _build("b")
    assert font_a == font_b
    assert json_a == json_b


def test_color_off_output_byte_identical(monkeypatch):
    # The central additive-track guarantee: running the colour pass must not perturb
    # the mono product one byte. Same synthetic pack, same fixed epoch, same mono
    # TTF - the only difference is whether the colour ingestion runs alongside it.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")

    def build_mono(color_on, outdir):
        monkeypatch.setattr(config, "COLOR_GLYPHS", color_on)
        os.makedirs(outdir, exist_ok=True)
        stack = AssetStack([FakeSource("vanilla", vanilla=True), _demo_pack()])
        mono_providers = collect_pack_providers(stack)
        if color_on:
            # the colour ingestion runs in the same phase as the mono parse/slice;
            # its side effects must not leak into the mono compilation
            collect_color_providers(stack)
        glyph_map = build_glyph_map(mono_providers, None, stack)
        styles = [dict(s) for s in FONT_STYLES if s["name"] == "Regular"]
        files = create_font_files(glyph_map, False, styles, outdir, OUTPUT_FONT_NAME, "ttf")
        with open(files[0], "rb") as f:
            return f.read()

    assert build_mono(False, "mono_off") == build_mono(True, "mono_on")


def test_colr_not_emitted(tmp_path):
    from helpers import make_raster_tile

    color_map = build_color_glyph_map([{"tiles": [
        make_raster_tile(CP_ICON, Image.open(io.BytesIO(two_color_block_png(8, 8))).convert("RGBA"),
                         8, 7, font_id="sky:icons"),
    ]}])
    files, _ = create_color_font_files(color_map, {}, str(tmp_path), OUTPUT_FONT_NAME)
    font = TTFont(files[0][0])
    for banned in ("COLR", "CPAL", "CBDT", "CBLC"):
        assert banned not in font
    assert "sbix" in font


def test_color_fixture_helper():
    # make_color_png_bytes yields a real colour cell with >= 2 distinct opaque colours
    png = two_color_block_png(8, 8)
    arr = np.array(Image.open(io.BytesIO(png)).convert("RGBA"))
    opaque = arr[arr[:, :, 3] == 255]
    distinct = {tuple(px) for px in opaque}
    assert len(distinct) >= 2
    # and it splices no tEXt marker (unlike make_png_bytes)
    assert b"tEXt" not in png
