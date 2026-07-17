import os
import sys

from collections import defaultdict
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from minecraft_fontgen.config import UNITS_PER_EM, DEFAULT_GLYPH_SIZE, NOTDEF, NOTDEF_GLYPH, ITALIC_SHEAR_FACTOR
from minecraft_fontgen.functions import get_unicode_codepoint

class Glyph:
    """Represents a single font glyph with pixel data, scaling, and pen drawing capabilities."""

    def __init__(self, tile, use_cff: bool = True):
        """Initializes a glyph from tile data, creating a drawing pen and handling .notdef."""
        # Raster (colour) tiles carry a verbatim RGBA cell PNG that rides in an
        # sbix strike; their glyf outline stays empty and they have no traced
        # pixel/contour data. Resolve this first so every field below can branch.
        self.is_raster = tile.get("render_mode") == "raster"
        self.unicode = tile["unicode"]
        self.codepoint = self._get_codepoint() if "codepoint" not in tile else tile["codepoint"]
        self.use_cff = use_cff
        self.name = self._get_name()
        self.svg = tile["svg"] if "svg" in tile else None
        self.size = tile["size"] or (DEFAULT_GLYPH_SIZE, DEFAULT_GLYPH_SIZE)
        self.ascent = tile["ascent"] if "ascent" in tile else 0

        if self.is_raster:
            self.raster_png = tile["raster_png"]
            self.raster_size = tile["raster_size"]
            self.font_id = tile.get("font_id")
            self.display_height = tile["display_height"]
            self.content_hash = tile["content_hash"]

        # Pixels (empty for raster tiles, which carry no traced contours; the
        # .get(...) or {} guard keeps membership/index reads below KeyError-free)
        self.pixels = tile.get("pixels") or {}
        self.width = self.pixels["width"] if "width" in self.pixels else DEFAULT_GLYPH_SIZE
        self.advance = self.pixels["advance"] if "advance" in self.pixels else DEFAULT_GLYPH_SIZE
        self.lsb = self.pixels["lsb"] if "lsb" in self.pixels else 0
        self.outer = self.pixels["paths"] if "paths" in self.pixels else {}
        self.holes = self.pixels["holes"] if "holes" in self.pixels else {}

        # Pre-computed scaled coordinates (set during glyph map building)
        self.scaled = tile.get("scaled", None)
        self.units_per_pixel = tile.get("units_per_pixel", UNITS_PER_EM / self.size[1])
        self.advance_units = tile.get("advance_units")
        self.outer_scaled = []
        self.holes_scaled = []

        # Create pen
        self.pen = self._new_pen()

        # TODO: Reverse-engineer unscaled coordinates,
        #       pass the pixels and paths data for .notdef,
        #       let #scale and #draw handle this

        # Draw .notdef
        if self.codepoint == 0x0000:
            def draw_rect(rect, ccw):
                x1, y1, x2, y2 = rect
                self.pen.moveTo((x1, y1))
                if ccw:
                    self.pen.lineTo((x2, y1))
                    self.pen.lineTo((x2, y2))
                    self.pen.lineTo((x1, y2))
                else:
                    self.pen.lineTo((x1, y2))
                    self.pen.lineTo((x2, y2))
                    self.pen.lineTo((x2, y1))
                self.pen.closePath()

            # CFF: outer=CCW, hole=CW; TrueType: outer=CW, hole=CCW
            draw_rect(NOTDEF_GLYPH[0], ccw=self.use_cff)
            draw_rect(NOTDEF_GLYPH[1], ccw=not self.use_cff)

    def _get_codepoint(self):
        """Resolves the integer codepoint from the unicode character string."""
        return get_unicode_codepoint(self.unicode)

    def _get_name(self):
        """Returns the PostScript glyph name (uni0041 for BMP, u010000 for SMP)."""
        if self.codepoint == 0x0000:
            return NOTDEF
        elif self.codepoint <= 0xFFFF:
            return f"uni{self.codepoint:04X}"
        else:
            return f"u{self.codepoint:06X}"

    def _new_pen(self):
        """Creates a new fontTools drawing pen (T2CharStringPen for CFF, TTGlyphPen for TrueType)."""
        if self.is_raster:
            # Raster glyphs stay empty-outline; the advance is sourced in
            # GlyphStorage.add from the cell footprint, not from the pen.
            return TTGlyphPen(None)
        if self.use_cff:
            if self.codepoint == 0x0020:
                advance_width = UNITS_PER_EM // 2
            elif self.advance_units is not None:
                advance_width = self.advance_units
            else:
                advance_width = round((self.width + 1) * self.units_per_pixel)
            return T2CharStringPen(advance_width, None)
        else:
            return TTGlyphPen(None)

    def is_valid(self):
        """Returns True if this glyph has a valid, non-null, non-.notdef codepoint."""
        if self.codepoint is None:
            print(f" → ⚠️ Skipping invalid unicode '0x{self.codepoint:04X}'.", file=sys.stderr)
            return False
        elif self.codepoint == 0x0000:
            return False

        return True

    def write_svg_paths(self, canvas_size=8):
        """
        Outputs a visual SVG of outer and hole paths.
        Outer paths = black fill, purple stroke.
        Hole paths = white fill, blue stroke.
        """
        def path_to_d(path):
            return "M " + " L ".join(f"{x} {y}" for x, y in path) + " Z"

        svg_header = f'''<?xml version="1.0" encoding="UTF-8"?>
    <svg xmlns="http://www.w3.org/2000/svg"
         width="{canvas_size*32}" height="{canvas_size*32}" viewBox="0 0 {canvas_size} {canvas_size}"
         shape-rendering="crispEdges">
    <g stroke-width="0.05">'''

        def extract_corners(source):
            if isinstance(source, dict):
                return [p["corners"] for p in source.values() if "corners" in p]
            elif isinstance(source, list):
                return [p for p in source if isinstance(p, list) and len(p) >= 3]
            else:
                return []

        # Collect paths
        outer_paths = extract_corners(self.outer)
        hole_paths = extract_corners(self.holes)
        all_paths = outer_paths + hole_paths
        svg_paths = []

        # Draw filled paths
        for path in outer_paths:
            svg_paths.append(f'<path d="{path_to_d(path)}" fill="black" stroke="purple"/>')
        for path in hole_paths:
            svg_paths.append(f'<path d="{path_to_d(path)}" fill="white" stroke="blue"/>')

        # Track point usage across paths
        point_usage = defaultdict(int)
        for path in all_paths:
            unique_points = set(path)
            for pt in unique_points:
                point_usage[pt] += 1

        # Draw intersections
        for path in all_paths:
            for x, y in path:
                if point_usage[(x, y)] > 1:
                    svg_paths.append(f'<circle cx="{x}" cy="{y}" r="0.1" fill="red"/>')

        svg_footer = "</g></svg>"

        file_path = os.path.splitext(self.svg["file"])[0] + f"_paths.svg"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(svg_header + "\n" + "\n".join(svg_paths) + "\n" + svg_footer)

    def scale(self, italic=False):
        """Assigns pre-computed scaled coordinates, applying italic shear if requested."""
        if self.scaled is None:
            return

        outer = self.scaled.get("outer", [])
        holes = self.scaled.get("holes", [])

        if not outer and not holes:
            return

        if italic:
            def apply_shear(pt):
                sx, sy = pt
                return (sx + sy * ITALIC_SHEAR_FACTOR, sy)
            self.outer_scaled = [[apply_shear(pt) for pt in path] for path in outer]
            self.holes_scaled = [[apply_shear(pt) for pt in path] for path in holes]
        else:
            self.outer_scaled = outer
            self.holes_scaled = holes

    def draw(self):
        """Draws contours with winding based on geometric nesting depth."""
        if not self.outer_scaled and not self.holes_scaled:
            return

        all_contours = list(self.outer_scaled) + list(self.holes_scaled)

        for contour in all_contours:
            if len(contour) < 3:
                continue

            ix, iy = self._interior_point(contour)
            depth = sum(
                1 for other in all_contours
                if other is not contour and self._point_in_polygon(ix, iy, other)
            )

            # CFF: even depth = CCW, odd depth = CW
            # TT: even depth = CW, odd depth = CCW
            want_ccw = (depth % 2 == 0) == self.use_cff
            sa = self._signed_area(contour)
            is_ccw = sa > 0

            pts = list(reversed(contour)) if want_ccw != is_ccw else contour
            self.pen.moveTo(pts[0])
            for pt in pts[1:]:
                self.pen.lineTo(pt)
            self.pen.closePath()

    @staticmethod
    def _interior_point(contour):
        """Returns a point guaranteed to be inside the contour.

        Needed because the naive approach (centroid) fails for non-convex
        shapes like C or L, where the centroid can land outside the contour
        or inside a nested hole.

        Walks each edge, takes its midpoint, and offsets it a tiny amount
        perpendicular to the edge in both directions. Since edges lie on the
        boundary, one direction is always interior. Returns the first offset
        point that _point_in_polygon confirms is inside. Falls back to an
        epsilon-offset centroid for degenerate polygons.
        """
        pip = Glyph._point_in_polygon
        eps = 0.01
        for idx in range(len(contour)):
            p0 = contour[idx]
            p1 = contour[(idx + 1) % len(contour)]
            mx = (p0[0] + p1[0]) / 2
            my = (p0[1] + p1[1]) / 2
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            if dx == 0 and dy == 0:
                continue
            for sign in (1, -1):
                px = mx + sign * (-dy) * eps
                py = my + sign * dx * eps
                if pip(px, py, contour):
                    return px, py
        cx = sum(x for x, y in contour) / len(contour) + eps
        cy = sum(y for x, y in contour) / len(contour) + eps
        return cx, cy

    @staticmethod
    def _signed_area(pts):
        """Returns the signed area of a polygon via the shoelace formula.

        The sign encodes winding direction: positive = CCW, negative = CW
        in Y-up coordinates. Used by draw() to check whether a contour's
        current winding matches what FontForge expects for its nesting depth.

        https://en.wikipedia.org/wiki/Shoelace_formula
        """
        n = len(pts)
        return sum(
            pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
            for i in range(n)
        ) / 2

    @staticmethod
    def _point_in_polygon(px, py, polygon):
        """Ray casting point-in-polygon test.

        Shoots a horizontal ray rightward from (px, py) and counts edge
        crossings: odd = inside, even = outside. Used by draw() to compute
        nesting depth (how many other contours contain a given contour's
        interior point).

        https://en.wikipedia.org/wiki/Point_in_polygon#Ray_casting_algorithm
        """
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    def build(self):
        """Returns the finalized font glyph object (T2CharString for CFF, TTGlyph for TrueType)."""
        if self.use_cff:
            glyph = self.pen.getCharString()
        else:
            glyph = self.pen.glyph()

        return glyph

    def is_debug_codepoint(self):
        """Returns True if this glyph is one of a set of debug-tracked codepoints."""
        return self.codepoint in [0x0034, 0x0038, 0x0051, 0x0041, 0x00C0, 0x00CA]
