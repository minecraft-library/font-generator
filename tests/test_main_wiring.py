import io
import sys

import pytest


class _FakeStd:
    """Stand-in for sys.stdout/stderr with a .buffer, so the UTF-8-wrapping
    module-level code in main.py wraps a throwaway object instead of
    pytest's captured stdout/stderr (wrapping the latter closes pytest's
    capture file on interpreter teardown)."""

    def __init__(self):
        self.buffer = io.BytesIO()


_real_stdout, _real_stderr = sys.stdout, sys.stderr
sys.stdout, sys.stderr = _FakeStd(), _FakeStd()
try:
    import minecraft_fontgen.main as main_mod
finally:
    sys.stdout, sys.stderr = _real_stdout, _real_stderr

from minecraft_fontgen.cli import BuildOptions

from helpers import FakeSource


def _opts(resource_packs=(), validate=False, color_glyphs=False):
    return BuildOptions(
        silent=True,
        output_dir="output",
        output_fonts=[],
        mc_version=None,
        use_cff=True,
        output_ext="otf",
        validate=validate,
        resource_packs=resource_packs,
        inset_vertices=True,
        color_glyphs=color_glyphs,
    )


def _stub_pipeline(monkeypatch, calls):
    """Patches the collaborators main() calls after packs are open, all no-ops recording into calls."""
    # set_silent is stubbed too: the real one mutates minecraft_fontgen.config.SILENT_LOG,
    # a plain module attribute monkeypatch can't auto-revert, which would leak into later
    # tests that assert on log() output via capsys.
    monkeypatch.setattr(main_mod, "set_silent", lambda value: None)

    def clean_directories(output_dir):
        calls.append("clean")

    def download_minecraft_assets(mc_version):
        calls.append("download")
        return "matched.jar", "otf", {}

    def parse_provider_file(file, format, stack):
        calls.append("parse")
        return []

    def collect_pack_providers(stack):
        calls.append("collect")
        return []

    def build_glyph_map(providers, unifont_glyphs, stack, inset_vertices=True):
        calls.append("build")
        return {}

    def create_font_files(glyph_map, use_cff, output_fonts, output_dir, output_font_name, output_file_ext):
        calls.append("create")
        return []

    def collect_color_providers(stack):
        calls.append("collect_color")
        return []

    def build_color_glyph_map(providers):
        calls.append("build_color_map")
        return {}

    def group_color_space_rows(providers):
        return {}

    def create_color_font_files(color_glyph_map, space_by_font_id, output_dir, output_font_name):
        calls.append("create_color")
        return "out/Minecraft-Color.ttf", object()

    def build_sidecar(file, storage, epoch):
        calls.append("build_sidecar")
        return {}

    def write_sidecar(sidecar, output_dir):
        calls.append("write_sidecar")
        return "out/colour-glyphs.json"

    monkeypatch.setattr(main_mod, "clean_directories", clean_directories)
    monkeypatch.setattr(main_mod, "download_minecraft_assets", download_minecraft_assets)
    monkeypatch.setattr(main_mod, "parse_provider_file", parse_provider_file)
    monkeypatch.setattr(main_mod, "collect_pack_providers", collect_pack_providers)
    monkeypatch.setattr(main_mod, "build_glyph_map", build_glyph_map)
    monkeypatch.setattr(main_mod, "create_font_files", create_font_files)
    monkeypatch.setattr(main_mod, "collect_color_providers", collect_color_providers)
    monkeypatch.setattr(main_mod, "build_color_glyph_map", build_color_glyph_map)
    monkeypatch.setattr(main_mod, "group_color_space_rows", group_color_space_rows)
    monkeypatch.setattr(main_mod, "create_color_font_files", create_color_font_files)
    monkeypatch.setattr(main_mod, "build_sidecar", build_sidecar)
    monkeypatch.setattr(main_mod, "write_sidecar", write_sidecar)


def test_invalid_pack_exits_before_any_work(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts(resource_packs=("bogus.zip",)))

    def open_resource_pack(path):
        raise ValueError(f"'{path}' is not a resource pack")

    monkeypatch.setattr(main_mod, "open_resource_pack", open_resource_pack)
    _stub_pipeline(monkeypatch, calls)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code == 1
    assert calls == []


def test_packs_open_before_network_and_stack_closes_on_success(monkeypatch):
    calls = []
    fakes = {"p1": FakeSource("pack1"), "p2": FakeSource("pack2")}
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts(resource_packs=("p1", "p2")))

    def open_resource_pack(path):
        calls.append(("open", path))
        return fakes[path]

    monkeypatch.setattr(main_mod, "open_resource_pack", open_resource_pack)
    _stub_pipeline(monkeypatch, calls)

    main_mod.main()

    assert calls.index(("open", "p1")) < calls.index(("open", "p2"))
    assert calls.index(("open", "p2")) < calls.index("clean")
    assert calls.index("clean") < calls.index("download")
    assert fakes["p1"].closed
    assert fakes["p2"].closed


def test_stack_closes_when_download_fails(monkeypatch):
    calls = []
    fakes = {"p1": FakeSource("pack1"), "p2": FakeSource("pack2")}
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts(resource_packs=("p1", "p2")))

    def open_resource_pack(path):
        calls.append(("open", path))
        return fakes[path]

    def download_minecraft_assets(mc_version):
        calls.append("download")
        raise RuntimeError("network is down")

    monkeypatch.setattr(main_mod, "open_resource_pack", open_resource_pack)
    _stub_pipeline(monkeypatch, calls)
    monkeypatch.setattr(main_mod, "download_minecraft_assets", download_minecraft_assets)

    with pytest.raises(RuntimeError, match="network is down"):
        main_mod.main()

    assert "parse" not in calls
    assert fakes["p1"].closed
    assert fakes["p2"].closed


def test_main_dispatches_color_after_build(monkeypatch):
    import minecraft_fontgen.config as config

    calls = []
    monkeypatch.setattr(config, "COLOR_GLYPHS", False)
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts(color_glyphs=True))
    monkeypatch.setattr(main_mod, "open_resource_pack", lambda path: FakeSource(path))
    _stub_pipeline(monkeypatch, calls)

    main_mod.main()

    # colour is ingested after the pack providers and the mono build; the colour
    # compile + sidecar run strictly after the mono create; mono still runs.
    assert "create" in calls
    assert calls.index("collect_color") > calls.index("collect")
    assert calls.index("create_color") > calls.index("create")
    assert calls.index("build_sidecar") > calls.index("create_color")
    assert calls.index("write_sidecar") > calls.index("build_sidecar")
    # the flag was mirrored onto the module config the ingestion helpers read
    assert config.COLOR_GLYPHS is True


def test_color_off_skips_color_and_keeps_mono(monkeypatch):
    import minecraft_fontgen.config as config

    calls = []
    monkeypatch.setattr(config, "COLOR_GLYPHS", False)
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts(color_glyphs=False))
    monkeypatch.setattr(main_mod, "open_resource_pack", lambda path: FakeSource(path))
    _stub_pipeline(monkeypatch, calls)

    main_mod.main()

    # colour off: none of the colour collaborators run, the mono create still does
    assert "create" in calls
    for colour_call in ("collect_color", "create_color", "build_sidecar", "write_sidecar"):
        assert colour_call not in calls
    assert config.COLOR_GLYPHS is False


def test_second_pack_open_failure_closes_first(monkeypatch):
    calls = []
    first = FakeSource("pack1")
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts(resource_packs=("p1", "p2")))

    def open_resource_pack(path):
        if path == "p1":
            calls.append(("open", path))
            return first
        raise ValueError(f"'{path}' is not a resource pack")

    monkeypatch.setattr(main_mod, "open_resource_pack", open_resource_pack)
    _stub_pipeline(monkeypatch, calls)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code == 1
    assert first.closed
    assert "clean" not in calls
    assert "download" not in calls
