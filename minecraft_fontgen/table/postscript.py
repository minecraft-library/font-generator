from math import degrees

from fontTools.ttLib import newTable

from minecraft_fontgen.config import ITALIC_SHEAR_ANGLE

def create_font_pscript_table(font, use_cff: bool = True, italic: bool = False):
    """Creates the 'post' table with PostScript rendering hints and underline metrics. An italic
    style states the angle its glyphs are slanted at, in degrees counter-clockwise from vertical."""
    post = font["post"] = newTable("post")
    post.formatType = 3.0
    post.isFixedPitch = 0
    post.italicAngle = -degrees(ITALIC_SHEAR_ANGLE) if italic else 0.0
    post.minMemType1 = 0
    post.minMemType42 = 0
    post.maxMemType1 = 0
    post.maxMemType42 = 0
    post.underlinePosition = -75
    post.underlineThickness = 50
    post.extraNames = []
    post.mapping = {}
