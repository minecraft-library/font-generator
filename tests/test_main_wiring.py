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


def _opts(resource_packs=(), validate=False, emit_bitmap_sheets=False):
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
        emit_bitmap_sheets=emit_bitmap_sheets,
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
        return "matched.json", "json", {}, "1.21.8"

    def emit_bitmap_sheets(provider_file, provider_format, output_dir, game_version, source=None):
        calls.append("emit")
        return "output/bitmap-sheets/manifest.json"

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

    monkeypatch.setattr(main_mod, "clean_directories", clean_directories)
    monkeypatch.setattr(main_mod, "download_minecraft_assets", download_minecraft_assets)
    monkeypatch.setattr(main_mod, "emit_bitmap_sheets", emit_bitmap_sheets)
    monkeypatch.setattr(main_mod, "parse_provider_file", parse_provider_file)
    monkeypatch.setattr(main_mod, "collect_pack_providers", collect_pack_providers)
    monkeypatch.setattr(main_mod, "build_glyph_map", build_glyph_map)
    monkeypatch.setattr(main_mod, "create_font_files", create_font_files)


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


def test_emit_bitmap_sheets_disabled_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts())
    _stub_pipeline(monkeypatch, calls)

    main_mod.main()

    assert "emit" not in calls


def test_emit_bitmap_sheets_runs_between_download_and_parse(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts(emit_bitmap_sheets=True))
    _stub_pipeline(monkeypatch, calls)

    main_mod.main()

    assert calls.index("download") < calls.index("emit")
    assert calls.index("emit") < calls.index("parse")
    assert "create" in calls  # font generation still runs in the same invocation


def test_emit_bitmap_sheets_failure_exits_nonzero_and_closes_stack(monkeypatch, capsys):
    calls = []
    fakes = {"p1": FakeSource("pack1")}
    monkeypatch.setattr(main_mod, "parse_args", lambda: _opts(resource_packs=("p1",), emit_bitmap_sheets=True))
    monkeypatch.setattr(main_mod, "open_resource_pack", lambda path: fakes[path])
    _stub_pipeline(monkeypatch, calls)

    def emit_bitmap_sheets(provider_file, provider_format, output_dir, game_version, source=None):
        raise RuntimeError("sheet 'minecraft:font/ascii.png' is missing")

    monkeypatch.setattr(main_mod, "emit_bitmap_sheets", emit_bitmap_sheets)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code == 1
    assert "minecraft:font/ascii.png" in capsys.readouterr().err
    assert "create" not in calls
    assert fakes["p1"].closed


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
