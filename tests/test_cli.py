import os
import sys

import pytest

from minecraft_fontgen.cli import BuildOptions, parse_args


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["minecraft_fontgen", *args])


def test_defaults_have_no_packs(monkeypatch):
    _argv(monkeypatch)
    monkeypatch.delenv("MCFONT_RESOURCE_PACKS", raising=False)
    opts = parse_args()
    assert isinstance(opts, BuildOptions)
    assert opts.resource_packs == ()
    assert opts.output_ext in ("otf", "ttf")


def test_repeatable_flag_preserves_order_and_abspaths(monkeypatch, tmp_path):
    p1 = tmp_path / "one.zip"
    p2 = tmp_path / "two"
    p1.write_bytes(b"")
    p2.mkdir()
    _argv(monkeypatch, "--resource-pack", str(p1), "--resource-pack", str(p2))
    opts = parse_args()
    assert opts.resource_packs == (os.path.abspath(str(p1)), os.path.abspath(str(p2)))


def test_env_fallback_splits_on_pathsep(monkeypatch, tmp_path):
    p1 = tmp_path / "a"
    p2 = tmp_path / "b"
    p1.mkdir()
    p2.mkdir()
    _argv(monkeypatch)
    monkeypatch.setenv("MCFONT_RESOURCE_PACKS", os.pathsep.join([str(p1), str(p2)]))
    opts = parse_args()
    assert opts.resource_packs == (os.path.abspath(str(p1)), os.path.abspath(str(p2)))


def test_cli_flag_overrides_env(monkeypatch, tmp_path):
    p1 = tmp_path / "cli"
    p2 = tmp_path / "env"
    p1.mkdir()
    p2.mkdir()
    _argv(monkeypatch, "--resource-pack", str(p1))
    monkeypatch.setenv("MCFONT_RESOURCE_PACKS", str(p2))
    assert parse_args().resource_packs == (os.path.abspath(str(p1)),)


def test_missing_pack_path_errors(monkeypatch, tmp_path):
    _argv(monkeypatch, "--resource-pack", str(tmp_path / "nope.zip"))
    with pytest.raises(SystemExit):
        parse_args()


def test_vertex_inset_enabled_by_default(monkeypatch):
    _argv(monkeypatch)
    monkeypatch.delenv("MCFONT_NO_VERTEX_INSET", raising=False)
    assert parse_args().inset_vertices is True


def test_no_vertex_inset_flag_disables(monkeypatch):
    _argv(monkeypatch, "--no-vertex-inset")
    assert parse_args().inset_vertices is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
def test_no_vertex_inset_env_disables(monkeypatch, value):
    _argv(monkeypatch)
    monkeypatch.setenv("MCFONT_NO_VERTEX_INSET", value)
    assert parse_args().inset_vertices is False


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_no_vertex_inset_env_falsy_keeps_inset(monkeypatch, value):
    _argv(monkeypatch)
    monkeypatch.setenv("MCFONT_NO_VERTEX_INSET", value)
    assert parse_args().inset_vertices is True


def test_emit_bitmap_sheets_disabled_by_default(monkeypatch):
    _argv(monkeypatch)
    monkeypatch.delenv("MCFONT_EMIT_BITMAP_SHEETS", raising=False)
    assert parse_args().emit_bitmap_sheets is False


def test_emit_bitmap_sheets_flag_enables(monkeypatch):
    _argv(monkeypatch, "--emit-bitmap-sheets")
    assert parse_args().emit_bitmap_sheets is True


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
def test_emit_bitmap_sheets_env_enables(monkeypatch, value):
    _argv(monkeypatch)
    monkeypatch.setenv("MCFONT_EMIT_BITMAP_SHEETS", value)
    assert parse_args().emit_bitmap_sheets is True


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_emit_bitmap_sheets_env_falsy_stays_off(monkeypatch, value):
    _argv(monkeypatch)
    monkeypatch.setenv("MCFONT_EMIT_BITMAP_SHEETS", value)
    assert parse_args().emit_bitmap_sheets is False
