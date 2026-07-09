import os

from minecraft_fontgen.asset_source import AssetStack, VanillaSource

from helpers import FakeSource, make_png_bytes


def test_font_json_layers_returns_sources_in_priority_ascending_order():
    low = FakeSource("low", fonts={"minecraft:default": b"low"}, vanilla=True)
    mid = FakeSource("mid", fonts={"minecraft:default": b"mid"})
    high = FakeSource("high", fonts={"other:font": b"x"})
    stack = AssetStack([low, mid, high])

    assert stack.font_json_layers("minecraft:default") == [("low", b"low"), ("mid", b"mid")]
    assert stack.pack_sources() == [mid, high]


def test_materialize_texture_highest_priority_wins():
    png_a = make_png_bytes(2, 2, [(0, 0)])
    png_b = make_png_bytes(2, 2, [(1, 1)])
    lower = FakeSource("lower", textures={"sky:gui/icons.png": png_a})
    higher = FakeSource("higher", textures={"sky:gui/icons.png": png_b})
    stack = AssetStack([lower, higher])

    path = stack.materialize_texture("sky:gui/icons.png")
    assert path == os.path.join("work/textures", "sky", "gui", "icons.png")
    with open(path, "rb") as f:
        assert f.read() == png_b


def test_materialize_texture_falls_through_to_lower_layers():
    png = make_png_bytes(2, 2, [(0, 0)])
    lower = FakeSource("lower", textures={"minecraft:font/ascii.png": png}, vanilla=True)
    higher = FakeSource("higher", textures={})
    stack = AssetStack([lower, higher])

    path = stack.materialize_texture("minecraft:font/ascii.png")
    assert path is not None
    assert os.path.isfile(path)


def test_materialize_texture_missing_everywhere_returns_none():
    stack = AssetStack([FakeSource("only", textures={})])
    assert stack.materialize_texture("sky:missing.png") is None


def test_materialize_texture_rejects_unsafe_ref():
    evil = FakeSource("evil", textures={"minecraft:../../escape.png": b"x"})
    stack = AssetStack([evil])
    assert stack.materialize_texture("minecraft:../../escape.png") is None
    assert not os.path.exists("escape.png")


def test_vanilla_source_reads_work_dir():
    os.makedirs("work/assets/minecraft/font/include", exist_ok=True)
    with open("work/assets/minecraft/font/include/default.json", "wb") as f:
        f.write(b"{}")
    source = VanillaSource()

    assert source.is_vanilla is True
    assert source.name == "vanilla"
    assert source.get_font_json("minecraft:include/default") == b"{}"


def test_close_closes_all_sources():
    a, b = FakeSource("a"), FakeSource("b")
    AssetStack([a, b]).close()
    assert a.closed and b.closed
