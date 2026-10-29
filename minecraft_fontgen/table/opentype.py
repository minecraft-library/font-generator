from math import degrees

from fontTools.ttLib import newTable
from fontTools.cffLib import (
    CFFFontSet, TopDict, TopDictIndex, Index,
    PrivateDict, CharStrings
)

from minecraft_fontgen.config import OUTPUT_FONT_NAME, BOUNDING_BOX, ITALIC_SHEAR_ANGLE, UNITS_PER_EM
from minecraft_fontgen.functions import get_font_type


def create_ot_font_tables(font, bold = False, italic = False):
    """Creates CFF (OpenType) outline tables with font set, top dict, and charstring storage."""
    font.sfntVersion = "OTTO"
    cff = font["CFF "] = newTable("CFF ")
    cff_font_set = CFFFontSet()
    top_dict = TopDict(None)
    top_dict_index = TopDictIndex()
    top_dict_index.append(top_dict)
    cff_font_set.topDictIndex = top_dict_index
    cff_font_set.major = 1
    cff_font_set.minor = 0
    cff_font_set.fontNames = [OUTPUT_FONT_NAME + get_font_type(bold, italic)]
    cff_font_set.GlobalSubrs = Index()

    #top_dict.FamilyName = f"{FONT_NAME} Font"
    #top_dict.Weight = "Regular"
    #top_dict.FullName = f"{FONT_NAME} Font Regular"
    #top_dict.version = f"Version {VERSION}"
    #top_dict.Notice = f"{FONT_NAME} Font Generation by {DESIGNER}"
    top_dict.FontBBox = BOUNDING_BOX
    top_dict.FontMatrix = [1 / UNITS_PER_EM, 0, 0, 1 / UNITS_PER_EM, 0, 0]
    if italic:
        top_dict.ItalicAngle = -degrees(ITALIC_SHEAR_ANGLE)  # the slant the post table states too

    # Rebuild CharStrings
    private = PrivateDict()
    charstrings = CharStrings(
        None,
        None,
        cff_font_set.GlobalSubrs,
        private,
        None,
        None
    )
    top_dict.Private = private
    top_dict.CharStrings = charstrings
    cff.cff = cff_font_set
