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
