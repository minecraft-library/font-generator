"""M6: --color-glyphs CLI flag / env, TrueType coercion, and family-qualified names."""
import sys

import pytest
from fontTools.ttLib import TTFont

from minecraft_fontgen.cli import parse_args
from minecraft_fontgen.table.name import create_font_name_table


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["minecraft_fontgen", *args])
    monkeypatch.delenv("MCFONT_COLOR_GLYPHS", raising=False)
    monkeypatch.delenv("MCFONT_TYPE", raising=False)


def test_cli_color_defaults_off(monkeypatch):
    _argv(monkeypatch)
    opts = parse_args()
    assert opts.color_glyphs is False


def test_cli_color_flag_parses(monkeypatch):
    _argv(monkeypatch, "--color-glyphs")
    opts = parse_args()
    assert opts.color_glyphs is True
    # colour forces TrueType output
    assert opts.use_cff is False
    assert opts.output_ext == "ttf"


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
def test_cli_color_env_enables(monkeypatch, value):
    _argv(monkeypatch)
    monkeypatch.setenv("MCFONT_COLOR_GLYPHS", value)
    opts = parse_args()
    assert opts.color_glyphs is True
    assert opts.output_ext == "ttf"


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_cli_color_env_falsy_stays_off(monkeypatch, value):
    _argv(monkeypatch)
    monkeypatch.setenv("MCFONT_COLOR_GLYPHS", value)
    assert parse_args().color_glyphs is False


def test_cli_color_coerces_default_type_to_ttf(monkeypatch, capsys):
    # default type is opentype; colour silently coerces it, no warning
    _argv(monkeypatch, "--color-glyphs")
    opts = parse_args()
    assert opts.use_cff is False and opts.output_ext == "ttf"
    assert "forces TrueType" not in capsys.readouterr().err


def test_cli_color_explicit_ttf_no_warning(monkeypatch, capsys):
    _argv(monkeypatch, "--color-glyphs", "--type", "ttf")
    opts = parse_args()
    assert opts.output_ext == "ttf"
    assert "forces TrueType" not in capsys.readouterr().err


@pytest.mark.parametrize("otf_type", ["otf", "opentype", "OTF"])
def test_cli_color_explicit_otf_warns_and_coerces(monkeypatch, capsys, otf_type):
    _argv(monkeypatch, "--color-glyphs", "--type", otf_type)
    opts = parse_args()
    # coerced despite the explicit OpenType request, and the override is announced
    assert opts.use_cff is False
    assert opts.output_ext == "ttf"
    assert "forces TrueType" in capsys.readouterr().err


def test_cli_no_color_keeps_opentype_default(monkeypatch, capsys):
    _argv(monkeypatch, "--type", "otf")
    opts = parse_args()
    assert opts.color_glyphs is False
    assert opts.use_cff is True and opts.output_ext == "otf"
    assert "forces TrueType" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# family-qualified name table (M6): two colour font ids must not collide on
# family + subfamily + full name at OS install time.
# ---------------------------------------------------------------------------

def _name_strings(font):
    return {rec.nameID: rec.toUnicode() for rec in font["name"].names}


def test_color_name_table_family_qualified():
    

    font = TTFont()
    create_font_name_table(font, bold=False, italic=False, family_qualifier="refpack:default")
    names = _name_strings(font)
    # the font id folds into family (1), full name (4), PostScript name (6)
    assert "refpack:default" in names[1]
    assert "refpack:default" in names[4]
    # PostScript name is sanitized (no colon / space) but still carries the id
    assert ":" not in names[6] and " " not in names[6]
    assert "refpackdefault" in names[6]


def test_color_name_table_none_qualifier_is_unchanged():
    

    plain = TTFont()
    create_font_name_table(plain, bold=False, italic=False)
    qualified_none = TTFont()
    create_font_name_table(qualified_none, bold=False, italic=False, family_qualifier=None)
    assert _name_strings(plain) == _name_strings(qualified_none)


def test_two_font_ids_have_distinct_family_names():
    

    fa, fb = TTFont(), TTFont()
    create_font_name_table(fa, family_qualifier="packA:icons")
    create_font_name_table(fb, family_qualifier="packB:icons")
    assert _name_strings(fa)[1] != _name_strings(fb)[1]
    assert _name_strings(fa)[6] != _name_strings(fb)[6]
