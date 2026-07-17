import os
import sys
import io

import minecraft_fontgen.config as config
from minecraft_fontgen.asset_source import AssetStack, VanillaSource, open_resource_pack
from minecraft_fontgen.cli import parse_args
from minecraft_fontgen.piston import download_minecraft_assets
from minecraft_fontgen.file_io import (
    clean_directories, collect_pack_providers, parse_provider_file, build_glyph_map,
    collect_color_providers, build_color_glyph_map, group_color_space_rows,
)
from minecraft_fontgen.font_creator import create_font_files, create_color_font_files
from minecraft_fontgen.colour_sidecar import build_sidecar, write_sidecar
from minecraft_fontgen.config import OUTPUT_FONT_NAME
from minecraft_fontgen.functions import set_silent, log, validate_fonts, resolve_source_date_epoch
from minecraft_fontgen.preview_font import write_preview_image, write_render_image

# Force UTF-8 output to handle emoji in print statements
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def open_resource_packs(paths):
    """Opens every resource pack before any network or destructive work so bad
    paths fail fast; closes any already-opened source if a later one fails."""
    pack_sources = []
    try:
        for path in paths:
            pack_sources.append(open_resource_pack(path))
    except ValueError as error:
        for source in pack_sources:
            source.close()
        log(f"❌ {error}")
        raise SystemExit(1)
    return pack_sources

def main():
    """Runs the font generation pipeline: download, parse, build glyph map, create fonts."""
    opts = parse_args()
    set_silent(opts.silent)
    # The colour track is gated on this module-level flag, which the ingestion
    # helpers read at runtime; mirror the resolved CLI/env option onto it.
    config.COLOR_GLYPHS = opts.color_glyphs

    pack_sources = open_resource_packs(opts.resource_packs)

    # Layer user resource packs above the vanilla extraction (later packs win)
    stack = AssetStack([VanillaSource()] + pack_sources)
    color_providers = []
    try:
        # Clean work and output directories
        clean_directories(opts.output_dir)

        # Download MC version, extract unifont + JAR assets
        matched_file, matched_format, unifont_glyphs = download_minecraft_assets(opts.mc_version)

        # Parse provider glyphs from JAR bitmap PNGs (includes slicing)
        providers = parse_provider_file(matched_file, matched_format, stack)

        # Append pack providers after vanilla so they win the last-wins merge
        providers += collect_pack_providers(stack)

        # Colour is a second, additive track: ingest every pack font file's colour
        # cells and space advances (a no-op that returns [] when the flag is off).
        if opts.color_glyphs:
            color_providers = collect_color_providers(stack)

        # Build unified glyph map with pre-computed scaling
        glyph_map = build_glyph_map(providers, unifont_glyphs, stack, inset_vertices=opts.inset_vertices)
    finally:
        stack.close()

    # Generate all font files (the mono product is emitted unchanged whether or not
    # colour is on: the classifier removed raster codepoints from the mono map).
    font_files = create_font_files(glyph_map, opts.use_cff, opts.output_fonts, opts.output_dir, OUTPUT_FONT_NAME, opts.output_ext)

    # Additive colour pass: one sbix TrueType per pack font id plus the shared sidecar.
    if opts.color_glyphs:
        color_glyph_map = build_color_glyph_map(color_providers)
        space_by_font_id = group_color_space_rows(color_providers)
        color_files, color_storages = create_color_font_files(
            color_glyph_map, space_by_font_id, opts.output_dir, OUTPUT_FONT_NAME)
        if color_storages:
            fonts = [{"font_id": font_id, "file": os.path.basename(path)}
                     for path, font_id in color_files]
            sidecar = build_sidecar(fonts, color_storages, resolve_source_date_epoch())
            write_sidecar(sidecar, opts.output_dir)

    if opts.validate and font_files:
        # Validate with FontForge (development only: --validate or MCFONT_VALIDATE=1)
        validate_fonts(font_files)

        # Write visual preview images
        write_preview_image(font_files, opts.output_dir)
        write_render_image(font_files[0], opts.output_dir)

    log("Done.")

if __name__ == "__main__":
    main()
