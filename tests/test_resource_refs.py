import pytest

from minecraft_fontgen.asset_source import split_resource_ref
from minecraft_fontgen.functions import sanitize_fs_name


def test_namespaced_ref_splits_on_first_colon():
    assert split_resource_ref("hypixel_skyblock:gui/stats.png") == ("hypixel_skyblock", "gui/stats.png")


def test_bare_ref_gets_default_namespace():
    assert split_resource_ref("font/ascii.png") == ("minecraft", "font/ascii.png")


def test_font_id_form():
    assert split_resource_ref("minecraft:include/default") == ("minecraft", "include/default")


@pytest.mark.parametrize("bad", [
    "minecraft:../../../etc/passwd",
    "minecraft:/absolute/path.png",
    "minecraft:a//b.png",
    "minecraft:a/./b.png",
    "MINECRAFT:font/ascii.png",
    "minecraft:font/As cii.png",
    "bad ns:font/ascii.png",
    "minecraft:",
    "..:font/ascii.png",
    ".:font/ascii.png",
])
def test_invalid_refs_raise(bad):
    with pytest.raises(ValueError):
        split_resource_ref(bad)


def test_sanitize_fs_name_strips_unsafe_characters():
    assert sanitize_fs_name("pack1_hypixel_skyblock:gui/stats") == "pack1_hypixel_skyblock_gui_stats"
    assert sanitize_fs_name("::/") == "pack"
