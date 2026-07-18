import argparse
import os
import sys

from dataclasses import dataclass

from minecraft_fontgen.config import OUTPUT_DIR, OPENTYPE, FONT_STYLES, RESOURCE_PACKS, INSET_SHARED_VERTICES, COLOR_GLYPHS

VALID_STYLES = {"regular", "bold", "italic", "bolditalic", "galactic", "illageralt"}


@dataclass(frozen=True)
class BuildOptions:
    silent: bool
    output_dir: str
    output_fonts: list
    mc_version: str | None
    use_cff: bool
    output_ext: str
    validate: bool
    resource_packs: tuple[str, ...]
    inset_vertices: bool
    color_glyphs: bool


def _load_env_file(path=".env"):
    """Loads key=value pairs from a .env file into os.environ (won't overwrite existing vars)."""
    if not os.path.isfile(path):
        return

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


def parse_args():
    """Parses CLI arguments with env var fallbacks. Returns a BuildOptions."""
    _load_env_file()

    parser = argparse.ArgumentParser(description="Minecraft bitmap font to OpenType/TrueType converter.")
    parser.add_argument("--silent", action="store_true", default=None,
                        help="Suppress all output except errors")
    parser.add_argument("--output", type=str, default=None,
                        help="Override output directory")
    parser.add_argument("--version", type=str, default=None,
                        help="Minecraft version to use (skips interactive prompt)")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated font styles: regular,bold,italic,bolditalic")
    parser.add_argument("--type", type=str, default=None,
                        help="Font type: opentype/otf or truetype/ttf (default: opentype)")
    parser.add_argument("--validate", action="store_true", default=None,
                        help="Run FontForge validation on generated fonts (requires fontforge)")
    parser.add_argument("--resource-pack", action="append", metavar="PATH", default=None,
                        help="Resource pack zip or directory whose font glyphs are merged into the "
                             "generated fonts (repeatable; later packs override earlier ones, and "
                             "all packs override vanilla)")
    parser.add_argument("--no-vertex-inset", action="store_true", default=None,
                        help="Disable the 1-unit inset of vertices shared between contours "
                             "(the inset silences FontForge wrong-direction warnings, but some "
                             "renderers show hairline gaps where contours touch)")
    parser.add_argument("--color-glyphs", action="store_true", default=None,
                        help="Additionally emit a colour (sbix) TrueType font per pack font id "
                             "plus a JSON sidecar; forces TrueType/.ttf output. The mono "
                             "OpenType/TrueType fonts are still emitted unchanged")

    args = parser.parse_args()

    # --- silent ---
    if args.silent is not None and args.silent:
        silent = True
    elif os.environ.get("MCFONT_SILENT", "").lower() in ("1", "true", "yes"):
        silent = True
    else:
        silent = False

    # --- output_dir ---
    if args.output is not None:
        output_dir = args.output
    elif os.environ.get("MCFONT_OUTPUT"):
        output_dir = os.environ["MCFONT_OUTPUT"]
    else:
        output_dir = OUTPUT_DIR

    # --- styles ---
    raw_styles = None
    if args.styles is not None:
        raw_styles = args.styles
    elif os.environ.get("MCFONT_STYLES"):
        raw_styles = os.environ["MCFONT_STYLES"]

    if raw_styles is not None:
        requested = {s.strip().lower() for s in raw_styles.split(",")}
        invalid = requested - VALID_STYLES
        if invalid:
            parser.error(f"Invalid style(s): {', '.join(sorted(invalid))}. "
                         f"Valid options: {', '.join(sorted(VALID_STYLES))}")
        output_fonts = [
            {**style, "enabled": style["name"].lower() in requested}
            for style in FONT_STYLES
        ]
    else:
        output_fonts = FONT_STYLES

    # --- version ---
    if args.version is not None:
        mc_version = args.version
    elif os.environ.get("MCFONT_VERSION"):
        mc_version = os.environ["MCFONT_VERSION"]
    else:
        mc_version = None

    # --- type ---
    valid_types = {"opentype": True, "otf": True, "truetype": False, "ttf": False}
    raw_type = None
    if args.type is not None:
        raw_type = args.type
    elif os.environ.get("MCFONT_TYPE"):
        raw_type = os.environ["MCFONT_TYPE"]

    if raw_type is not None:
        key = raw_type.strip().lower()
        if key not in valid_types:
            parser.error(f"Invalid type: {raw_type}. Valid options: opentype, otf, truetype, ttf")
        use_cff = valid_types[key]
    else:
        use_cff = OPENTYPE

    output_ext = "otf" if use_cff else "ttf"

    # --- colour glyphs ---
    if args.color_glyphs is not None and args.color_glyphs:
        color_glyphs = True
    elif os.environ.get("MCFONT_COLOR_GLYPHS", "").lower() in ("1", "true", "yes"):
        color_glyphs = True
    else:
        color_glyphs = COLOR_GLYPHS

    # Colour strikes ride in a TrueType-flavoured sfnt, so the mode forces
    # TrueType/.ttf. If the user explicitly asked for OpenType we warn about the
    # override; a defaulted or already-TrueType type is coerced silently.
    if color_glyphs and use_cff:
        if raw_type is not None and raw_type.strip().lower() in ("opentype", "otf"):
            print("→ ⚠️ --color-glyphs forces TrueType output; ignoring --type "
                  f"{raw_type}", file=sys.stderr)
        use_cff = False
        output_ext = "ttf"

    # --- validate ---
    if args.validate is not None and args.validate:
        validate = True
    elif os.environ.get("MCFONT_VALIDATE", "").lower() in ("1", "true", "yes"):
        validate = True
    else:
        validate = False

    # --- vertex inset ---
    if args.no_vertex_inset is not None and args.no_vertex_inset:
        inset_vertices = False
    elif os.environ.get("MCFONT_NO_VERTEX_INSET", "").lower() in ("1", "true", "yes"):
        inset_vertices = False
    else:
        inset_vertices = INSET_SHARED_VERTICES

    # --- resource packs ---
    if args.resource_pack:
        raw_packs = args.resource_pack
    elif os.environ.get("MCFONT_RESOURCE_PACKS"):
        raw_packs = [p for p in os.environ["MCFONT_RESOURCE_PACKS"].split(os.pathsep) if p.strip()]
    else:
        raw_packs = list(RESOURCE_PACKS)

    resource_packs = []
    for pack in raw_packs:
        pack_path = os.path.abspath(pack)
        if not os.path.exists(pack_path):
            parser.error(f"Resource pack not found: {pack}")
        resource_packs.append(pack_path)

    return BuildOptions(
        silent=silent,
        output_dir=output_dir,
        output_fonts=output_fonts,
        mc_version=mc_version,
        use_cff=use_cff,
        output_ext=output_ext,
        validate=validate,
        resource_packs=tuple(resource_packs),
        inset_vertices=inset_vertices,
        color_glyphs=color_glyphs,
    )
