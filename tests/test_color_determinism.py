import io
import time

import pytest
from fontTools.ttLib import TTFont, TTLibError, newTable
from fontTools.pens.ttGlyphPen import TTGlyphPen

import minecraft_fontgen.config as config
from minecraft_fontgen.config import MAC_EPOCH
from minecraft_fontgen.functions import resolve_source_date_epoch
from minecraft_fontgen.table.header import create_font_header_table
from minecraft_fontgen.table.truetype import create_tt_font_tables


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _header_font():
    f = TTFont()
    create_font_header_table(f)
    return f


def _minimal_tt_font():
    """Smallest saveable TrueType font: empty .notdef outline + the tables
    save() needs to compile a glyf/loca sfnt."""
    f = TTFont()
    create_tt_font_tables(f)
    create_font_header_table(f, use_cff=False)
    f["glyf"].glyphs[".notdef"] = TTGlyphPen(None).glyph()
    f.setGlyphOrder([".notdef"])
    f["glyf"].glyphOrder = [".notdef"]

    maxp = f["maxp"] = newTable("maxp")
    maxp.tableVersion = 0x00010000
    for attr in ("maxPoints", "maxContours", "maxCompositePoints", "maxCompositeContours",
                 "maxTwilightPoints", "maxStorage", "maxFunctionDefs", "maxInstructionDefs",
                 "maxStackElements", "maxSizeOfInstructions", "maxComponentElements",
                 "maxComponentDepth"):
        setattr(maxp, attr, 0)
    maxp.maxZones = 2
    maxp.numGlyphs = 1

    hmtx = f["hmtx"] = newTable("hmtx")
    hmtx.metrics = {".notdef": (512, 0)}

    hhea = f["hhea"] = newTable("hhea")
    for attr, val in dict(tableVersion=0x00010000, ascent=896, descent=-128, lineGap=0,
                          advanceWidthMax=512, minLeftSideBearing=0, minRightSideBearing=0,
                          xMaxExtent=512, caretSlopeRise=1, caretSlopeRun=0, caretOffset=0,
                          reserved0=0, reserved1=0, reserved2=0, reserved3=0,
                          metricDataFormat=0, numberOfHMetrics=1).items():
        setattr(hhea, attr, val)
    return f


# ---------------------------------------------------------------------------
# header epoch resolution
# ---------------------------------------------------------------------------

def test_header_uses_source_date_epoch_env(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    head = _header_font()["head"]
    assert head.created == 1000000000 + MAC_EPOCH
    assert head.modified == 1000000000 + MAC_EPOCH


def test_header_config_epoch_override(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    monkeypatch.setattr(config, "SOURCE_DATE_EPOCH", 1234567890)
    head = _header_font()["head"]
    assert head.created == 1234567890 + MAC_EPOCH
    assert head.modified == 1234567890 + MAC_EPOCH


def test_header_epoch_timezone_independent(monkeypatch):
    # The old code added (MAC_EPOCH - mktime(gmtime(0))), which reinterprets the
    # UTC epoch struct as local time and makes the timestamp timezone-dependent.
    # Poison time.mktime: if any such term were reintroduced the timestamp would
    # shift; a pinned epoch must resolve to exactly epoch + MAC_EPOCH regardless.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    monkeypatch.setattr(time, "mktime", lambda *a, **k: 999999)
    head = _header_font()["head"]
    assert head.created == 1000000000 + MAC_EPOCH
    assert head.modified == 1000000000 + MAC_EPOCH


def test_header_epoch_invalid_env_errors(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-an-int")
    with pytest.raises(SystemExit):
        resolve_source_date_epoch()
    with pytest.raises(SystemExit):
        _header_font()


def test_header_two_builds_byte_identical(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    f1 = _header_font()
    f2 = _header_font()
    assert f1["head"].compile(f1) == f2["head"].compile(f2)


# ---------------------------------------------------------------------------
# TrueType sfntVersion tag
# ---------------------------------------------------------------------------

def test_truetype_sfnt_version_is_string_tag():
    f = TTFont()
    create_tt_font_tables(f)
    assert f.sfntVersion == "\x00\x01\x00\x00"
    assert isinstance(f.sfntVersion, str)


def test_truetype_save_roundtrip(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    f = _minimal_tt_font()
    buf = io.BytesIO()
    f.save(buf)  # int sfntVersion would raise TTLibError('bad sfntVersion') here

    buf.seek(0)
    reopened = TTFont(buf)
    assert reopened.sfntVersion == "\x00\x01\x00\x00"
    assert reopened["head"].created == 1000000000 + MAC_EPOCH

    # regression guard: the pre-fix int tag still breaks save()
    f.sfntVersion = 0x00010000
    with pytest.raises(TTLibError):
        f.save(io.BytesIO())
