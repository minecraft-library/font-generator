from collections import OrderedDict
from math import ceil, floor

from minecraft_fontgen.glyph.glyph import Glyph
from minecraft_fontgen.config import NOTDEF, DEFAULT_GLYPH_SIZE, UNITS_PER_EM

class GlyphStorage:
    """Accumulates drawn glyphs, manages cmap entries, and writes final font data."""

    def __init__(self, font, use_cff: bool = True):
        """Initializes storage bound to a TTFont, extracting CFF or glyf table references."""
        self.font = font
        self.tables = font["cmap"].tables
        self.use_cff = use_cff
        self.glyphs = OrderedDict()
        self.cpr = [0xFFFFFF, 0]
        self.hmtx = {}
        self.y_min = 0
        self.y_max = 0

        if self.use_cff:
            cff = font["CFF "]
            self.top_dict = cff.cff.topDictIndex[0]
            self.charstrings = self.top_dict.CharStrings
        else:
            self.glyf = font["glyf"]

    def create_glyph(self, tile):
        """Creates a new Glyph instance from tile data using this storage's font format."""
        return Glyph(tile, self.use_cff)

    def add(self, glyph: Glyph):
        """Adds a drawn glyph to storage with its advance width, LSB, and cmap mappings."""
        name = glyph.name
        if name in ("space", "uni0020"):
            advance_width = UNITS_PER_EM // 2
        elif glyph.advance_units is not None:
            advance_width = glyph.advance_units
        else:
            advance_width = int(round((glyph.width + 1) * glyph.units_per_pixel))
        lsb = 0

        # Adjust metrics from actual glyph extents (italic shear may widen glyphs)
        all_contours = list(glyph.outer_scaled) + list(glyph.holes_scaled)
        if all_contours:
            all_points = [pt for contour in all_contours for pt in contour]
            x_max = max(x for x, y in all_points)
            y_max = max(y for x, y in all_points)
            y_min = min(y for x, y in all_points)

            if x_max > advance_width:
                advance_width = ceil(x_max)

            self.y_max = max(self.y_max, y_max)
            self.y_min = min(self.y_min, y_min)

        self.hmtx[name] = (advance_width, lsb)

        # Draw font glyph
        font_glyph = glyph.build()
        if self.use_cff:
            font_glyph.width = advance_width
            if font_glyph.program and isinstance(font_glyph.program[0], (int, float)):
                font_glyph.program[0] = advance_width
            font_glyph.private = self.top_dict.Private
        self.glyphs[name] = font_glyph

        # Update min/max codepoint
        if glyph.codepoint != 0x0000:
            self.cpr[0] = min(self.cpr[0], glyph.codepoint)
            self.cpr[1] = max(self.cpr[1], glyph.codepoint)

        # Add to glyph mapping
        for table in self.tables:
            if table.format == 4 and glyph.codepoint <= 0xFFFF: # BMP (U+0000 - U+FFFF)
                table.cmap[glyph.codepoint] = name
            elif table.format == 12: # SMP (U+10000 - U+1FFFF)
                table.cmap[glyph.codepoint] = name

    def add_notdef(self):
        """Creates and adds the .notdef placeholder glyph."""
        self.add(Glyph({
            "unicode": None,
            "codepoint": 0x0000,
            "size": (DEFAULT_GLYPH_SIZE, DEFAULT_GLYPH_SIZE),
            "location": (0, 0),
            "output": None
        }, self.use_cff))

    def finalize(self):
        """Finalizes the font by setting glyph order, charstrings/glyf entries, and metrics."""
        # Sort glyphs
        self.glyphs = OrderedDict([(NOTDEF, self.glyphs[NOTDEF])] + list(self.glyphs.items()))

        # Set glyph order
        self.font.setGlyphOrder(list(self.glyphs.keys()))

        # Set glyph mappings
        if self.use_cff:
            self.top_dict.charset = list(self.glyphs.keys())

            for name, glyph in self.glyphs.items():
                self.charstrings[name] = glyph
        else:
            self.glyf.glyphOrder = self.font.getGlyphOrder()

            for name, glyph in self.glyphs.items():
                self.glyf.glyphs[name] = glyph

        # Set glyph metrics
        total_glyphs = len(self.glyphs)
        self.font["hmtx"].metrics = self.hmtx
        self.font["hhea"].numberOfHMetrics = total_glyphs # Number of advanceWidth + leftSideBearing pairs in the hmtx table
        self.font["maxp"].numGlyphs = total_glyphs # Total number of glyphs in the font
        self.font["OS/2"].usFirstCharIndex = self.cpr[0] # First Unicode codepoint in the font
        self.font["OS/2"].usLastCharIndex = self.cpr[1] # Last Unicode codepoint in the font

        advances = [aw for (aw, _lsb) in self.hmtx.values() if aw is not None]
        self.font["OS/2"].xAvgCharWidth = int(round(sum(advances) / len(advances))) # Average character width (mean of the advanced widths)

        # Update head table bounding box to encompass all glyph extents
        y_max = ceil(self.y_max)
        y_min = floor(self.y_min)
        if y_max > self.font["head"].yMax:
            self.font["head"].yMax = y_max
        if y_min < self.font["head"].yMin:
            self.font["head"].yMin = y_min

        # Update Windows clipping metrics to prevent clipping of accented glyphs
        if y_max > self.font["OS/2"].usWinAscent:
            self.font["OS/2"].usWinAscent = y_max
        if abs(y_min) > self.font["OS/2"].usWinDescent:
            self.font["OS/2"].usWinDescent = abs(y_min)

    def save(self, output_file):
        """Saves the assembled font to an output file."""
        self.font.save(output_file)
