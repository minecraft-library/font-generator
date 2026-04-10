# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Minecraft Font Generator converts Minecraft's bitmap font glyphs into OpenType (CFF) or TrueType font files. It downloads a selected Minecraft version's JAR via the Piston API, extracts bitmap PNG textures and font provider JSON, then traces pixel contours into vector outlines and assembles complete `.otf`/`.ttf` fonts using fontTools.

## Commands

```bash
# Activate venv
.venv/Scripts/activate    # Windows

# Install dependencies
pip install -e .

# Run the tool (interactive - prompts for Minecraft version)
python -m minecraft_fontgen

# Run non-interactively
python -m minecraft_fontgen --version 1.21.4 --styles regular,bold --output dist/fonts --silent

# Run with FontForge validation (requires fontforge installed)
python -m minecraft_fontgen --version 1.21.4 --validate

# Or via environment variable (useful for IDE run configurations)
MCFONT_VALIDATE=1 python -m minecraft_fontgen --version 1.21.4

# Validate an existing font file directly
fontforge -lang=py -script minecraft_fontgen/validate_font.py output/Minecraft-Regular.otf
```

There are no tests or linting configured.

### CLI Arguments and Environment Variables

`parse_args()` in `cli.py` resolves configuration with this priority: CLI arg > shell env var > `.env` file > `config.py` defaults.

| CLI Argument | Env Var | Description | Default |
|---|---|---|---|
| `--version` | `MCFONT_VERSION` | Minecraft version (skips interactive prompt when set) | `None` (interactive) |
| `--output` | `MCFONT_OUTPUT` | Output directory for font files | `output` |
| `--styles` | `MCFONT_STYLES` | Comma-separated styles: `regular,bold,italic,bolditalic,galactic,illageralt` | All enabled in `config.py` |
| `--type` | `MCFONT_TYPE` | Font type: `opentype`/`otf` or `truetype`/`ttf` | `opentype` |
| `--silent` | `MCFONT_SILENT` | Suppress output (`1`/`true`/`yes`) | `False` |
| `--validate` | `MCFONT_VALIDATE` | Run FontForge validation after build (`1`/`true`/`yes`) | `False` |

## Architecture

### Pipeline (minecraft_fontgen/main.py)

The pipeline runs sequentially through six stages:

1. **Clean** (`minecraft_fontgen.file_io:clean_directories`) - Wipes and recreates `work/` and `output/` directories
2. **Download** (`minecraft_fontgen.piston:download_minecraft_assets`) - Selects a Minecraft version (non-interactively via `--version`/`MCFONT_VERSION`, or interactively via prompt). Downloads version manifest, client JAR, and extracts font assets to `work/`. Then downloads unifont hex files if enabled. Returns the matched font file path, format, and unifont glyph data
3. **Parse + Slice** (`minecraft_fontgen.file_io:parse_provider_file`) - Reads `include/default.json` from the extracted JAR to discover bitmap font providers (PNG files + Unicode character mappings). Internally calls `slice_provider_tiles` to crop individual glyphs from bitmap PNGs, trace contours with flood-fill labeling, and generate SVG debug output
4. **Build glyph map** (`minecraft_fontgen.file_io:build_glyph_map`) - Merges provider glyphs (priority) with unifont fallback glyphs into an `OrderedDict` keyed by codepoint, per style (Regular/Bold). Processes alternate fonts (Galactic, Illageralt) by cloning the Regular glyph map and overlaying alternate glyphs from their JSON provider files. Pre-computes scaled coordinates (pixel space to font units) for all glyphs via `precompute_glyph_scaling`
5. **Create font files** (`minecraft_fontgen.font_creator:create_font_files`) - Batch creates all enabled font styles (Regular, Bold, Italic, BoldItalic, Galactic, Illageralt). Initializes fontTools `TTFont` tables for each style, converts glyphs with a single progress bar across all styles, then finalizes and saves all fonts. Styles whose glyph map is missing (e.g. Galactic on older versions) are gracefully skipped. Returns the list of output file paths
6. **Validate** (`minecraft_fontgen.functions:validate_fonts`) - Optional, runs only when `--validate` or `MCFONT_VALIDATE=1` is set. Invokes `validate_font.py` via FontForge subprocess on all generated font files. Reports per-glyph validation errors bucketed by type

### Glyph Processing

- `minecraft_fontgen.file_io:_trace_bitmap_contours` - Core contour tracing: flood-fill labels pixel groups, traces boundary edges using right-hand rule, extracts corner points for vector outlines. Bold glyphs get a 1px rightward expansion before tracing
- `minecraft_fontgen.file_io:precompute_glyph_scaling` - Scales glyph coordinates from pixel space to font units using `UNITS_PER_EM / tile_height` (e.g. 128 for 8px provider glyphs, 64 for 16px unifont glyphs). Splits self-touching contours at duplicate vertices and insets shared vertices between contours. This is style-independent; only italic shear differs and is applied as a lightweight post-transform per font
- `minecraft_fontgen.glyph.glyph:Glyph` - Assigns pre-computed scaled coordinates, applies italic shear transform if needed, draws contours with winding direction based on geometric nesting depth via fontTools pen (T2CharStringPen for CFF, TTGlyphPen for TrueType). Advance width in the CFF pen uses `self.size[1]` (tile height) for the scale factor
- `minecraft_fontgen.glyph.glyph_storage:GlyphStorage` - Accumulates glyphs, manages cmap table entries (Format 4 for BMP, Format 12 for SMP), writes final glyph order and metrics. Advance width calculation uses `glyph.size[1]` (tile height) for the scale factor

### Font Table Modules (minecraft_fontgen/table/)

Each file creates one OpenType/TrueType table via `fontTools.ttLib.newTable()`. They set initial values; `GlyphStorage.finalize()` patches final glyph-dependent values (numGlyphs, charIndex ranges, average widths, etc.) after all glyphs are added.

- `header.py` - `head` table (timestamps, bounding box, unitsPerEm)
- `horizontal_header.py` - `hhea` table (ascent, descent, line gap)
- `maximum_profile.py` - `maxp` table (glyph count placeholder)
- `postscript.py` - `post` table (italic angle, underline, fixed pitch)
- `horizontal_metrics.py` - `hmtx` table (advance widths, LSBs)
- `name.py` - `name` table (family, style, version, metadata strings)
- `os2_metrics.py` - `OS/2` table (weight class, panose, unicode ranges)
- `glyph_mappings.py` - `cmap` table (Format 4 for BMP, Format 12 for SMP)
- `opentype.py` - CFF tables (font set, top dict, charstrings)
- `truetype.py` - TrueType tables (glyf, loca)

### Key Constants (minecraft_fontgen/config.py)

Configuration is module-level constants, not CLI args (unless noted). Key settings:
- `OPENTYPE = True` - CFF (OpenType) vs TrueType outlines (overridable via `--type`/`MCFONT_TYPE`)
- `UNIFONT = True` - Include GNU Unifont fallback glyphs
- `FONT_STYLES` - List of dicts defining all font styles. Each has `name`, `enabled`, `bold`, `italic`, `pixel_style`, `debug`. Alternate styles also have `json_file` and `map_lowercase`. Toggle `enabled` to include/exclude a style. The `debug` dict has keys `svg` (pixel grid SVGs + path SVGs for provider tiles), `bmp` (cropped glyph bitmaps), and `unifont` (pixel grid SVGs for unifont fallback glyphs), all defaulting to `False`
- `UNITS_PER_EM = 1024`, `DEFAULT_GLYPH_SIZE = 8` - Font metrics. `DEFAULT_GLYPH_SIZE` is a fallback default for missing tile sizes; the actual scale factor uses each tile's height from `tile["size"][1]` (8 for provider glyphs, 16 for unifont)
- `BOUNDING_BOX = [0, -128, 1152, 896]` - Global glyph bounds
- `OUTPUT_FONT_NAME = "Minecraft"` - Output font family name

### Batch Font Creation

All enabled font styles are created in a single batch call (`create_font_files`). The process:
1. Initialize `TTFont` + `GlyphStorage` for each enabled style
2. Single `tqdm` progress bar iterates all styles, showing the current style name
3. For each glyph: create from tile, validate, apply pre-computed scaling (with italic shear if needed), draw, and add to storage
4. Finalize all fonts (add .notdef, write glyph order/metrics) and save

Pens are per-font (CFF T2CharString or TT glyph), so glyph objects cannot be shared between styles. However, the pre-computed scaling coordinates are shared since they are style-independent. Alternate font styles (Galactic, Illageralt) use their own glyph maps but follow the same creation pipeline. Styles whose `pixel_style` key is missing from the glyph map are skipped with a warning.

### Italic Handling

Italic and BoldItalic reuse Regular/Bold pixel data respectively. The italic shear is applied during `Glyph.scale()` by adding `sy * ITALIC_SHEAR_FACTOR` to x-coordinates of the pre-computed base coordinates.

### Alternate Fonts (Galactic, Illageralt)

Minecraft includes alternate font scripts: Standard Galactic Alphabet (enchanting table text) and Illageralt (Illager runes). These are handled as overlay styles on top of the Regular glyph map:

1. `_process_alternate_font()` in `file_io.py` reads the font's JSON provider file (e.g. `font/alt.json`), extracts the bitmap texture and character mappings, traces contours, then clones the full Regular glyph map and replaces matching codepoints with alternate glyphs
2. For Galactic, `map_lowercase: True` duplicates uppercase glyphs (A-Z) onto lowercase codepoints (a-z) since the Standard Galactic Alphabet only defines uppercase
3. The resulting overlay maps are stored under their style name (`"Galactic"`, `"Illageralt"`) in the glyph map dict
4. If the JSON file doesn't exist (e.g. Minecraft 1.8.9 lacks `alt.json`), the style is silently skipped during both glyph map building and font creation

Configuration lives in `config.py:FONT_STYLES` — alternate styles are identified by the presence of `json_file` and `map_lowercase` keys. Only JSON file paths are stored, not character mappings. Mappings are read from the JSON at runtime.

### Unifont Fallback

When `UNIFONT = True`, GNU Unifont hex files are downloaded from Minecraft's asset index and parsed into 16-row bitmap grids (`minecraft_fontgen.piston:parse_unifont_hex_bytes`). These are traced into tile dicts via `trace_unifont_tiles` and merged as fallbacks (lower priority than provider glyphs) in `build_glyph_map`. The `UNIFONT_RANGES` config controls which Unicode ranges are included. Unifont glyphs are duospaced (8px half-width or 16px full-width) in a 16px-tall grid. The scale factor `UNITS_PER_EM / 16 = 64` gives full-width glyphs 1.0em advance and half-width glyphs ~0.5em advance.

### Directory Layout at Runtime

- `work/` - Downloaded JAR, extracted assets, sliced tile bitmaps + debug SVGs (gitignored)
- `output/` - Generated `.otf`/`.ttf` files (gitignored)
- `font/` - Reference copies of Minecraft's font provider JSONs
- `minecraft_fontgen/validate_font.py` - FontForge validation script (run via `fontforge -lang=py -script` subprocess, not imported as a module)

## Dependencies

fontTools (font building), Pillow (bitmap processing), numpy (pixel grid operations), requests (Mojang API downloads), tqdm (progress bars), svgpathtools/uharfbuzz (SVG utilities). Python 3.10+.

## Module Import Style

Source files use absolute imports from the `minecraft_fontgen` package (e.g., `from minecraft_fontgen.config import ...`). The project uses the PyPA src layout with `__init__.py` files and runs as `python -m minecraft_fontgen`.
