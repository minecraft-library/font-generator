import hashlib
import sys

from fontTools.ttLib import TTFont
from tqdm import tqdm

from minecraft_fontgen.config import COLOR_OUTPUT_INFIX
from minecraft_fontgen.functions import log, is_silent, sanitize_fs_name

from minecraft_fontgen.glyph.glyph_storage import GlyphStorage
from minecraft_fontgen.table.glyph_mappings import create_font_mapping_table
from minecraft_fontgen.table.header import create_font_header_table
from minecraft_fontgen.table.horizontal_header import create_font_hheader_table
from minecraft_fontgen.table.horizontal_metrics import create_font_hmetrics_table
from minecraft_fontgen.table.maximum_profile import create_font_mprofile_table
from minecraft_fontgen.table.name import create_font_name_table
from minecraft_fontgen.table.opentype import create_ot_font_tables
from minecraft_fontgen.table.os2_metrics import create_font_metrics_table
from minecraft_fontgen.table.postscript import create_font_pscript_table
from minecraft_fontgen.table.truetype import create_tt_font_tables

def create_font_files(glyph_map, use_cff, output_fonts, output_dir, output_font_name, output_file_ext):
    """Creates all enabled font files in batch: initializes tables, converts glyphs, saves. Returns output file paths."""
    font_icon = "🅾️" if use_cff else "🆎"
    font_type = "OpenType" if use_cff else "TrueType"
    enabled_fonts = [f for f in output_fonts if f["enabled"]]

    if not enabled_fonts:
        log("→ ⚠️ No font styles enabled.")
        return []

    log(f"{font_icon} Creating {font_type} font files...")

    # Initialize font tables and glyph storages for each style
    storages = {}
    for style in enabled_fonts:
        log(f"→ 📄 Initializing {style['name'].lower()} tables...")
        font = TTFont()
        create_font_header_table(font, use_cff)
        create_font_hheader_table(font, use_cff)
        create_font_mprofile_table(font, use_cff)
        create_font_pscript_table(font, use_cff)
        create_font_hmetrics_table(font)
        create_font_name_table(font, style["bold"], style["italic"])
        create_font_metrics_table(font)
        create_font_mapping_table(font)

        if use_cff:
            create_ot_font_tables(font, style["bold"], style["italic"])
        else:
            create_tt_font_tables(font)

        storages[style["name"]] = (GlyphStorage(font, use_cff), style)

    # Filter out fonts whose pixel style isn't in the glyph map (e.g. Galactic when alt.json is missing)
    available_fonts = [f for f in enabled_fonts if f["pixel_style"] in glyph_map]
    for f in enabled_fonts:
        if f["pixel_style"] not in glyph_map:
            log(f"→ ⚠️ Skipping {f['name']} (alternate font assets not found in this version)")

    # Convert glyphs for all styles in a single pass
    total = sum(len(glyph_map[f["pixel_style"]]) for f in available_fonts)
    log(f"→ 🔣 Drawing glyphs ({len(available_fonts)} styles)...")

    with tqdm(total=total, desc=f" → 🔣 {available_fonts[0]['name']}", unit="glyph",
              ncols=80, leave=False, file=sys.stdout, disable=is_silent()) as progress:
        for style in available_fonts:
            progress.set_description(f" → 🔣 {style['name']}")
            tiles = glyph_map[style["pixel_style"]]
            storage = storages[style["name"]][0]

            for tile in tiles.values():
                progress.update(1)
                glyph = storage.create_glyph(tile)

                if not glyph.is_valid():
                    continue

                if tile.get("svg") and not style["italic"]:
                    glyph.write_svg_paths()

                glyph.scale(italic=style["italic"])
                glyph.draw()
                storage.add(glyph)

    # Finalize and save all fonts
    log(f"💾 Saving font files...", flush=True)
    output_files = []
    for font_name, (storage, style) in storages.items():
        if style["pixel_style"] not in glyph_map:
            continue

        output_file = f"{output_font_name}-{font_name}.{output_file_ext}"
        output_path = f"{output_dir}/{output_file}"
        log(f"→ ☕ {output_file}...", flush=True)
        storage.add_notdef()
        storage.finalize()
        storage.save(output_path)
        output_files.append(output_path)

    return output_files


def create_color_font_files(color_glyph_map, space_by_font_id, output_dir, output_font_name):
    """Compiles one colour (sbix) TrueType font per pack font id, plus the finalized
    storages the JSON sidecar is assembled from.

    This is a separate single-Regular emission that never touches create_font_files
    or its four-style fan-out: bold smears a bitmap grid and italic is a vector
    shear, both meaningless on a raster cell, so colour is Regular-only. Each font's
    glyph set is seeded ONLY from that font id's raster tiles plus .notdef (no
    vanilla/unifont clone), so numGlyphs stays tiny and far under the 65535 ceiling.

    A font id that contributes only space-provider advances mints no glyph and so no
    .ttf, but its storage still rides in the returned list so its sidecar rows are
    not lost. Output names are pack-qualified (`{name}-Color-{font_id}.ttf`); on the
    rare event two font ids sanitize to the same base, the later one gains a short
    stable sha1(font_id) suffix. Returns (color_files, storages) where color_files is
    the list of (path, font_id) for the files actually written."""
    if not color_glyph_map and not space_by_font_id:
        log("→ ℹ️ No colour glyphs to emit.")
        return [], []

    log("🎨 Creating colour (sbix) font files...")
    color_files = []
    storages = []
    seen_names = set()

    for font_id in sorted(set(color_glyph_map) | set(space_by_font_id)):
        font = TTFont()
        create_font_header_table(font, use_cff=False)
        create_font_hheader_table(font, use_cff=False)
        create_font_mprofile_table(font, use_cff=False)
        create_font_pscript_table(font, use_cff=False)
        create_font_hmetrics_table(font)
        create_font_name_table(font, bold=False, italic=False, family_qualifier=font_id)
        create_font_metrics_table(font)
        create_font_mapping_table(font)
        create_tt_font_tables(font)

        storage = GlyphStorage(font, use_cff=False, color_mode=True)
        for tile in color_glyph_map.get(font_id, {}).values():
            storage.add(storage.create_glyph(tile))
        for codepoint, advance in space_by_font_id.get(font_id, []):
            storage.add_space_row(font_id, codepoint, advance)
        storage.add_notdef()
        storage.finalize()
        storages.append(storage)

        # A font id with no raster strikes contributes only sidecar rows; emitting a
        # glyphless .ttf for it would be dead weight, so skip the file (keep the rows).
        if not storage.sbix_strikes:
            continue

        base = f"{output_font_name}-{COLOR_OUTPUT_INFIX}-{sanitize_fs_name(font_id)}"
        if base in seen_names:
            base = f"{base}-{hashlib.sha1(font_id.encode('utf-8')).hexdigest()[:8]}"
        seen_names.add(base)

        output_file = f"{base}.ttf"
        output_path = f"{output_dir}/{output_file}"
        log(f"→ ☕ {output_file}...", flush=True)
        storage.save(output_path)
        color_files.append((output_path, font_id))

    return color_files, storages
