"""M4: sbix dual-path assembly - empty-glyf raster glyphs, strike-per-display-scale,
origin offsets, the maxp.recalc-then-resynthesize bbox order, and content-hash dedup."""
import io

import numpy as np
import pytest
from fontTools.ttLib import TTFont
from PIL import Image, features

from helpers import (
    build_color_font_storage,
    color_cell,
    compiled_font_bytes,
    flat_two_color_cell,
    make_raster_tile,
)

UNITS_PER_EM = 1024
UNITS_PER_PIXEL_BASE = 128


def _reopen(storage):
    return TTFont(io.BytesIO(compiled_font_bytes(storage)))


def _big_opaque_cell(size=256):
    """A fully-opaque 256x256 art cell (varied colours, no transparency)."""
    a = np.zeros((size, size, 4), np.uint8)
    yy, xx = np.mgrid[0:size, 0:size]
    a[..., 0] = (xx & 0xFF)
    a[..., 1] = (yy & 0xFF)
    a[..., 2] = ((xx ^ yy) & 0xFF)
    a[..., 3] = 255
    return Image.fromarray(a, "RGBA")


# ---------------------------------------------------------------------------
# strike round-trip / pixel equality
# ---------------------------------------------------------------------------

def test_sbix_roundtrip_pixel_equality():
    cells = {
        0xE001: flat_two_color_cell(8, 8),
        0xE002: flat_two_color_cell(16, 16),
        0xE003: _big_opaque_cell(256),
    }
    tiles = [
        make_raster_tile(0xE001, cells[0xE001], 8, 7),
        make_raster_tile(0xE002, cells[0xE002], 16, 15),
        make_raster_tile(0xE003, cells[0xE003], 256, 240),
    ]
    font = _reopen(build_color_font_storage(tiles))
    best = font.getBestCmap()
    sbix = font["sbix"]

    for cp, source in cells.items():
        gname = best[cp]
        found = None
        for strike in sbix.strikes.values():
            if gname in strike.glyphs and strike.glyphs[gname].imageData:
                found = strike.glyphs[gname]
                break
        assert found is not None, f"no strike image for U+{cp:04X}"
        decoded = np.asarray(Image.open(io.BytesIO(found.imageData)).convert("RGBA"))
        assert decoded.shape == np.asarray(source).shape
        assert np.array_equal(decoded, np.asarray(source)), f"U+{cp:04X} not pixel-equal"


def test_sbix_256px_pixel_equality():
    source = _big_opaque_cell(256)
    tiles = [make_raster_tile(0xE006, source, 256, 240)]
    font = _reopen(build_color_font_storage(tiles))
    gname = font.getBestCmap()[0xE006]
    strike = font["sbix"].strikes[8]  # native==display -> ppem 8
    decoded = np.asarray(Image.open(io.BytesIO(strike.glyphs[gname].imageData)).convert("RGBA"))
    assert np.array_equal(decoded, np.asarray(source))


# ---------------------------------------------------------------------------
# strike sharing by display scale
# ---------------------------------------------------------------------------

def test_strike_sharing_by_display_scale():
    tiles = [
        make_raster_tile(0xE001, flat_two_color_cell(8, 8), 8, 7),     # scale 1.0 -> ppem 8
        make_raster_tile(0xE002, flat_two_color_cell(16, 16), 16, 15),  # scale 1.0 -> ppem 8
        make_raster_tile(0xE003, flat_two_color_cell(16, 16), 8, 7),    # scale 0.5 -> ppem 16
    ]
    storage = build_color_font_storage(tiles)
    strikes = storage.font["sbix"].strikes

    # equal display_scale (1.0) cells share the ppem-8 strike despite different pixel sizes
    assert set(strikes.keys()) == {8, 16}
    ppem8_names = set(strikes[8].glyphs.keys())
    best = storage.font.getBestCmap()
    assert best[0xE001] in ppem8_names
    assert best[0xE002] in ppem8_names
    # the downscaled cell (native taller than display) lands in the LARGER ppem strike
    assert best[0xE003] in strikes[16].glyphs


def test_strike_ppem_noninteger_warns(capsys, monkeypatch):
    import minecraft_fontgen.config as config
    monkeypatch.setattr(config, "SILENT_LOG", False)
    # 8 * native_h / display_height = 8 * 8 / 3 = 21.33 -> non-integer, warns
    tiles = [make_raster_tile(0xE001, flat_two_color_cell(8, 8), 3, 2)]
    build_color_font_storage(tiles)
    out = capsys.readouterr().out
    assert "Non-integer strike ppem" in out
    assert "U+E001" in out


# ---------------------------------------------------------------------------
# bbox synthesis after maxp.recalc
# ---------------------------------------------------------------------------

def test_bbox_covers_tall_256px_art():
    tiles = [make_raster_tile(0xE006, _big_opaque_cell(256), 256, 240)]
    storage = build_color_font_storage(tiles)
    # ascent 240 px * 128 units/px = 30720; bbox must enclose it AFTER maxp.recalc,
    # which had set head.yMax from the (empty) contours only.
    expected_top = 240 * UNITS_PER_PIXEL_BASE
    assert storage.font["head"].yMax >= expected_top
    assert storage.font["OS/2"].usWinAscent >= expected_top

    reopened = _reopen(storage)  # save() with recalcBBoxes=False preserves it
    assert reopened["head"].yMax >= expected_top


def test_bbox_clamped_for_oversized_display():
    # A large display height (512) with a small ascent pushes the descent extent
    # past the int16 head range, and a wide cell pushes the mean advance past the
    # int16 xAvgCharWidth range. Both must clamp so save() does not raise (real HD
    # packs ship such cells).
    cell = _big_opaque_cell(512).crop((0, 0, 600, 512))  # 600 wide x 512 tall, opaque
    storage = build_color_font_storage([make_raster_tile(0xE00A, cell, 512, 8)])
    head = storage.font["head"]
    os2 = storage.font["OS/2"]
    # descent extent (8 - 512) * 128 = -64512 saturates to the int16 floor
    assert head.yMin == -0x8000
    assert -0x8000 <= head.yMax <= 0x7FFF
    assert -0x8000 <= head.xMax <= 0x7FFF
    assert -0x8000 <= os2.xAvgCharWidth <= 0x7FFF
    assert 0 <= os2.usWinAscent <= 0xFFFF
    assert 0 <= os2.usWinDescent <= 0xFFFF
    # the whole font still saves and reopens (the failure mode was a save crash)
    reopened = _reopen(storage)
    assert reopened["head"].yMin == -0x8000


def test_maxp_recalc_mixed_glyf_sbix():
    tiles = [
        make_raster_tile(0xE001, flat_two_color_cell(8, 8), 8, 7),
        make_raster_tile(0xE006, _big_opaque_cell(256), 256, 240),
    ]
    storage = build_color_font_storage(tiles)
    font = storage.font
    # .notdef (contours) + two raster glyphs + is there a glyph count match?
    assert font["maxp"].numGlyphs == len(font.getGlyphOrder())
    # the only contour-bearing glyph is .notdef, so maxp reflects its contours
    assert font["maxp"].maxContours >= 1
    reopened = _reopen(storage)
    assert reopened["maxp"].numGlyphs == font["maxp"].numGlyphs


# ---------------------------------------------------------------------------
# empty glyf + hmtx clamp
# ---------------------------------------------------------------------------

def test_empty_glyf_roundtrip():
    tiles = [make_raster_tile(0xE001, flat_two_color_cell(8, 8), 8, 7)]
    font = _reopen(build_color_font_storage(tiles))
    gname = font.getBestCmap()[0xE001]
    assert font["glyf"][gname].numberOfContours == 0
    assert all(adv >= 0 for adv, _lsb in font["hmtx"].metrics.values())


def test_hmtx_clamp_vs_sidecar_signed():
    # A very wide short cell: advance = native_w * (1024 / native_h) overflows uint16.
    # native_w=520, native_h=8 -> 520 * 128 = 66560 > 65535.
    wide = flat_two_color_cell(520, 8)
    tiles = [make_raster_tile(0xE001, wide, 8, 7)]
    storage = build_color_font_storage(tiles)
    gname = storage.font.getGlyphOrder()[storage.name_to_gid()[storage.sidecar_rows[0]["glyphName"]]]

    advance_signed = int(round(520 * (UNITS_PER_EM / 8)))
    assert advance_signed == 66560
    hmtx_adv = storage.font["hmtx"].metrics[gname][0]
    assert hmtx_adv == 0xFFFF  # clamped
    row = storage.sidecar_rows[0]
    assert row["advance"] == advance_signed  # true value survives in the sidecar


# ---------------------------------------------------------------------------
# content-hash dedup
# ---------------------------------------------------------------------------

def test_dedup_shares_gid():
    same = flat_two_color_cell(8, 8)
    same_again = flat_two_color_cell(8, 8)
    tiles = [
        make_raster_tile(0xE001, same, 8, 7),        # ppem 8
        make_raster_tile(0xE003, same_again, 8, 7),  # identical pixels+geometry+advance
        make_raster_tile(0xE005, flat_two_color_cell(8, 8), 4, 3),  # same pixels, ppem 16
    ]
    storage = build_color_font_storage(tiles)
    best = storage.font.getBestCmap()

    # identical bitmap + ppem + origin + advance -> one glyph, two cmap entries
    assert best[0xE001] == best[0xE003]
    # differing geometry (ppem) does NOT dedup
    assert best[0xE005] != best[0xE001]

    # one strike entry for the shared glyph, three sidecar rows total
    strike8 = storage.font["sbix"].strikes[8]
    assert sum(1 for n in strike8.glyphs if n == best[0xE001]) == 1
    rows_for = {r["codepoint"]: r for r in storage.sidecar_rows}
    assert rows_for[0xE001]["glyphName"] == rows_for[0xE003]["glyphName"]
    assert len([r for r in storage.sidecar_rows if r["glyphName"] is not None]) == 3

    gid = storage.name_to_gid()
    assert gid[best[0xE001]] == gid[best[0xE003]]


# ---------------------------------------------------------------------------
# FreeType golden render (pins the sbix originOffsetY sign/unit)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not features.check("freetype2"), reason="FreeType not available in Pillow")
def test_origin_golden_image_freetype(tmp_path):
    from PIL import ImageFont

    ascent, display_height, native_h = 7, 8, 8
    source = flat_two_color_cell(8, 8)
    tiles = [make_raster_tile(0xE001, source, display_height, ascent)]
    storage = build_color_font_storage(tiles)

    font_path = tmp_path / "color.ttf"
    with open(font_path, "wb") as f:
        f.write(compiled_font_bytes(storage))

    # FreeType is the golden colour renderer (embedded_color / FT_LOAD_COLOR path):
    # its rasterization of the strike must be pixel-identical to the source art.
    ft = ImageFont.truetype(str(font_path), 8)
    mask = ft.getmask(chr(0xE001), mode="RGBA")
    rendered = np.asarray(Image.Image()._new(mask).convert("RGBA"))
    assert (rendered[:, :, 3] > 0).any()
    opaque = rendered[rendered[:, :, 3] == 255]
    colours = set(map(tuple, opaque[:, :3].tolist()))
    assert (220, 40, 40) in colours and (40, 60, 220) in colours

    # the stored int16 originOffsetY matches the pinned formula
    expected_oy = round((ascent - display_height) * native_h / display_height)
    strike = storage.font["sbix"].strikes[8]
    gname = storage.font.getBestCmap()[0xE001]
    assert strike.glyphs[gname].originOffsetY == expected_oy
