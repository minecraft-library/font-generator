import os

import pytest

from minecraft_fontgen.asset_source import AssetStack
from minecraft_fontgen.file_io import parse_bin_providers, parse_json_providers

from helpers import FakeSource, block, font_json_bytes, make_png_bytes


def _stack(textures):
    return AssetStack([FakeSource("skypack", textures=textures)])


def test_parses_namespaced_provider_with_grid_geometry():
    textures = {"hypixel_skyblock:gui/stats.png": make_png_bytes(56, 42, block(0, 0, 7, 7))}
    raw = font_json_bytes([{
        "type": "bitmap",
        "file": "hypixel_skyblock:gui/stats.png",
        "ascent": 7,
        "height": 7,
        "chars": [""] * 6,
    }])

    providers = parse_json_providers(raw, _stack(textures), layer_name="skypack")

    assert len(providers) == 1
    provider = providers[0]
    assert provider["columns"] == 8
    assert provider["rows"] == 6
    assert provider["height"] == 7
    assert provider["ascent"] == 7
    assert provider["layer"] == "skypack"
    assert ":" not in provider["name"]
    assert os.path.isfile(provider["file_path"])
    assert os.path.isdir(provider["output"])


def test_work_dir_names_are_unique_per_provider_index():
    png = make_png_bytes(7, 7, block(0, 0, 3, 3))
    textures = {"sky:gui/icons.png": png}
    raw = font_json_bytes([
        {"type": "bitmap", "file": "sky:gui/icons.png", "ascent": 7, "height": 7, "chars": [""]},
        {"type": "bitmap", "file": "sky:gui/icons.png", "ascent": 0, "height": 7, "chars": [""]},
    ])
    providers = parse_json_providers(raw, _stack(textures), layer_name="skypack")
    assert len(providers) == 2
    assert providers[0]["name"] != providers[1]["name"]


def test_skips_invalid_providers_with_warnings(capsys):
    textures = {"sky:ok.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    raw = font_json_bytes([
        {"type": "space", "advances": {" ": 4}},
        {"type": "bitmap", "file": "sky:missing.png", "ascent": 7, "height": 8, "chars": ["a"]},
        {"type": "bitmap", "file": "sky:ok.png", "ascent": 7, "height": 8, "chars": ["ab", "c"]},
        {"type": "bitmap", "file": "sky:ok.png", "ascent": 9, "height": 8, "chars": ["a"]},
        {"type": "bitmap", "file": "sky:ok.png", "ascent": 7, "height": 8, "chars": ["a"]},
    ])

    providers = parse_json_providers(raw, _stack(textures), layer_name="skypack")

    out = capsys.readouterr().out
    assert len(providers) == 1
    assert "space" in out
    assert "not found" in out
    assert "unequal" in out
    assert "exceeds height" in out


@pytest.mark.parametrize("override", [
    {"height": "8"},
    {"chars": 42},
    {"chars": [[1, 2]]},
])
def test_wrong_typed_provider_fields_are_skipped(capsys, override):
    textures = {"sky:ok.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    provider = {"type": "bitmap", "file": "sky:ok.png", "ascent": 7, "height": 8, "chars": ["a"]}
    provider.update(override)
    raw = font_json_bytes([provider])

    providers = parse_json_providers(raw, _stack(textures), layer_name="skypack")

    assert len(providers) == 0
    assert "⚠️" in capsys.readouterr().out


def test_negative_ascent_is_accepted():
    textures = {"sky:below.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    raw = font_json_bytes([
        {"type": "bitmap", "file": "sky:below.png", "ascent": -2, "height": 8, "chars": ["a"]},
    ])
    providers = parse_json_providers(raw, _stack(textures), layer_name="skypack")
    assert providers[0]["ascent"] == -2


def test_bom_tolerated():
    textures = {"sky:ok.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    raw = b"\xef\xbb\xbf" + font_json_bytes([
        {"type": "bitmap", "file": "sky:ok.png", "ascent": 7, "height": 8, "chars": ["a"]},
    ])
    assert len(parse_json_providers(raw, _stack(textures), layer_name="skypack")) == 1


def test_bin_providers_carry_grid_fields():
    os.makedirs("work/assets/minecraft/textures/font", exist_ok=True)
    png = make_png_bytes(128, 128, block(8, 32, 6, 6))
    with open("work/assets/minecraft/textures/font/ascii.png", "wb") as f:
        f.write(png)

    providers = parse_bin_providers(bytes(65536))

    assert [p["name"] for p in providers] == ["ascii"]
    assert providers[0]["columns"] == 16
    assert providers[0]["rows"] == 16
    assert providers[0]["layer"] == "vanilla"


def test_vanilla_default_stack_resolves_jar_textures():
    os.makedirs("work/assets/minecraft/textures/font", exist_ok=True)
    png = make_png_bytes(16, 16, block(0, 0, 8, 8))
    with open("work/assets/minecraft/textures/font/ascii.png", "wb") as f:
        f.write(png)
    raw = font_json_bytes([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "height": 8, "chars": ["\x00\x00"]},
    ])

    providers = parse_json_providers(raw)

    assert len(providers) == 1
    assert providers[0]["layer"] == "vanilla"
    assert providers[0]["columns"] == 2
    assert providers[0]["rows"] == 1
    with open(providers[0]["file_path"], "rb") as f:
        assert f.read() == png
