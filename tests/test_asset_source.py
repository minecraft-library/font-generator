import pytest

from minecraft_fontgen.asset_source import DirAssetSource, ZipAssetSource, open_resource_pack

from helpers import font_json_bytes, make_png_bytes, write_pack_dir, write_pack_zip

PACK_FILES = {
    "pack.mcmeta": b'{"pack": {"pack_format": 88, "description": "Test"}}',
    "assets/minecraft/font/default.json": font_json_bytes([]),
    "assets/sky/font/extra.json": font_json_bytes([]),
    "assets/sky/textures/gui/icons.png": make_png_bytes(7, 7, [(0, 0)]),
}


def test_dir_source_reads_fonts_and_textures(tmp_path):
    root = write_pack_dir(tmp_path / "pack", PACK_FILES)
    source = DirAssetSource(root, "pack")

    assert source.get_font_json("minecraft:default") == font_json_bytes([])
    assert source.get_font_json("sky:extra") == font_json_bytes([])
    assert source.get_font_json("minecraft:missing") is None
    assert source.get_texture("sky", "gui/icons.png") == PACK_FILES["assets/sky/textures/gui/icons.png"]
    assert source.get_texture("sky", "gui/nope.png") is None
    assert sorted(source.list_font_ids()) == ["minecraft:default", "sky:extra"]
    assert source.read_mcmeta() == PACK_FILES["pack.mcmeta"]


def test_zip_source_flat_and_nested_root(tmp_path):
    flat = write_pack_zip(tmp_path / "flat.zip", PACK_FILES)
    nested = write_pack_zip(tmp_path / "nested.zip", PACK_FILES, root_prefix="MyPack/")

    for path in (flat, nested):
        source = ZipAssetSource(path, "pack")
        assert source.get_font_json("sky:extra") == font_json_bytes([])
        assert source.get_texture("sky", "gui/icons.png") is not None
        assert sorted(source.list_font_ids()) == ["minecraft:default", "sky:extra"]
        source.close()


def test_zip_source_normalizes_backslash_members(tmp_path):
    import zipfile

    path = tmp_path / "backslash.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("assets\\sky\\font\\extra.json", font_json_bytes([]))
    source = ZipAssetSource(str(path), "pack")
    assert source.get_font_json("sky:extra") == font_json_bytes([])


def test_zip_source_without_assets_raises(tmp_path):
    path = write_pack_zip(tmp_path / "junk.zip", {"readme.txt": b"hi"})
    with pytest.raises(ValueError):
        ZipAssetSource(path, "pack")


def test_open_resource_pack_dispatch(tmp_path):
    root = write_pack_dir(tmp_path / "dirpack", PACK_FILES)
    zipped = write_pack_zip(tmp_path / "zippack.zip", PACK_FILES)

    assert isinstance(open_resource_pack(root), DirAssetSource)
    assert isinstance(open_resource_pack(zipped), ZipAssetSource)


def test_open_resource_pack_nested_dir(tmp_path):
    write_pack_dir(tmp_path / "wrapper" / "inner", PACK_FILES)
    source = open_resource_pack(str(tmp_path / "wrapper"))
    assert source.get_font_json("sky:extra") == font_json_bytes([])


def test_open_resource_pack_rejects_non_pack(tmp_path):
    plain = tmp_path / "file.txt"
    plain.write_bytes(b"not a pack")
    with pytest.raises(ValueError):
        open_resource_pack(str(plain))


def test_open_resource_pack_tolerates_missing_mcmeta(tmp_path, capsys):
    files = {k: v for k, v in PACK_FILES.items() if k != "pack.mcmeta"}
    root = write_pack_dir(tmp_path / "nometa", files)
    source = open_resource_pack(root)
    assert source.get_font_json("sky:extra") is not None
    assert "pack.mcmeta" in capsys.readouterr().out


def test_open_resource_pack_tolerates_malformed_mcmeta(tmp_path, capsys):
    files = dict(PACK_FILES)
    files["pack.mcmeta"] = b"not json{"
    root = write_pack_dir(tmp_path / "badmeta", files)
    source = open_resource_pack(root)
    assert source.get_font_json("sky:extra") is not None
    assert "malformed" in capsys.readouterr().out


def test_dir_source_get_texture_rejects_traversal(tmp_path):
    root = write_pack_dir(tmp_path / "pack", PACK_FILES)
    source = DirAssetSource(root, "pack")
    with pytest.raises(ValueError):
        source.get_texture("minecraft", "../../../../etc/passwd")


def test_zip_source_get_texture_rejects_traversal(tmp_path):
    path = write_pack_zip(tmp_path / "flat.zip", PACK_FILES)
    source = ZipAssetSource(path, "pack")
    with pytest.raises(ValueError):
        source.get_texture("..", "gui/icons.png")
    source.close()
