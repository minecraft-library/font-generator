from fontTools.ttLib import newTable
from minecraft_fontgen.config import UNITS_PER_EM, BOUNDING_BOX, DEFAULT_GLYPH_SIZE, MAC_EPOCH
from minecraft_fontgen.functions import resolve_source_date_epoch

def create_font_header_table(font, use_cff: bool = True):
    """Creates the 'head' table with font-wide metadata, timestamps, and bounding box."""
    now = resolve_source_date_epoch()
    head = font["head"] = newTable("head")
    head.checkSumAdjustment = 0 # Used to ensure the font has a valid file checksum (recalculated automatically)
    # head timestamps are seconds since the 1904 Mac epoch. now is already a Unix
    # timestamp, so the Unix->Mac delta is exactly the constant MAC_EPOCH; do NOT
    # subtract mktime(gmtime(0)), which reinterprets the UTC epoch as local time
    # and makes head.created timezone-dependent (nondeterministic across machines).
    head.created = now + MAC_EPOCH # Creation timestamp of the font
    head.flags = 11 # Bit flags that define font-wide behavior (e.g., baseline, left sidebearing point at x=0)
    head.fontRevision = 1.0
    head.fontDirectionHint = 2 # Used by font renderers for direction hints (usually set to 2 for modern fonts)
    head.glyphDataFormat = 0
    head.indexToLocFormat = 1 if not use_cff else 0 # 0 = short offsets (16-bit), 1 = long offsets (32-bit) in the loca table
    head.lowestRecPPEM = DEFAULT_GLYPH_SIZE # Smallest readable pixel size the font is designed for (in pixels per em)
    head.macStyle = 0 # Bit flags for font styling (e.g., bold, italic)
    head.magicNumber = 0x5F0F3CF5 # Verification signature for OpenType and TrueType
    head.modified = now + MAC_EPOCH # Last modified timestamp of the font
    head.tableVersion = 1.0
    head.unitsPerEm = UNITS_PER_EM # Defines the em square size (Higher values increase the resolution of glyph coordinates)
    head.xMin, head.yMin, head.xMax, head.yMax = BOUNDING_BOX # Bounding Box of all glyphs
