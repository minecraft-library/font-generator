"""Versioned JSON sidecar for the single-file colour-glyph track.

A single vanilla cmap plus a uint16 hmtx cannot carry what the consumer needs to
position colour glyphs: the (font_id, original_codepoint) rows that disambiguate
private-use codepoints reused across font ids, the signed and possibly fractional
advances from space providers, and the glyph origins. The colour output is now one
merged .ttf per pack, so this module flattens one storage's rows into one
deterministic sidecar.

Schema v2 adds two things over v1: each glyph row carries the STORED codepoint it
occupies in the merged font (the plane-15/16 codepoint the cmap keys on), and the
top level names the single font file rather than a per-font-id map. The gid stays
the authoritative cross-reference (post format 3.0 renames glyph names to uniXXXX
on reload, so glyph_name is advisory)."""
import json
import os

from minecraft_fontgen.config import (
    UNITS_PER_EM, VERSION, SBIX_GRAPHIC_TYPE, COLOR_SIDECAR_NAME,
)
from minecraft_fontgen.functions import log

SCHEMA_VERSION = 2


def build_sidecar(file, storage, source_date_epoch):
    """Assembles the sidecar dict from the single compiled colour font.

    `file` is the merged .ttf basename (or None when the pack minted only space
    rows and no file was written); `storage` is the finalized GlyphStorage. Each
    row's gid is resolved against the storage's compiled glyph order. Pure and
    deterministic: rows are sorted by (font_id, original codepoint, glyph_name)."""
    name_to_gid = storage.name_to_gid()
    glyphs = []
    for row in storage.sidecar_rows:
        glyph_name = row["glyphName"]
        gid = name_to_gid[glyph_name] if glyph_name is not None else None
        glyphs.append({
            "font_id": row["font_id"],
            "codepoint": row["codepoint"],
            "stored_codepoint": row["stored_codepoint"],
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
        "file": file,
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
