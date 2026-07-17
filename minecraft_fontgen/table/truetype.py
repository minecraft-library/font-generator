import numpy as np

from fontTools.ttLib import newTable
from fontTools.ttLib.tables.ttProgram import Program

def create_tt_font_tables(font):
    """Creates TrueType outline tables (glyf, loca) with FontForge compatibility stubs."""
    # sfntVersion must be the 4-char Tag string, not the int 0x00010000. fontTools
    # 4.63 save() validates the string tags (sfnt.py) and raises TTLibError('bad
    # sfntVersion') on the int form, which silently broke the TrueType path.
    font.sfntVersion = "\x00\x01\x00\x00"
    font["glyf"] = newTable("glyf")
    font["glyf"].glyphs = {}

    font["loca"] = newTable("loca") # Automatically populated

    # FontForge Compatibility
    font["prep"] = newTable("prep") # TT instructions pre-program
    font["prep"].program = Program() # Dummy

    font["fpgm"] = newTable("fpgm") # Font program
    font["fpgm"].program = Program() # Dummy

    font["cvt "] = newTable("cvt ") # Control values
    font["cvt "].values = np.zeros(0, dtype=np.int16) # Dummy
