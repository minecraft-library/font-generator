import os
import sys
import io

from minecraft_fontgen.asset_source import AssetStack, VanillaSource, open_resource_pack
from minecraft_fontgen.cli import parse_args
from minecraft_fontgen.piston import download_minecraft_assets
from minecraft_fontgen.file_io import (
    clean_directories, collect_pack_providers, parse_provider_file, build_glyph_map,
    collect_color_fonts,
)
from minecraft_fontgen.font_creator import create_font_files
from minecraft_fontgen.colour_sidecar import build_sidecar, write_sidecar, sidecar_name
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

    pack_sources = open_resource_packs(opts.resource_packs)

    # Layer user resource packs above the vanilla extraction (later packs win)
    stack = AssetStack([VanillaSource()] + pack_sources)
    color_fonts = []
    try:
        # Clean work and output directories
        clean_directories(opts.output_dir)

        # Download MC version, extract unifont + JAR assets
        matched_file, matched_format, unifont_glyphs = download_minecraft_assets(opts.mc_version)

        # Parse provider glyphs from JAR bitmap PNGs (includes slicing)
        providers = parse_provider_file(matched_file, matched_format, stack)

        # Append pack providers after vanilla so they win the last-wins merge
        providers += collect_pack_providers(stack, opts.color_glyphs)

        # Colour is a second, additive track: compose one colour font spec per source
        # pack (a no-op that returns [] when the flag is off), collected in the same
        # file_io layer as the mono pack providers.
        if opts.color_glyphs:
            color_fonts = collect_color_fonts(stack, opts.color_glyphs)

        # Build unified glyph map with pre-computed scaling
        glyph_map = build_glyph_map(providers, unifont_glyphs, stack, inset_vertices=opts.inset_vertices)
    finally:
        stack.close()

    # Generate all font files through the shared loop: the mono styles plus one merged
    # sbix TrueType per colour pack. The mono product is emitted unchanged whether or
    # not colour is on (the classifier removed raster codepoints from the mono map).
    font_files, color_results = create_font_files(
        glyph_map, opts.use_cff, opts.output_fonts, opts.output_dir,
        OUTPUT_FONT_NAME, opts.output_ext, color_fonts=color_fonts)

    # Each colour pack writes its own sidecar naming its own merged font file.
    for spec, color_file, color_storage in color_results:
        if color_storage is None:
            continue
        file_ref = os.path.basename(color_file) if color_file else None
        sidecar = build_sidecar(file_ref, color_storage, resolve_source_date_epoch())
        write_sidecar(sidecar, opts.output_dir, name=sidecar_name(spec["name"]))

    if opts.validate and font_files:
        # Validate with FontForge (development only: --validate or MCFONT_VALIDATE=1)
        validate_fonts(font_files)

        # Write visual preview images
        write_preview_image(font_files, opts.output_dir)
        write_render_image(font_files[0], opts.output_dir)

    log("Done.")

if __name__ == "__main__":
    main()
