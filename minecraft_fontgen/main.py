import sys
import io

from minecraft_fontgen.asset_source import AssetStack, VanillaSource, open_resource_pack
from minecraft_fontgen.cli import parse_args
from minecraft_fontgen.piston import download_minecraft_assets
from minecraft_fontgen.file_io import clean_directories, collect_pack_providers, parse_provider_file, build_glyph_map
from minecraft_fontgen.font_creator import create_font_files
from minecraft_fontgen.config import OUTPUT_FONT_NAME
from minecraft_fontgen.functions import set_silent, log, validate_fonts
from minecraft_fontgen.preview_font import write_preview_image, write_render_image

# Force UTF-8 output to handle emoji in print statements
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def main():
    """Runs the font generation pipeline: download, parse, build glyph map, create fonts."""
    opts = parse_args()
    set_silent(opts.silent)

    # Open packs one at a time before any network or destructive work so bad
    # paths fail fast; close any already-opened source if a later one fails
    pack_sources = []
    try:
        for p in opts.resource_packs:
            pack_sources.append(open_resource_pack(p))
    except ValueError as error:
        for source in pack_sources:
            source.close()
        log(f"❌ {error}")
        raise SystemExit(1)

    # Layer user resource packs above the vanilla extraction (later packs win)
    stack = AssetStack([VanillaSource()] + pack_sources)
    try:
        # Clean work and output directories
        clean_directories(opts.output_dir)

        # Download MC version, extract unifont + JAR assets
        matched_file, matched_format, unifont_glyphs = download_minecraft_assets(opts.mc_version)

        # Parse provider glyphs from JAR bitmap PNGs (includes slicing)
        providers = parse_provider_file(matched_file, matched_format, stack)

        # Append pack providers after vanilla so they win the last-wins merge
        providers += collect_pack_providers(stack)

        # Build unified glyph map with pre-computed scaling
        glyph_map = build_glyph_map(providers, unifont_glyphs, stack)
    finally:
        stack.close()

    # Generate all font files
    font_files = create_font_files(glyph_map, opts.use_cff, opts.output_fonts, opts.output_dir, OUTPUT_FONT_NAME, opts.output_ext)

    if opts.validate and font_files:
        # Validate with FontForge (development only: --validate or MCFONT_VALIDATE=1)
        validate_fonts(font_files)

        # Write visual preview images
        write_preview_image(font_files, opts.output_dir)
        write_render_image(font_files[0], opts.output_dir)

    log("Done.")

if __name__ == "__main__":
    main()
