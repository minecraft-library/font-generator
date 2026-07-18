import sys

from fontTools.ttLib import TTFont
from tqdm import tqdm

from minecraft_fontgen.config import VANILLA_PACK_ID
from minecraft_fontgen.functions import log, is_silent, allocate_stored_codepoints

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

def _init_font(spec, use_cff):
    """Builds an empty TTFont with all shared tables for one font spec.

    This is the single header/name/table creation path both the mono styles and the
    colour fonts run through: a colour spec forces TrueType (use_cff False) and folds
    its namespace into the name table via family_qualifier, but every other call is
    identical to the mono path, so mono output stays byte-identical."""
    font = TTFont()
    create_font_header_table(font, use_cff)
    create_font_hheader_table(font, use_cff)
    create_font_mprofile_table(font, use_cff)
    create_font_pscript_table(font, use_cff)
    create_font_hmetrics_table(font)
    create_font_name_table(font, spec["bold"], spec["italic"],
                           family_qualifier=spec.get("family_qualifier"))
    create_font_metrics_table(font)
    create_font_mapping_table(font)
    if use_cff:
        create_ot_font_tables(font, spec["bold"], spec["italic"])
    else:
        create_tt_font_tables(font)
    return font

def _fill_color_storage(storage, color_glyph_map, space_by_font_id):
    """Populates a colour storage from one pack's glyph map and space rows.

    Every (font_id, original_codepoint) raster pair is assigned a synthetic STORED
    codepoint from plane 15/16 (see functions.allocate_stored_codepoints), so
    codepoints that different font ids reuse coexist in one merged font. Allocation is
    deterministic: the pairs are sorted by (font_id, original_codepoint) and assigned
    linearly from U+F0000, so the same input yields a byte-identical font + sidecar.
    Pack-wide content dedup collapses identical art to one glyph (many sidecar rows may
    share a gid). Space rows (no glyph) ride in the storage in a stable order."""
    pairs = [(font_id, codepoint)
             for font_id in sorted(color_glyph_map)
             for codepoint in sorted(color_glyph_map[font_id])]
    stored_by_pair = allocate_stored_codepoints(pairs)
    for font_id, codepoint in pairs:
        tile = dict(color_glyph_map[font_id][codepoint])
        tile["stored_codepoint"] = stored_by_pair[(font_id, codepoint)]
        storage.add(storage.create_glyph(tile))

    for font_id in sorted(space_by_font_id):
        for codepoint, advance in space_by_font_id[font_id]:
            storage.add_space_row(font_id, codepoint, advance)

def create_font_files(glyph_map, use_cff, output_fonts, output_dir, output_font_name,
                      output_file_ext, color_fonts=()):
    """Creates all enabled font files in batch through one shared loop.

    The mono styles (output_fonts) and the per-pack colour fonts (color_fonts) are
    driven by the same init/save loop: tables are created once through _init_font, and
    the only branch is the glyph-drawing pass (mono traces contours; colour adds
    pre-encoded sbix cells plus space rows). Colour fonts are Regular-only TrueType and
    force use_cff off; mono output is byte-identical whether or not colour is present.

    Returns (output_files, color_results):
      - output_files: the written mono font paths.
      - color_results: one (spec, color_file, storage) per colour font, where
        color_file is None for a space-only pack (no strikes, no .ttf) and storage is
        the finalized GlyphStorage the JSON sidecar is assembled from."""
    font_icon = "🅾️" if use_cff else "🆎"
    font_type = "OpenType" if use_cff else "TrueType"
    enabled_fonts = [f for f in output_fonts if f["enabled"]]
    color_fonts = list(color_fonts)
    specs = enabled_fonts + color_fonts

    if not specs:
        log("→ ⚠️ No font styles enabled.")
        return [], []

    log(f"{font_icon} Creating {font_type} font files...")

    # Initialize font tables and glyph storages for every spec (mono + colour) through
    # the single shared creation path. A colour spec is Regular-only TrueType and is
    # tagged with the vanilla/colour pack identity for a uniform "identified source"
    # model; mono styles inherit the vanilla pack id.
    storages = {}
    for spec in specs:
        is_color = spec.get("color", False)
        spec_cff = use_cff and not is_color  # colour rides in a TrueType-flavoured sfnt
        # Every font stores the identity of the source it came from; the mono styles
        # inherit the vanilla pack id, colour fonts carry their own pack's id.
        pack_id = spec.get("pack_id", VANILLA_PACK_ID)
        log(f"→ 📄 Initializing {spec['name'].lower()} tables...")
        font = _init_font(spec, spec_cff)
        storages[spec["name"]] = (
            GlyphStorage(font, spec_cff, color_mode=is_color, pack_id=pack_id), spec)

    # Filter out mono fonts whose pixel style isn't in the glyph map (e.g. Galactic when
    # alt.json is missing). Colour fonts carry no pixel style and are drawn separately.
    available_fonts = [f for f in enabled_fonts if f["pixel_style"] in glyph_map]
    for f in enabled_fonts:
        if f["pixel_style"] not in glyph_map:
            log(f"→ ⚠️ Skipping {f['name']} (alternate font assets not found in this version)")

    # Mono glyph-drawing pass: convert glyphs for all mono styles in a single sweep.
    if available_fonts:
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

    # Colour glyph pass: each pack's raster cells + space rows fill its storage.
    for spec in color_fonts:
        log(f"🎨 Compiling the {spec['name'].lower()} colour font...")
        _fill_color_storage(storages[spec["name"]][0], spec["color_map"], spec["space_rows"])

    # Finalize and save all fonts through the shared save loop.
    log(f"💾 Saving font files...", flush=True)
    output_files = []
    color_results = []
    for font_name, (storage, spec) in storages.items():
        if spec.get("color", False):
            storage.add_notdef()
            storage.finalize()
            # A pack with only space advances mints no strike; emitting a glyphless
            # .ttf would be dead weight, so skip the file but keep the storage (its
            # rows still reach the sidecar).
            if not storage.sbix_strikes:
                color_results.append((spec, None, storage))
                continue
            output_file = f"{output_font_name}-{spec['name']}.ttf"
            output_path = f"{output_dir}/{output_file}"
            log(f"→ ☕ {output_file}...", flush=True)
            storage.save(output_path)
            color_results.append((spec, output_path, storage))
            continue

        if spec["pixel_style"] not in glyph_map:
            continue

        output_file = f"{output_font_name}-{font_name}.{output_file_ext}"
        output_path = f"{output_dir}/{output_file}"
        log(f"→ ☕ {output_file}...", flush=True)
        storage.add_notdef()
        storage.finalize()
        storage.save(output_path)
        output_files.append(output_path)

    return output_files, color_results
