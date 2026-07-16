import hashlib
import io
import json
import os

import pytest
from PIL import Image

from minecraft_fontgen.bitmap_sheets import emit_bitmap_sheets

from helpers import FakeSource, block, font_json_bytes, make_png_bytes

ASCII_ROWS = ["ABCD", "EFGH"]
ACCENTED_ROWS = ["ÀÁÂÈ"]
# NUL cell padding and a supplementary-plane character, as vanilla sheets use
# (the wave10 Java consumer indexes glyph cells by row position, so padding
# must survive the manifest round-trip verbatim)
PADDED_ROWS = ["\u0000A\u0000", "B\U0001F320\u0000"]


def _write_provider_file(providers, raw=None):
    """Writes a fixture include/default.json into the isolated cwd and returns its path."""
    os.makedirs("work/assets/minecraft/font/include", exist_ok=True)
    path = "work/assets/minecraft/font/include/default.json"
    with open(path, "wb") as f:
        f.write(raw if raw is not None else font_json_bytes(providers))
    return path


def _vanilla_fixture():
    """Returns (provider_file, source, textures) shaped like the vanilla default chain."""
    textures = {
        "minecraft:font/ascii.png": make_png_bytes(32, 16, block(0, 0, 7, 7)),
        "minecraft:font/accented.png": make_png_bytes(36, 12, block(1, 1, 5, 9)),
    }
    provider_file = _write_provider_file([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ASCII_ROWS},
        {"type": "bitmap", "file": "minecraft:font/accented.png", "height": 12, "ascent": 10, "chars": ACCENTED_ROWS},
    ])
    return provider_file, FakeSource("vanilla", textures=textures, vanilla=True), textures


def _read_manifest():
    with open("output/bitmap-sheets/manifest.json", encoding="utf-8") as f:
        return json.load(f)


def test_manifest_matches_fixture_providers():
    provider_file, source, textures = _vanilla_fixture()

    manifest_path = emit_bitmap_sheets(provider_file, "json", "output", "1.21.8", source=source)

    assert manifest_path == os.path.join("output", "bitmap-sheets", "manifest.json")
    manifest = _read_manifest()
    assert manifest["game_version"] == "1.21.8"
    assert manifest["providers"] == [
        {
            "type": "bitmap",
            "file": "minecraft:font/ascii.png",
            "height": 8,
            "ascent": 7,
            "chars": ASCII_ROWS,
            "sha256": hashlib.sha256(textures["minecraft:font/ascii.png"]).hexdigest(),
        },
        {
            "type": "bitmap",
            "file": "minecraft:font/accented.png",
            "height": 12,
            "ascent": 10,
            "chars": ACCENTED_ROWS,
            "sha256": hashlib.sha256(textures["minecraft:font/accented.png"]).hexdigest(),
        },
    ]


def test_copied_sheets_are_byte_identical():
    provider_file, source, textures = _vanilla_fixture()

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8", source=source)

    for ref, original in textures.items():
        rel = ref.replace("minecraft:", "minecraft/")
        with open(os.path.join("output", "bitmap-sheets", *rel.split("/")), "rb") as f:
            assert f.read() == original


def test_fixture_pngs_do_not_survive_pil_reencode():
    """Guards the property test_copied_sheets_are_byte_identical relies on: real
    vanilla sheets are not PIL-encoded, so a code path that decodes and re-saves
    instead of copying bytes must make the byte-identity assertions fail. The
    fixture PNGs carry a marker chunk to keep them equally re-encode-fragile."""
    png = make_png_bytes(32, 16, block(0, 0, 7, 7))

    resaved = io.BytesIO()
    Image.open(io.BytesIO(png)).save(resaved, "PNG")

    assert resaved.getvalue() != png


def test_missing_height_defaults_to_8_explicitly():
    textures = {"minecraft:font/ascii.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    provider_file = _write_provider_file([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ["a"]},
    ])

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                       source=FakeSource("vanilla", textures=textures, vanilla=True))

    assert _read_manifest()["providers"][0]["height"] == 8


def test_non_bitmap_providers_are_skipped(capsys):
    textures = {"minecraft:font/ascii.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    provider_file = _write_provider_file([
        {"type": "space", "advances": {" ": 4}},
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ["a"]},
    ])

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                       source=FakeSource("vanilla", textures=textures, vanilla=True))

    manifest = _read_manifest()
    assert len(manifest["providers"]) == 1
    assert manifest["providers"][0]["file"] == "minecraft:font/ascii.png"
    assert "non-bitmap" in capsys.readouterr().out


def test_repeated_file_reference_is_copied_once_with_same_sha256():
    png = make_png_bytes(8, 8, block(0, 0, 3, 3))
    textures = {"minecraft:font/ascii.png": png}
    provider_file = _write_provider_file([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ["a"]},
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 5, "chars": ["b"]},
    ])

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                       source=FakeSource("vanilla", textures=textures, vanilla=True))

    providers = _read_manifest()["providers"]
    assert len(providers) == 2
    assert providers[0]["sha256"] == providers[1]["sha256"] == hashlib.sha256(png).hexdigest()


def test_non_minecraft_namespace_path_is_preserved():
    png = make_png_bytes(8, 8, block(0, 0, 2, 2))
    textures = {"other:gui/sheet.png": png}
    provider_file = _write_provider_file([
        {"type": "bitmap", "file": "other:gui/sheet.png", "ascent": 7, "chars": ["a"]},
    ])

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                       source=FakeSource("vanilla", textures=textures, vanilla=True))

    with open(os.path.join("output", "bitmap-sheets", "other", "gui", "sheet.png"), "rb") as f:
        assert f.read() == png


def test_missing_sheet_texture_fails_loudly():
    provider_file = _write_provider_file([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ["a"]},
    ])

    with pytest.raises(RuntimeError, match="minecraft:font/ascii.png.*missing"):
        emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                           source=FakeSource("vanilla", textures={}, vanilla=True))


def test_bin_format_fails_loudly(tmp_path):
    # 1.13-1.19.4 also ship glyph_sizes.bin and are detected as 'bin', so the
    # message must claim 1.20+ (when include/default.json appeared), not 1.13+
    with pytest.raises(RuntimeError, match=r"include/default\.json font layout \(Minecraft 1\.20\+\)"):
        emit_bitmap_sheets(str(tmp_path / "glyph_sizes.bin"), "bin", "output", "1.8.9")


@pytest.mark.parametrize("provider, match", [
    ({"type": "bitmap", "ascent": 7, "chars": ["a"]}, "no file reference"),
    ({"type": "bitmap", "file": "bad ref!", "ascent": 7, "chars": ["a"]}, "invalid file reference"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "chars": ["a"]}, "no ascent"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": "7", "chars": ["a"]}, "not a number"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "height": "8", "ascent": 7, "chars": ["a"]}, "not a number"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "height": 0, "ascent": 0, "chars": ["a"]}, "not positive"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 9, "chars": ["a"]}, "exceeds height"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7}, "chars grid"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": []}, "chars grid"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": [[1]]}, "chars grid"),
    ({"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ["ab", "c"]}, "unequal"),
])
def test_malformed_bitmap_provider_fails_loudly(provider, match):
    textures = {"minecraft:font/ascii.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    provider_file = _write_provider_file([provider])

    with pytest.raises(RuntimeError, match=match):
        emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                           source=FakeSource("vanilla", textures=textures, vanilla=True))


def test_no_bitmap_providers_fails_loudly():
    provider_file = _write_provider_file([{"type": "space", "advances": {" ": 4}}])

    with pytest.raises(RuntimeError, match="no bitmap providers"):
        emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                           source=FakeSource("vanilla", textures={}, vanilla=True))


def test_missing_providers_array_fails_loudly():
    provider_file = _write_provider_file(None, raw=b"{}")

    with pytest.raises(RuntimeError, match="no providers array"):
        emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                           source=FakeSource("vanilla", textures={}, vanilla=True))


def test_non_object_json_root_fails_loudly():
    # A truncated/corrupted file whose root is a JSON array must raise the
    # clean RuntimeError main() converts to exit 1, not an AttributeError
    provider_file = _write_provider_file(None, raw=b"[]")

    with pytest.raises(RuntimeError, match="no providers array"):
        emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                           source=FakeSource("vanilla", textures={}, vanilla=True))


def test_non_object_provider_entry_fails_loudly():
    # The game's codec rejects non-object provider entries, so per the
    # fail-loud contract this raises instead of warn-skipping
    provider_file = _write_provider_file(None, raw=json.dumps({"providers": ["oops"]}).encode("utf-8"))

    with pytest.raises(RuntimeError, match="Provider 0 is not a JSON object"):
        emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                           source=FakeSource("vanilla", textures={}, vanilla=True))


def test_unrecognized_provider_keys_warn_and_are_omitted(capsys):
    textures = {"minecraft:font/ascii.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    provider_file = _write_provider_file([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ["a"],
         "filter": {"uniform": True}},
    ])

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                       source=FakeSource("vanilla", textures=textures, vanilla=True))

    out = capsys.readouterr().out
    assert "filter" in out and "manifest omits" in out
    entry = _read_manifest()["providers"][0]
    assert set(entry) == {"type", "file", "height", "ascent", "chars", "sha256"}


def test_chars_rows_round_trip_verbatim_including_nul_padding():
    textures = {"minecraft:font/ascii.png": make_png_bytes(24, 16, block(0, 0, 4, 4))}
    provider_file = _write_provider_file([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": PADDED_ROWS},
    ])

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                       source=FakeSource("vanilla", textures=textures, vanilla=True))

    with open("output/bitmap-sheets/manifest.json", "rb") as f:
        raw = f.read()
    assert b"\x00" not in raw  # NUL padding must be escaped, never written literally
    manifest = json.loads(raw.decode("utf-8"))
    assert manifest["providers"][0]["chars"] == PADDED_ROWS


def test_bom_prefixed_provider_file_is_tolerated():
    textures = {"minecraft:font/ascii.png": make_png_bytes(8, 8, block(0, 0, 2, 2))}
    provider_file = _write_provider_file(None, raw=b"\xef\xbb\xbf" + font_json_bytes([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ["a"]},
    ]))

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8",
                       source=FakeSource("vanilla", textures=textures, vanilla=True))

    assert _read_manifest()["providers"][0]["file"] == "minecraft:font/ascii.png"


def test_resolves_from_vanilla_work_dir_by_default():
    png = make_png_bytes(16, 16, block(0, 0, 8, 8))
    os.makedirs("work/assets/minecraft/textures/font", exist_ok=True)
    with open("work/assets/minecraft/textures/font/ascii.png", "wb") as f:
        f.write(png)
    provider_file = _write_provider_file([
        {"type": "bitmap", "file": "minecraft:font/ascii.png", "ascent": 7, "chars": ["ab"]},
    ])

    emit_bitmap_sheets(provider_file, "json", "output", "1.21.8")

    with open("output/bitmap-sheets/minecraft/font/ascii.png", "rb") as f:
        assert f.read() == png
    assert _read_manifest()["providers"][0]["sha256"] == hashlib.sha256(png).hexdigest()
