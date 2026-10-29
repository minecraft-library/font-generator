from fractions import Fraction

from fontTools.ttLib import newTable

from minecraft_fontgen.config import ASCENT, DESCENT, MAX_ADVANCE_WIDTH, BOUNDING_BOX, ITALIC_SHEAR_FACTOR, ITALIC_SHEAR_PIVOT

def create_font_hheader_table(font, use_cff: bool = True, italic: bool = False):
    """Creates the 'hhea' table with horizontal layout metrics (ascent, descent, line gap). An
    italic style's caret leans as its glyphs do, offset by the slant's shift on the baseline."""
    slope = Fraction(ITALIC_SHEAR_FACTOR).limit_denominator(1000)
    hhea = font["hhea"] = newTable("hhea")
    hhea.advanceWidthMax = MAX_ADVANCE_WIDTH # Maximum advance width among all glyphs
    #hhea.ascender = ASCENT
    hhea.ascent = ASCENT # Used for line height and vertical alignment
    hhea.caretOffset = round(-ITALIC_SHEAR_PIVOT * ITALIC_SHEAR_FACTOR) if italic else 0 # Shift of a slanted caret: the slant's shift on the baseline
    hhea.caretSlopeRise = slope.denominator if italic else 1 # Defines the slope of the caret for italic text
    hhea.caretSlopeRun = slope.numerator if italic else 0 # Defines the slope of the caret for italic text
    #hhea.descender = DESCENT
    hhea.descent = DESCENT # Depth below baseline (negative value)
    hhea.lineGap = 0 # Extra space between lines
    hhea.metricDataFormat = 0 # Reserved (should be 0)
    hhea.minLeftSideBearing = 0 # Smallest left sidebearing of any glyph
    hhea.minRightSideBearing = BOUNDING_BOX[1] # Smallest right sidebearing of any glyph
    hhea.reserved0 = 0
    hhea.reserved1 = 0
    hhea.reserved2 = 0
    hhea.reserved3 = 0
    hhea.tableVersion = 0x00010000
    hhea.xMaxExtent = BOUNDING_BOX[2] # Maximum horizontal extent (left sidebearing + glyph width)
