"""Versioned, GID-keyed JSON sidecar for the colour-glyph track.

A single vanilla cmap plus a uint16 hmtx cannot carry what the consumer needs to
position colour glyphs: the (font_id, codepoint) rows that disambiguate PUA
codepoints reused across font files, the signed and possibly fractional advances
from space providers, and the glyph origins. This module flattens the per-storage
rows into one deterministic sidecar keyed on gid (post format 3.0 renames glyph
names to uniXXXX on reload, so gid is the authoritative cross-reference)."""
import json
import os

from minecraft_fontgen.config import (
    UNITS_PER_EM, VERSION, SBIX_GRAPHIC_TYPE, COLOR_SIDECAR_NAME,
)
from minecraft_fontgen.functions import log

SCHEMA_VERSION = 1


def build_sidecar(fonts, storages, source_date_epoch):
    """Assembles the sidecar dict from the compiled colour fonts.

    `fonts` is the list of {"font_id", "file"} entries (one per per-font-id .ttf);
    `storages` is the matching finalized GlyphStorage objects. Each row's gid is
    resolved against its own storage's compiled glyph order. Pure/deterministic:
    the glyph rows are sorted by (font_id, codepoint) then (glyph_name or "")."""
    glyphs = []
    for storage in storages:
        name_to_gid = storage.name_to_gid()
        for row in storage.sidecar_rows:
            glyph_name = row["glyphName"]
            gid = name_to_gid[glyph_name] if glyph_name is not None else None
            glyphs.append({
                "font_id": row["font_id"],
                "codepoint": row["codepoint"],
                "glyph_name": glyph_name,
                "gid": gid,
                "advance": row["advance"],
                "origin": list(row["origin_units"]),
                "strike_ppem": row["strike_ppem"],
            })

    glyphs.sort(key=lambda g: (g["font_id"], g["codepoint"], g["glyph_name"] or ""))

    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": VERSION,
        "source_date_epoch": source_date_epoch,
        "units_per_em": UNITS_PER_EM,
        "graphic_type": SBIX_GRAPHIC_TYPE,
        "fonts": fonts,
        "glyphs": glyphs,
    }


def write_sidecar(sidecar, output_dir, name=COLOR_SIDECAR_NAME):
    """Writes the sidecar as UTF-8 JSON (arrays pre-sorted -> byte-deterministic under
    a fixed epoch). Fails loud on write error. Returns the written path."""
    path = os.path.join(output_dir, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sidecar, f, ensure_ascii=False, indent=2)
    except OSError as error:
        log(f"❌ Failed to write colour sidecar {path}: {error}")
        raise SystemExit(1)
    return path
