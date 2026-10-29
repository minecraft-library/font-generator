import io
import json
import math
import os
import zipfile
from collections import OrderedDict, defaultdict
from fractions import Fraction
from types import SimpleNamespace

from PIL import Image


def make_png_bytes(width, height, pixels, color=(255, 255, 255, 255)):
    """Builds PNG bytes: a transparent canvas with the given pixels set to color."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for x, y in pixels:
        img.putpixel((x, y), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def block(x0, y0, w, h):
    """Returns pixel coordinates of a filled w x h rectangle at (x0, y0)."""
    return [(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)]


def font_json_bytes(providers):
    return json.dumps({"providers": providers}).encode("utf-8")


def write_pack_dir(root, files):
    """Writes {relative/path: bytes} under root, creating directories. Returns str(root)."""
    for rel, data in files.items():
        dest = os.path.join(str(root), *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
    return str(root)


def write_pack_zip(zip_path, files, root_prefix=""):
    """Writes {relative/path: bytes} into a zip, optionally under a nested root folder."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for rel, data in files.items():
            zf.writestr(root_prefix + rel, data)
    return str(zip_path)


class FakeSource:
    """Dict-backed AssetSource stand-in for unit tests."""

    def __init__(self, name, fonts=None, textures=None, vanilla=False):
        self.name = name
        self.fonts = fonts or {}
        self.textures = textures or {}
        self.is_vanilla = vanilla
        self.closed = False

    @property
    def pack_id(self):
        return self.name

    def get_font_json(self, font_id):
        return self.fonts.get(font_id)

    def get_texture(self, namespace, path):
        return self.textures.get(f"{namespace}:{path}")

    def list_font_ids(self):
        return list(self.fonts)

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# colour-glyph (sbix) test infrastructure
# ---------------------------------------------------------------------------

def color_cell(width, height, pixels, base=(0, 0, 0, 0)):
    """RGBA PIL image on a `base` canvas with {(x, y): (r, g, b, a)} painted."""
    img = Image.new("RGBA", (width, height), base)
    for (x, y), rgba in pixels.items():
        img.putpixel((x, y), rgba)
    return img


def flat_two_color_cell(width, height, left=(220, 40, 40, 255), right=(40, 60, 220, 255)):
    """Opaque cell split into two vertical colour bands (a classic raster icon)."""
    img = Image.new("RGBA", (width, height), left)
    for x in range(width // 2, width):
        for y in range(height):
            img.putpixel((x, y), right)
    return img


def make_raster_tile(codepoint, cell, display_height, ascent, font_id="test:demo"):
    """Builds a raster tile dict shaped exactly like slice_provider_tiles emits one,
    encoding + hashing the cell through the real file_io helpers."""
    from minecraft_fontgen.file_io import encode_cell_png, raster_cell_hash

    width, height = cell.size
    return {
        "unicode": chr(codepoint),
        "codepoint": codepoint,
        "size": (width, height),
        "display_height": display_height,
        "ascent": ascent,
        "font_id": font_id,
        "location": (0, 0),
        "render_mode": "raster",
        "raster_png": encode_cell_png(cell),
        "content_hash": raster_cell_hash(cell),
        "raster_size": (width, height),
    }


def color_font_spec(color_map, space_rows=None, namespace="Testpack", pack_id="testpack"):
    """Builds one colour font spec shaped exactly as file_io.collect_color_fonts emits,
    for create_font_files to consume alongside (or instead of) the mono styles."""
    return {
        "name": namespace,
        "enabled": True,
        "color": True,
        "bold": False,
        "italic": False,
        "pack_id": pack_id,
        "family_qualifier": namespace,
        "color_map": color_map,
        "space_rows": space_rows or {},
    }


def build_one_color_font(color_map, space_rows, outdir, font_name="Minecraft",
                         namespace="Testpack"):
    """Compiles a single pack's merged colour font through the real create_font_files
    loop (no mono styles) and returns (color_file, storage). This is the shared path
    the colour-compile tests drive, so they exercise the same code main() runs."""
    from minecraft_fontgen.font_creator import create_font_files

    spec = color_font_spec(color_map, space_rows, namespace=namespace)
    _, color_results = create_font_files({}, False, [], str(outdir), font_name, "ttf",
                                         color_fonts=[spec])
    _, color_file, storage = color_results[0]
    return color_file, storage


def build_color_font_storage(tiles):
    """Assembles one pack's merged colour TrueType font from raster tile dicts and
    returns the finalized GlyphStorage. Groups the tiles into a per-font-id colour map
    and drives the real create_font_files loop, so stored codepoints are allocated over
    the (font_id, codepoint) pairs exactly as the production compiler does."""
    import os
    import tempfile
    from collections import OrderedDict

    from minecraft_fontgen.file_io import build_color_glyph_map

    color_map = build_color_glyph_map([{"tiles": list(tiles)}])
    with tempfile.TemporaryDirectory() as tmp:
        _, storage = build_one_color_font(color_map, {}, tmp)
    return storage


def stored_cp_for(storage, codepoint, font_id="test:demo"):
    """Returns the stored codepoint the merged font assigned to an original
    (font_id, codepoint) raster pair, read back from the storage's sidecar rows."""
    for row in storage.sidecar_rows:
        if row["codepoint"] == codepoint and row["font_id"] == font_id:
            return row["stored_codepoint"]
    raise KeyError((font_id, codepoint))


def glyph_name_for(storage, codepoint, font_id="test:demo"):
    """Returns the compiled glyph name for an original (font_id, codepoint) raster
    pair. The merged font's cmap keys on stored codepoints, so tests resolve the
    strike by name through the sidecar row rather than getBestCmap()[original_cp]."""
    for row in storage.sidecar_rows:
        if row["codepoint"] == codepoint and row["font_id"] == font_id:
            return row["glyphName"]
    raise KeyError((font_id, codepoint))


def compiled_font_bytes(storage):
    """Compiles a finalized storage's font to bytes and returns them."""
    buf = io.BytesIO()
    storage.font.save(buf)
    return buf.getvalue()


def _encode_png(img):
    """PNG bytes of a PIL image with no spliced tEXt marker: colour cells are re-encoded
    crops verified by pixel-equality, not byte-identity, so a synthetic marker would only
    pollute the ancillary-chunk assertions."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_color_png_bytes(width, height, colored_pixels):
    """PNG bytes of a transparent RGBA canvas with {(x, y): (r, g, b, a)} painted."""
    return _encode_png(color_cell(width, height, colored_pixels))


def two_color_block_png(width, height, left=(220, 40, 40, 255), right=(40, 60, 220, 255)):
    """PNG bytes of an opaque cell split into two vertical colour bands (raster icon)."""
    return _encode_png(flat_two_color_cell(width, height, left=left, right=right))


def color_pack_source(font_id, cells, space_advances=None,
                      name="colorpack", height=8, ascent=7):
    """A FakeSource carrying one colour font file: a single-cell bitmap provider per
    (texture_ref -> (char, png_bytes)) entry plus an optional space provider.
    Everything is synthetic - no real pack assets."""
    providers = []
    textures = {}
    for ref, (char, png) in cells.items():
        providers.append({"type": "bitmap", "file": ref, "ascent": ascent,
                          "height": height, "chars": [char]})
        textures[ref] = png
    if space_advances:
        providers.append({"type": "space", "advances": space_advances})
    return FakeSource(name, fonts={font_id: font_json_bytes(providers)}, textures=textures)


# ---------------------------------------------------------------------------
# glyph geometry: the client's quad, and outlines sampled the way it samples
# ---------------------------------------------------------------------------

# Cells of the 26.1 font textures, '#' for ink, each drawn at ascent 7 unless noted. 'o' (U+006F) holds
# a counter whose diagonal pinches the slant puts on pixel-centre columns; the em dash (U+2014) inks the
# cell's last column; U+04BB and U+0394 each put a texel edge of the thickened bold-italic quad within
# 0.03 font units of a pixel centre at 16 px/em; U+00C0 is an accented 9x12 cell drawn at ascent 10.
# '"' (U+0022) holds one-texel holes the second bold copy all but fills; '!' (U+0021) and '$' (U+0024) each
# put a bold-italic texel edge within 1/64 of an output pixel of a pixel centre at 24 or 32 px/em.
CELL_FULL = ["########"] * 8
CELL_QUOTE = ["#.#.....", "#.#.....", "........", "........", "........", "........", "........", "........"]
CELL_BANG = ["#.......", "#.......", "#.......", "#.......", "#.......", "........", "#.......", "........"]
CELL_DOLLAR = ["..#.....", ".####...", "#.......", ".###....", "....#...", "####....", "..#.....", "........"]
CELL_O = ["........", "........", ".###....", "#...#...", "#...#...", "#...#...", ".###....", "........"]
CELL_DIAGONAL = ["........", ".#......", "..#.....", "...#....", "....#...", ".....#..", "........", "........"]
CELL_EM_DASH = ["........", "........", "........", "########", "........", "........", "........", "........"]
CELL_SHHA = ["#.......", "#.......", "#.##....", "##..#...", "#...#...", "#...#...", "#...#...", "........"]
CELL_DELTA = ["..#.....", "..#.....", ".#.#....", ".#.#....", ".#.#....", "#...#...", "#####...", "........"]
CELL_A_GRAVE = [".#.......", "..#......", ".........", ".###.....", "#...#....", "#####....", "#...#....",
                "#...#....", "#...#....", "#...#....", ".........", "........."]


def ink_grid(rows):
    """A 0/1 ink grid from '#' / '.' row strings."""
    return [[1 if c == "#" else 0 for c in row] for row in rows]


def first_ink_column(rows):
    """The first column of a '#' / '.' cell holding ink - the left padding the generator trims."""
    return min(row.index("#") for row in rows if "#" in row)


def bitmap_tile(rows, ascent=7, height=None, codepoint=0xE000, bold=False):
    """A bitmap-provider tile traced from '#' / '.' rows, displayed `height` GUI pixels tall (its row
    count unless given), drawing the client's two bold copies when `bold`."""
    import numpy as np
    from minecraft_fontgen.file_io import _trace_bitmap_contours2

    grid = np.array(ink_grid(rows), dtype=np.uint8)
    return {
        "unicode": chr(codepoint),
        "codepoint": codepoint,
        "size": (len(rows[0]), len(rows)),
        "display_height": len(rows) if height is None else height,
        "ascent": ascent,
        "pixels": _trace_bitmap_contours2(grid),
        "svg": None,
        "source": "provider",
        "bold_copies": bold,
    }


def unifont_tile(rows, codepoint=0xE000, bold=False):
    """A unifont fallback tile traced from 16 '#' / '.' rows."""
    import numpy as np
    from minecraft_fontgen.file_io import _trace_bitmap_contours2

    grid = np.array(ink_grid(rows), dtype=np.uint8)
    return {
        "unicode": chr(codepoint),
        "codepoint": codepoint,
        "size": (len(rows[0]), 16),
        "ascent": 15,
        "pixels": _trace_bitmap_contours2(grid),
        "svg": None,
        "source": "unifont",
        "bold_copies": bold,
    }


def scaled(tile):
    """Runs one tile through precompute_glyph_scaling and returns it."""
    from minecraft_fontgen.file_io import precompute_glyph_scaling

    precompute_glyph_scaling({"Regular": OrderedDict({tile["codepoint"]: tile})})
    return tile


def stored_advance(tile, italic=False):
    """Draws one scaled tile into a fresh CFF font's storage and returns the advance it was given."""
    from fontTools.ttLib import TTFont
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

    font = TTFont()
    create_font_header_table(font, True)
    create_font_hheader_table(font, True)
    create_font_mprofile_table(font, True)
    create_font_pscript_table(font, True)
    create_font_hmetrics_table(font)
    create_font_name_table(font, False, italic)
    create_font_metrics_table(font)
    create_font_mapping_table(font)
    create_ot_font_tables(font, False, italic)

    storage = GlyphStorage(font, use_cff=True)
    glyph = storage.create_glyph(tile)
    glyph.scale(italic=italic)
    glyph.draw()
    storage.add(glyph)
    return storage.hmtx[glyph.name][0]


def glyph_contours(tile, italic=False):
    """The contours a scaled tile's glyph is written with to a CFF font: drawn by Glyph as
    create_font_files draws it, then read back out of the compiled charstring, so in whole font units."""
    from fontTools.pens.recordingPen import RecordingPen
    from minecraft_fontgen.glyph.glyph import Glyph

    glyph = Glyph(tile, use_cff=True)
    glyph.scale(italic=italic)
    glyph.draw()
    charstring = glyph.build()
    charstring.private = SimpleNamespace(nominalWidthX=0, defaultWidthX=0)
    pen = RecordingPen()
    charstring.draw(pen)
    contours, current = [], []
    for op, args in pen.value:
        if op == "moveTo":
            current = [args[0]]
        elif op == "lineTo":
            current.append(args[0])
        elif op in ("closePath", "endPath"):
            contours.append(current)
            current = []
    return contours


def client_coverage(bitmap, ascent, height, bold=False, italic=False, gui_scale=2):
    """The output pixels the 26.1 client lights for one bitmap-provider glyph drawn at the pen.

    BakedSheetGlyph.render lays one quad over the whole cell, its corners (left + sT - t, up - t),
    (left + sB - t, down + t), (right + sB + t, down + t) and (right + sT + t, up - t) in GUI pixels
    from the pen and the line top: up = 7 - ascent, down = up + height, sT = 1 - up / 4 and
    sB = 1 - down / 4 when italic (0 when upright), t = 0.1 when bold. FontTexture.add insets the UVs
    by 0.01 texel. Bold draws the glyph again one GUI pixel right, that copy thickened too. Each output
    pixel centre (gui_scale per GUI pixel) samples the nearest texel and is lit where the texel is ink.
    Exact arithmetic throughout.

    Returns {(i, j)}: i output pixels right of the pen, j below the baseline (negative above it).
    """
    rows, cols = len(bitmap), len(bitmap[0])
    n = gui_scale
    up = 7 - Fraction(ascent)
    down = up + Fraction(height)
    width = cols * Fraction(height) / rows
    t = Fraction(1, 10) if bold else Fraction(0)
    s_top, s_bottom = (1 - up / 4, 1 - down / 4) if italic else (Fraction(0), Fraction(0))
    inset = Fraction(1, 100)
    quad_w, quad_h = width + 2 * t, down - up + 2 * t
    covered = set()
    for dx in ((0, 1) if bold else (0,)):
        x0, y0 = dx - t, up - t
        xs = (x0 + s_top, x0 + s_bottom, x0 + s_top + quad_w, x0 + s_bottom + quad_w)
        for j in range(math.floor(y0 * n) - 1, math.ceil((y0 + quad_h) * n) + 1):
            b = (Fraction(2 * j + 1, 2 * n) - y0) / quad_h
            if not 0 <= b < 1:
                continue
            texel_row = bitmap[math.floor(inset + b * (rows - 2 * inset))]
            shift = s_top + b * (s_bottom - s_top)
            for i in range(math.floor(min(xs) * n) - 1, math.ceil(max(xs) * n) + 1):
                a = (Fraction(2 * i + 1, 2 * n) - x0 - shift) / quad_w
                if 0 <= a < 1 and texel_row[math.floor(inset + a * (cols - 2 * inset))]:
                    covered.add((i, j - 7 * n))
    return covered


def outline_coverage(contours, gui_scale=2):
    """The output pixels whose centres font-unit contours cover by the nonzero rule, at gui_scale output
    pixels per 128 units, on client_coverage's grid. A centre lying on a slanted or vertical edge is
    covered, as FreeType's rasterizer has it. Exact arithmetic throughout."""
    pitch = Fraction(128, gui_scale)
    edges = []
    for contour in contours:
        for k, (x0, y0) in enumerate(contour):
            x1, y1 = contour[(k + 1) % len(contour)]
            if y0 != y1:
                edges.append((Fraction(x0), Fraction(y0), Fraction(x1), Fraction(y1)))
    if not edges:
        return set()
    xs = [x for edge in edges for x in (edge[0], edge[2])]
    ys = [y for edge in edges for y in (edge[1], edge[3])]
    covered = set()
    for j in range(math.floor(-max(ys) / pitch) - 1, math.ceil(-min(ys) / pitch) + 1):
        cy = -(j + Fraction(1, 2)) * pitch
        crossings = [(x0 + (cy - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1)
                     for x0, y0, x1, y1 in edges if min(y0, y1) <= cy < max(y0, y1)]
        for i in range(math.floor(min(xs) / pitch) - 1, math.ceil(max(xs) / pitch) + 1):
            cx = (i + Fraction(1, 2)) * pitch
            left_of = sum(d for x, d in crossings if x < cx)
            through = sum(d for x, d in crossings if x <= cx)
            if left_of or through:
                covered.add((i, j))
    return covered


def _scanline_crossings(contours, cy):
    """Where the contours' edges cross the horizontal line y = cy, as (x, +1 upward / -1 downward)."""
    crossings = []
    for contour in contours:
        for k, (x0, y0) in enumerate(contour):
            x1, y1 = contour[(k + 1) % len(contour)]
            x0, y0, x1, y1 = Fraction(x0), Fraction(y0), Fraction(x1), Fraction(y1)
            if y0 != y1 and min(y0, y1) <= cy < max(y0, y1):
                crossings.append((x0 + (cy - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1))
    return crossings


def fragile_centres(contours, gui_scale, margin):
    """The output pixel centres on outline_coverage's grid whose coverage changes if an edge crossing
    their scanline within `margin` font units of them is moved to their other side - the centres a
    rasterizer that places crossings only to that precision may get wrong. Exact arithmetic."""
    pitch = Fraction(128, gui_scale)
    ys = [Fraction(y) for contour in contours for _, y in contour]
    xs = [Fraction(x) for contour in contours for x, _ in contour]
    fragile = set()
    for j in range(math.floor(-max(ys) / pitch) - 1, math.ceil(-min(ys) / pitch) + 1):
        crossings = _scanline_crossings(contours, -(j + Fraction(1, 2)) * pitch)
        for i in range(math.floor(min(xs) / pitch) - 1, math.ceil(max(xs) / pitch) + 1):
            cx = (i + Fraction(1, 2)) * pitch
            base = sum(d for x, d in crossings if x < cx - margin)
            near = [d for x, d in crossings if cx - margin <= x <= cx + margin]
            windings = {base + sum(d for k, d in enumerate(near) if mask >> k & 1) != 0
                        for mask in range(1 << len(near))}
            if len(windings) > 1:
                fragile.add((i, j))
    return fragile


def scanline_gaps(contours, y):
    """The widths of the stretches the contours leave unfilled, by the nonzero rule, between filled ones
    along the line at height y."""
    steps = defaultdict(int)  # edges meeting at one x, as abutting contours do, change the winding at once
    for x, d in _scanline_crossings(contours, Fraction(y)):
        steps[x] += d
    gaps, winding, gap_start = [], 0, None
    for x, d in sorted(steps.items()):
        was_filled = winding != 0
        winding += d
        if was_filled and winding == 0:
            gap_start = x
        elif not was_filled and winding != 0 and gap_start is not None:
            gaps.append(x - gap_start)
    return gaps


def column_gaps(contours, x):
    """scanline_gaps down the vertical line at x."""
    return scanline_gaps([[(py, px) for px, py in contour] for contour in contours], x)


def charstring_width(tile, italic=False):
    """The advance written into a scaled tile's CFF charstring, read back as a CFF consumer reads it."""
    from fontTools.misc.psCharStrings import T2WidthExtractor
    from minecraft_fontgen.glyph.glyph import Glyph

    glyph = Glyph(tile, use_cff=True)
    glyph.scale(italic=italic)
    glyph.draw()
    extractor = T2WidthExtractor([], [], 0, 0)
    extractor.execute(glyph.build())
    return extractor.width
