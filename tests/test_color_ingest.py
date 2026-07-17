import io

import numpy as np
import pytest
from PIL import Image, ImageFile

import minecraft_fontgen.config as config
import minecraft_fontgen.file_io as file_io
from minecraft_fontgen.asset_source import AssetStack, DirAssetSource, ZipAssetSource
from minecraft_fontgen.file_io import (
    collect_color_providers,
    collect_pack_providers,
    load_provider_rgba,
    parse_json_providers,
    parse_space_provider,
    slice_provider_tiles,
)

from helpers import (
    FakeSource,
    font_json_bytes,
    write_pack_dir,
    write_pack_zip,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _stack(textures):
    return AssetStack([FakeSource("skypack", textures=textures)])


def _color_cell_png(top=(220, 40, 40, 255), bottom=(40, 60, 220, 255), width=8, height=8):
    """A flat two-colour cell: guaranteed to classify raster."""
    arr = np.zeros((height, width, 4), np.uint8)
    arr[:, : width // 2] = top
    arr[:, width // 2:] = bottom
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, "PNG")
    return buf.getvalue()


def _bitmap_provider(ref, char, ascent=7, height=8):
    return {"type": "bitmap", "file": ref, "ascent": ascent, "height": height, "chars": [char]}


# ---------------------------------------------------------------------------
# font id enumeration
# ---------------------------------------------------------------------------

def test_list_font_ids_dir_and_zip_parity(tmp_path):
    files = {
        "pack.mcmeta": b'{"pack": {"pack_format": 88}}',
        "assets/minecraft/font/default.json": font_json_bytes([]),
        "assets/wy/font/hud/portrait.json": font_json_bytes([]),
        "assets/wy/font/icons.json": font_json_bytes([]),
    }
    dir_source = DirAssetSource(write_pack_dir(tmp_path / "d", files), "d")
    zip_source = ZipAssetSource(write_pack_zip(tmp_path / "z.zip", files), "z")

    expected = ["minecraft:default", "wy:hud/portrait", "wy:icons"]
    assert sorted(dir_source.list_font_ids()) == expected
    assert sorted(zip_source.list_font_ids()) == expected
    zip_source.close()


def test_dir_source_font_dir_with_nested_and_non_json(tmp_path):
    files = {
        "assets/wy/font/a.json": font_json_bytes([]),
        "assets/wy/font/sub/b.json": font_json_bytes([]),
        "assets/wy/font/notes.txt": b"not a font",
        "assets/wy/font/sub/readme.md": b"ignore me",
    }
    source = DirAssetSource(write_pack_dir(tmp_path / "d", files), "d")
    # nested paths are walked, non-json files are ignored
    assert sorted(source.list_font_ids()) == ["wy:a", "wy:sub/b"]


def test_color_font_layers_deterministic():
    pack1 = FakeSource("p1", fonts={"wy:z": font_json_bytes([]), "wy:a": font_json_bytes([])})
    pack2 = FakeSource("p2", fonts={"mc:b": font_json_bytes([])})
    stack = AssetStack([FakeSource("vanilla", vanilla=True), pack1, pack2])

    layers = stack.color_font_layers()
    # vanilla excluded; pack order preserved; font ids sorted within a pack
    assert [(name, fid) for name, fid, _ in layers] == [
        ("p1", "wy:a"), ("p1", "wy:z"), ("p2", "mc:b")]
    # deterministic across calls
    assert stack.color_font_layers() == layers


def test_pack_qualified_when_two_packs_same_font_id():
    pack1 = FakeSource("p1", fonts={"ns:shared": font_json_bytes([])})
    pack2 = FakeSource("p2", fonts={"ns:shared": font_json_bytes([])})
    stack = AssetStack([pack1, pack2])

    layers = stack.color_font_layers()
    # the same font id in two packs is qualified by pack name, never merged
    assert [(name, fid) for name, fid, _ in layers] == [
        ("p1", "ns:shared"), ("p2", "ns:shared")]


def test_list_font_ids_collected_not_warnskipped(capsys, monkeypatch):
    monkeypatch.setattr(config, "SILENT_LOG", False)
    pack = FakeSource("wy", fonts={"wy:icons": font_json_bytes([])})
    stack = AssetStack([FakeSource("vanilla", vanilla=True), pack])

    # mono mode still warns that the tool does not build this font id
    monkeypatch.setattr(config, "COLOR_GLYPHS", False)
    collect_pack_providers(stack)
    assert "does not build" in capsys.readouterr().out

    # colour mode ingests it independently, so the warning is silenced
    monkeypatch.setattr(config, "COLOR_GLYPHS", True)
    collect_pack_providers(stack)
    assert "does not build" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# font id stamping
# ---------------------------------------------------------------------------

def test_parse_json_providers_font_id_default_none():
    textures = {"sky:ok.png": _color_cell_png()}
    raw = font_json_bytes([_bitmap_provider("sky:ok.png", "A")])

    providers = parse_json_providers(raw, _stack(textures), layer_name="skypack")
    assert providers[0]["font_id"] is None

    slice_provider_tiles(providers)
    assert providers[0]["tiles"][0]["font_id"] is None


def test_font_id_stamped_on_provider_and_tile():
    textures = {"wy:font/a.png": _color_cell_png()}
    raw = font_json_bytes([_bitmap_provider("wy:font/a.png", "")])

    providers = parse_json_providers(
        raw, _stack(textures), layer_name="wy", font_id="wy:custom", color_mode=True)
    assert providers[0]["font_id"] == "wy:custom"

    slice_provider_tiles(providers, color_mode=True)
    tile = providers[0]["tiles"][0]
    assert tile["font_id"] == "wy:custom"
    assert tile["codepoint"] == 0xE000


def test_font_id_collision_distinguishable():
    # same PUA codepoint, different art, in two different font files
    textures = {
        "wy:font/red.png": _color_cell_png(top=(220, 40, 40, 255), bottom=(40, 60, 220, 255)),
        "wy:font/green.png": _color_cell_png(top=(30, 180, 60, 255), bottom=(200, 120, 30, 255)),
    }
    stack = _stack(textures)
    raw_a = font_json_bytes([_bitmap_provider("wy:font/red.png", "")])
    raw_b = font_json_bytes([_bitmap_provider("wy:font/green.png", "")])

    providers_a = parse_json_providers(raw_a, stack, layer_name="wy", font_id="wy:one", color_mode=True)
    providers_b = parse_json_providers(raw_b, stack, layer_name="wy", font_id="wy:two", color_mode=True)
    slice_provider_tiles(providers_a, color_mode=True)
    slice_provider_tiles(providers_b, color_mode=True)

    tile_a = providers_a[0]["tiles"][0]
    tile_b = providers_b[0]["tiles"][0]
    # identical codepoint, distinct font id, and distinct raster art
    assert tile_a["codepoint"] == tile_b["codepoint"] == 0xE000
    assert tile_a["font_id"] == "wy:one"
    assert tile_b["font_id"] == "wy:two"
    assert tile_a["render_mode"] == tile_b["render_mode"] == "raster"
    assert tile_a["content_hash"] != tile_b["content_hash"]


# ---------------------------------------------------------------------------
# space providers
# ---------------------------------------------------------------------------

def test_space_provider_advances_signed_and_fractional():
    provider = {
        "type": "space",
        "advances": {
            chr(0xE010): -16384,   # signed int, verbatim
            chr(0xE011): 4.0,      # float, verbatim
            chr(0xE012): 0.0,      # zero float, kept
            chr(0xE013): True,     # bool dropped (int subclass)
            "AB": 5,               # multi-char key dropped
            chr(0x0000): 3,        # null glyph dropped
        },
    }
    record = parse_space_provider(provider, "wy", "wy:spacing")

    assert record["type"] == "space"
    assert record["font_id"] == "wy:spacing"
    assert record["advances"] == [(0xE010, -16384), (0xE011, 4.0), (0xE012, 0.0)]
    # types are preserved exactly, not coerced
    kinds = {cp: type(v) for cp, v in record["advances"]}
    assert kinds[0xE010] is int
    assert kinds[0xE011] is float
    assert kinds[0xE012] is float


def test_space_provider_empty_returns_none():
    assert parse_space_provider({"type": "space"}, "wy", "wy:x") is None
    assert parse_space_provider({"type": "space", "advances": {}}, "wy", "wy:x") is None
    assert parse_space_provider({"type": "space", "advances": {"AB": 1}}, "wy", "wy:x") is None


def test_space_only_file_emits_no_tiles(monkeypatch):
    monkeypatch.setattr(config, "COLOR_GLYPHS", True)
    space_json = font_json_bytes([{"type": "space", "advances": {chr(0xE010): -8.0}}])
    pack = FakeSource("wy", fonts={"wy:spacing": space_json})
    stack = AssetStack([pack])

    providers = collect_color_providers(stack)

    # the space record is captured but nothing gets sliced into tiles
    assert len(providers) == 1
    assert providers[0]["type"] == "space"
    assert providers[0]["advances"] == [(0xE010, -8.0)]
    assert all("tiles" not in p for p in providers)


# ---------------------------------------------------------------------------
# non-bitmap dispatch
# ---------------------------------------------------------------------------

def test_reference_provider_not_followed(capsys, monkeypatch):
    monkeypatch.setattr(config, "SILENT_LOG", False)
    raw = font_json_bytes([{"type": "reference", "id": "wy:other"}])

    providers = parse_json_providers(raw, layer_name="wy", font_id="wy:main", color_mode=True)

    # the reference is logged and dropped, never expanded
    assert providers == []
    out = capsys.readouterr().out
    assert "Reference provider" in out
    assert "not following" in out


def test_ttf_and_unsupported_skipped(capsys, monkeypatch):
    monkeypatch.setattr(config, "SILENT_LOG", False)
    raw = font_json_bytes([
        {"type": "ttf", "file": "wy:font/custom.ttf"},
        {"type": "legacy_unicode", "sizes": "wy:font/sizes.bin", "template": "wy:font/%s.png"},
        {"type": "made_up", "whatever": 1},
    ])

    providers = parse_json_providers(raw, layer_name="wy", font_id="wy:main", color_mode=True)

    assert providers == []
    out = capsys.readouterr().out
    assert "ttf" in out
    assert "legacy_unicode" in out
    assert "made_up" in out


def test_flag_off_is_byte_identical(capsys, monkeypatch):
    monkeypatch.setattr(config, "SILENT_LOG", False)
    textures = {"sky:ok.png": _color_cell_png()}
    raw = font_json_bytes([
        {"type": "space", "advances": {chr(0xE010): -4.0}},
        _bitmap_provider("sky:ok.png", "A"),
    ])

    providers = parse_json_providers(raw, _stack(textures), layer_name="skypack")

    # flag off: the space provider is warn-skipped exactly as before, only the
    # bitmap survives, and its font id stays inert None
    assert len(providers) == 1
    assert "type" not in providers[0]  # emitted bitmap providers carry no type key
    assert providers[0]["name"]
    assert providers[0]["font_id"] is None
    assert "unsupported 'space'" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# texture decode robustness
# ---------------------------------------------------------------------------

def _truncated_png_bytes():
    """A valid two-colour PNG cut off mid-IDAT (no IEND): the exact shape the
    reference (HD) packs ship, which a strict decoder rejects."""
    arr = np.zeros((8, 8, 4), np.uint8)
    arr[:, :4] = (220, 40, 40, 255)
    arr[:, 4:] = (40, 60, 220, 255)
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, "PNG")
    good = buf.getvalue()
    return good[: good.find(b"IDAT") + 8]


def test_truncated_texture_decodes_not_fatal(tmp_path):
    # The reference packs' font textures carry truncated zlib streams that a strict
    # Pillow rejects; load_provider_rgba must recover the art rather than abort.
    path = tmp_path / "trunc.png"
    path.write_bytes(_truncated_png_bytes())

    # prove the fixture actually needs the tolerance: strict Pillow rejects it
    saved = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        with pytest.raises(OSError):
            Image.open(str(path)).convert("RGBA").load()
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = saved

    # the module enables the tolerance at import, so the real decode succeeds
    image = load_provider_rgba({"name": "trunc", "file_path": str(path)})
    assert image is not None
    assert image.size == (8, 8)


def test_corrupt_texture_warnskips_not_fatal(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(config, "SILENT_LOG", False)
    monkeypatch.setattr(config, "COLOR_GLYPHS", True)
    files = {
        "pack.mcmeta": b'{"pack": {"pack_format": 88}}',
        "assets/wy/font/icons.json": font_json_bytes([
            {"type": "bitmap", "file": "wy:font/broken.png",
             "ascent": 7, "height": 8, "chars": [chr(0xE000)]},
        ]),
        "assets/wy/textures/font/broken.png": b"this is not a valid png at all",
    }
    source = DirAssetSource(write_pack_dir(tmp_path / "d", files), "d")
    stack = AssetStack([source])

    # a single undecodable texture must warn-skip, never abort the whole colour pass
    providers = collect_color_providers(stack)
    tiles = [t for p in providers for t in p.get("tiles", [])]
    assert tiles == []
    assert "failed to decode" in capsys.readouterr().out
