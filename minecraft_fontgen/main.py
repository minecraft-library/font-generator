import sys
import io

from minecraft_fontgen.cli import parse_args
from minecraft_fontgen.piston import download_minecraft_assets
from minecraft_fontgen.file_io import clean_directories, parse_provider_file, build_glyph_map
from minecraft_fontgen.font_creator import create_font_files
from minecraft_fontgen.config import OUTPUT_FONT_NAME
from minecraft_fontgen.functions import set_silent, log, validate_fonts
from minecraft_fontgen.preview_font import write_preview_image, write_render_image

# Force UTF-8 output to handle emoji in print statements
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def main():
    """Runs the font generation pipeline: download, parse, build glyph map, create fonts."""
    # Parse user provided arguments
    silent, output_dir, output_fonts, mc_version, use_cff, output_ext, validate = parse_args()
    set_silent(silent)

    # Clean work and output directories
    clean_directories(output_dir)

    # Download MC version, extract unifont + JAR assets
    matched_file, matched_format, unifont_glyphs = download_minecraft_assets(mc_version)

    # Parse provider glyphs from JAR bitmap PNGs (includes slicing)
    providers = parse_provider_file(matched_file, matched_format)

    # Build unified glyph map with pre-computed scaling
    glyph_map = build_glyph_map(providers, unifont_glyphs)

    # Generate all font files
    font_files = create_font_files(glyph_map, use_cff, output_fonts, output_dir, OUTPUT_FONT_NAME, output_ext)

    if validate and font_files:
        # Validate with FontForge (development only: --validate or MCFONT_VALIDATE=1)
        validate_fonts(font_files)

        # Write visual preview images
        write_preview_image(font_files, output_dir)
        write_render_image(font_files[0], output_dir)

    log("Done.")

if __name__ == "__main__":
    main()
