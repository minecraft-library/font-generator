import sys

from fontTools.ttLib import TTFont
from tqdm import tqdm

from minecraft_fontgen.config import COLOR_OUTPUT_INFIX
from minecraft_fontgen.functions import log, is_silent
from minecraft_fontgen.stored_codepoint import allocate_stored_codepoints

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
    """Compiles ONE colour (sbix) TrueType font for the whole pack, plus the finalized
    storage the JSON sidecar is assembled from.

    This is a separate single-Regular emission that never touches create_font_files
    or its four-style fan-out: bold smears a bitmap grid and italic is a vector
    shear, both meaningless on a raster cell, so colour is Regular-only. The glyph
    set is seeded ONLY from the packs' raster tiles plus .notdef (no vanilla/unifont
    clone), so numGlyphs stays far under the 65535 ceiling.

    Every (font_id, original_codepoint) raster pair is assigned a synthetic STORED
    codepoint from plane 15/16 (see stored_codepoint.allocate_stored_codepoints), so
    codepoints that different font ids reuse coexist in one cmap. Pack-wide content
    dedup collapses identical art across font ids to one glyph (many sidecar rows may
    share a gid). Font ids that contribute only space-provider advances mint no glyph
    but their rows still ride in the returned storage.

    The output is a single `{name}-Color.ttf`. Returns (color_file, storage), where
    color_file is the written path or None (space-only: no strikes, no .ttf) and
    storage is the finalized GlyphStorage or None (nothing to emit at all)."""
    if not color_glyph_map and not space_by_font_id:
        log("→ ℹ️ No colour glyphs to emit.")
        return None, None

    log("🎨 Creating the colour (sbix) font file...")

    font = TTFont()
    create_font_header_table(font, use_cff=False)
    create_font_hheader_table(font, use_cff=False)
    create_font_mprofile_table(font, use_cff=False)
    create_font_pscript_table(font, use_cff=False)
    create_font_hmetrics_table(font)
    create_font_name_table(font, bold=False, italic=False, family_qualifier=COLOR_OUTPUT_INFIX)
    create_font_metrics_table(font)
    create_font_mapping_table(font)
    create_tt_font_tables(font)

    storage = GlyphStorage(font, use_cff=False, color_mode=True)

    # Deterministic stored-codepoint allocation: sort the raster pairs by
    # (font_id, original_codepoint) and assign linearly from U+F0000. Same input ->
    # byte-identical font + sidecar.
    pairs = [(font_id, codepoint)
             for font_id in sorted(color_glyph_map)
             for codepoint in sorted(color_glyph_map[font_id])]
    stored_by_pair = allocate_stored_codepoints(pairs)
    for font_id, codepoint in pairs:
        tile = dict(color_glyph_map[font_id][codepoint])
        tile["stored_codepoint"] = stored_by_pair[(font_id, codepoint)]
        storage.add(storage.create_glyph(tile))

    # Space rows (no glyph) in a stable (font_id, codepoint) order.
    for font_id in sorted(space_by_font_id):
        for codepoint, advance in space_by_font_id[font_id]:
            storage.add_space_row(font_id, codepoint, advance)

    storage.add_notdef()
    storage.finalize()

    # A pack with only space advances mints no strike; emitting a glyphless .ttf would
    # be dead weight, so skip the file but keep the storage (its rows reach the sidecar).
    if not storage.sbix_strikes:
        return None, storage

    output_file = f"{output_font_name}-{COLOR_OUTPUT_INFIX}.ttf"
    output_path = f"{output_dir}/{output_file}"
    log(f"→ ☕ {output_file}...", flush=True)
    storage.save(output_path)
    return output_path, storage
