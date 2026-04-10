from math import atan

# =============================
# === RUNTIME CONFIGURATION ===
# =============================

SILENT_LOG = False # True to disable logging
OUTPUT_DIR = "output"
OPENTYPE = True # False for TrueType

# ==================================
# === FONT DETAILS / DO NOT EDIT ===
# ==================================

VERSION = "1.1.0"
MANUFACTURER = "SkyBlock Simplified"
DESIGNER = "CraftedFury"
COPYRIGHT = "Copyright © Mojang AB"
TRADEMARK = "The glyphs used in this font file are trademarked by Mojang."
VENDOR_URL = "https://github.com/minecraft-library/font-generator"
DESIGNER_URL = "https://sbs.dev/"
LICENSE_TEXT = "The glyphs used in this font file are licensed by Mojang."
DESCRIPTION = "Build your own font files containing the Minecraft font glyphs."
SAMPLE_TEXT = "The quick brown fox jumps over the lazy dog. 0123456789"

# ===============================
# === CONSTANTS / DO NOT EDIT ===
# ===============================

# File Output
OUTPUT_FONT_NAME = "Minecraft"

# File Input
WORK_DIR = "work"
MINECRAFT_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MINECRAFT_RESOURCE_URL = "https://resources.download.minecraft.net"
MINECRAFT_JAR_DIR = WORK_DIR + "/assets/minecraft"
MINECRAFT_BIN_FILE = f"{MINECRAFT_JAR_DIR}/font/glyph_sizes.bin"
MINECRAFT_JSON_FILE = f"{MINECRAFT_JAR_DIR}/font/include/default.json"
UNIFONT_PATH = "minecraft/font/include/unifont.json"
TEXTURE_PATH = f"{MINECRAFT_JAR_DIR}/textures/font"
VALIDATE_SCRIPT = "validate_font.py"

# Font Styles (toggle "enabled" to include/exclude a style)
FONT_STYLES = [
    {
        "name": "Regular",
        "enabled": True,
        "bold": False,
        "italic": False,
        "pixel_style": "Regular",
        "debug": {
            "svg": False,
            "bmp": False,
            "unifont": False
        },
    },
    {
        "name": "Bold",
        "enabled": True,
        "bold": True,
        "italic": False,
        "pixel_style": "Bold",
        "debug": {
            "svg": False,
            "bmp": False,
            "unifont": False
        },
    },
    {
        "name": "Italic",
        "enabled": True,
        "bold": False,
        "italic": True,
        "pixel_style": "Regular",
        "debug": {
            "svg": False,
            "bmp": False,
            "unifont": False
        },
    },
    {
        "name": "BoldItalic",
        "enabled": True,
        "bold": True,
        "italic": True,
        "pixel_style": "Bold",
        "debug": {
            "svg": False,
            "bmp": False,
            "unifont": False
        },
    },
    {
        "name": "Galactic",
        "enabled": True,
        "bold": False,
        "italic": False,
        "pixel_style": "Galactic",
        "json_file": f"{MINECRAFT_JAR_DIR}/font/alt.json",
        "map_lowercase": True,  # Duplicate uppercase glyphs onto lowercase codepoints
        "debug": {
            "svg": False,
            "bmp": False,
            "unifont": False
        },
    },
    {
        "name": "Illageralt",
        "enabled": True,
        "bold": False,
        "italic": False,
        "pixel_style": "Illageralt",
        "json_file": f"{MINECRAFT_JAR_DIR}/font/illageralt.json",
        "map_lowercase": False,
        "debug": {
            "svg": False,
            "bmp": False,
            "unifont": False
        },
    },
]

# FontTools Epoch
MAC_EPOCH = 2082844800 # Seconds since 12:00 midnight, January 1, 1904 UTC

# Glyph
COLUMNS_PER_ROW = 16
DEFAULT_GLYPH_SIZE = 8
UNITS_PER_EM = 1024
ASCENT = (DEFAULT_GLYPH_SIZE - 1) * (UNITS_PER_EM // DEFAULT_GLYPH_SIZE)  # 7 * 128 = 896
DESCENT = -(UNITS_PER_EM // DEFAULT_GLYPH_SIZE)  # -128
BOUNDING_BOX = [0, -256, 1280, 1280]
MAX_ADVANCE_WIDTH = BOUNDING_BOX[2] + BOUNDING_BOX[1]
NOTDEF = ".notdef"
NOTDEF_GLYPH = [
    [20, 0, 437, 675], # Inner rectangle
    [68, 48, 388, 627] # Outer rectangle
]

# Italic Glyph
ITALIC_SHEAR_VERTICAL = 5
ITALIC_SHEAR_FACTOR = 1 / ITALIC_SHEAR_VERTICAL
ITALIC_SHEAR_ANGLE = atan(ITALIC_SHEAR_FACTOR)

# Unifont Codepoint Ranges
# Controls which Unicode blocks are included from GNU Unifont hex files.
# Each entry is (start, end, enabled). Disabled blocks are excluded from the
# font to stay within CFF's 65,535 glyph limit (unifont has ~113k total).
# Minecraft's bitmap provider glyphs are always included regardless of this list.
# Toggling a block on/off requires regenerating the font.
UNIFONT_RANGES = [
    # === BMP: Latin, Greek, Cyrillic ===
    (0x0000, 0x007F, True),    # Basic Latin
    (0x0080, 0x00FF, True),    # Latin-1 Supplement
    (0x0100, 0x017F, True),    # Latin Extended-A
    (0x0180, 0x024F, True),    # Latin Extended-B
    (0x0250, 0x02AF, True),    # IPA Extensions
    (0x02B0, 0x02FF, True),    # Spacing Modifier Letters
    (0x0300, 0x036F, True),    # Combining Diacritical Marks
    (0x0370, 0x03FF, True),    # Greek and Coptic
    (0x0400, 0x04FF, True),    # Cyrillic
    (0x0500, 0x052F, True),    # Cyrillic Supplement

    # === BMP: Armenian, Hebrew, Arabic ===
    (0x0530, 0x058F, True),    # Armenian
    (0x0590, 0x05FF, True),    # Hebrew
    (0x0600, 0x06FF, True),    # Arabic
    (0x0700, 0x074F, True),    # Syriac
    (0x0750, 0x077F, True),    # Arabic Supplement
    (0x0780, 0x07BF, True),    # Thaana
    (0x07C0, 0x07FF, True),    # NKo
    (0x0800, 0x083F, False),   # Samaritan
    (0x0840, 0x085F, False),   # Mandaic
    (0x0860, 0x086F, False),   # Syriac Supplement
    (0x0870, 0x089F, False),   # Arabic Extended-B
    (0x08A0, 0x08FF, False),   # Arabic Extended-A

    # === BMP: Indic Scripts ===
    (0x0900, 0x097F, True),    # Devanagari
    (0x0980, 0x09FF, False),   # Bengali
    (0x0A00, 0x0A7F, False),   # Gurmukhi
    (0x0A80, 0x0AFF, False),   # Gujarati
    (0x0B00, 0x0B7F, False),   # Oriya
    (0x0B80, 0x0BFF, False),   # Tamil
    (0x0C00, 0x0C7F, False),   # Telugu
    (0x0C80, 0x0CFF, False),   # Kannada
    (0x0D00, 0x0D7F, True),    # Malayalam
    (0x0D80, 0x0DFF, True),    # Sinhala

    # === BMP: Southeast Asian ===
    (0x0E00, 0x0E7F, True),    # Thai
    (0x0E80, 0x0EFF, False),   # Lao
    (0x0F00, 0x0FFF, True),    # Tibetan
    (0x1000, 0x109F, False),   # Myanmar

    # === BMP: Georgian, Hangul, Ethiopic ===
    (0x10A0, 0x10FF, True),    # Georgian
    (0x1100, 0x11FF, True),    # Hangul Jamo
    (0x1200, 0x137F, True),    # Ethiopic
    (0x1380, 0x139F, False),   # Ethiopic Supplement
    (0x13A0, 0x13FF, False),   # Cherokee

    # === BMP: Canadian Aboriginal, Ogham, Runic ===
    (0x1400, 0x167F, False),   # Unified Canadian Aboriginal Syllabics
    (0x1680, 0x169F, False),   # Ogham
    (0x16A0, 0x16FF, False),   # Runic

    # === BMP: Philippine, Khmer, Mongolian ===
    (0x1700, 0x171F, False),   # Tagalog
    (0x1720, 0x173F, False),   # Hanunoo
    (0x1740, 0x175F, False),   # Buhid
    (0x1760, 0x177F, False),   # Tagbanwa
    (0x1780, 0x17FF, False),   # Khmer
    (0x1800, 0x18AF, True),    # Mongolian
    (0x18B0, 0x18FF, False),   # Unified Canadian Aboriginal Syllabics Extended

    # === BMP: Tai, Buginese, Balinese ===
    (0x1900, 0x194F, False),   # Limbu
    (0x1950, 0x197F, False),   # Tai Le
    (0x1980, 0x19DF, False),   # New Tai Lue
    (0x19E0, 0x19FF, False),   # Khmer Symbols
    (0x1A00, 0x1A1F, False),   # Buginese
    (0x1A20, 0x1AAF, False),   # Tai Tham
    (0x1AB0, 0x1AFF, False),   # Combining Diacritical Marks Extended
    (0x1B00, 0x1B7F, False),   # Balinese
    (0x1B80, 0x1BBF, False),   # Sundanese
    (0x1BC0, 0x1BFF, False),   # Batak
    (0x1C00, 0x1C4F, False),   # Lepcha
    (0x1C50, 0x1C7F, False),   # Ol Chiki
    (0x1C80, 0x1C8F, False),   # Cyrillic Extended-C
    (0x1C90, 0x1CBF, False),   # Georgian Extended
    (0x1CC0, 0x1CCF, False),   # Sundanese Supplement
    (0x1CD0, 0x1CFF, False),   # Vedic Extensions

    # === BMP: Phonetic Extensions, Latin/Greek Extended ===
    (0x1D00, 0x1D7F, True),    # Phonetic Extensions
    (0x1D80, 0x1DBF, True),    # Phonetic Extensions Supplement
    (0x1DC0, 0x1DFF, True),    # Combining Diacritical Marks Supplement
    (0x1E00, 0x1EFF, True),    # Latin Extended Additional
    (0x1F00, 0x1FFF, True),    # Greek Extended

    # === BMP: Punctuation, Symbols, Arrows ===
    (0x2000, 0x206F, True),    # General Punctuation
    (0x2070, 0x209F, True),    # Superscripts and Subscripts
    (0x20A0, 0x20CF, True),    # Currency Symbols
    (0x20D0, 0x20FF, True),    # Combining Diacritical Marks for Symbols
    (0x2100, 0x214F, True),    # Letterlike Symbols
    (0x2150, 0x218F, True),    # Number Forms
    (0x2190, 0x21FF, True),    # Arrows
    (0x2200, 0x22FF, True),    # Mathematical Operators
    (0x2300, 0x23FF, True),    # Miscellaneous Technical
    (0x2400, 0x243F, True),    # Control Pictures
    (0x2440, 0x245F, True),    # Optical Character Recognition
    (0x2460, 0x24FF, True),    # Enclosed Alphanumerics
    (0x2500, 0x257F, True),    # Box Drawing
    (0x2580, 0x259F, True),    # Block Elements
    (0x25A0, 0x25FF, True),    # Geometric Shapes
    (0x2600, 0x26FF, True),    # Miscellaneous Symbols
    (0x2700, 0x27BF, True),    # Dingbats
    (0x27C0, 0x27EF, True),    # Miscellaneous Mathematical Symbols-A
    (0x27F0, 0x27FF, True),    # Supplemental Arrows-A
    (0x2800, 0x28FF, True),    # Braille Patterns
    (0x2900, 0x297F, True),    # Supplemental Arrows-B
    (0x2980, 0x29FF, True),    # Miscellaneous Mathematical Symbols-B
    (0x2A00, 0x2AFF, True),    # Supplemental Mathematical Operators
    (0x2B00, 0x2BFF, True),    # Miscellaneous Symbols and Arrows

    # === BMP: Glagolitic, Coptic, Georgian Supplement ===
    (0x2C00, 0x2C5F, True),    # Glagolitic
    (0x2C60, 0x2C7F, True),    # Latin Extended-C
    (0x2C80, 0x2CFF, True),    # Coptic
    (0x2D00, 0x2D2F, False),   # Georgian Supplement
    (0x2D30, 0x2D7F, False),   # Tifinagh
    (0x2D80, 0x2DDF, False),   # Ethiopic Extended
    (0x2DE0, 0x2DFF, False),   # Cyrillic Extended-A
    (0x2E00, 0x2E7F, True),    # Supplemental Punctuation

    # === BMP: CJK ===
    (0x2E80, 0x2EFF, False),   # CJK Radicals Supplement
    (0x2F00, 0x2FDF, False),   # Kangxi Radicals
    (0x2FF0, 0x2FFF, False),   # Ideographic Description Characters
    (0x3000, 0x303F, False),   # CJK Symbols and Punctuation
    (0x3040, 0x309F, False),   # Hiragana
    (0x30A0, 0x30FF, False),   # Katakana
    (0x3100, 0x312F, False),   # Bopomofo
    (0x3130, 0x318F, False),   # Hangul Compatibility Jamo
    (0x3190, 0x319F, False),   # Kanbun
    (0x31A0, 0x31BF, False),   # Bopomofo Extended
    (0x31C0, 0x31EF, False),   # CJK Strokes
    (0x31F0, 0x31FF, False),   # Katakana Phonetic Extensions
    (0x3200, 0x32FF, False),   # Enclosed CJK Letters and Months
    (0x3300, 0x33FF, False),   # CJK Compatibility
    (0x3400, 0x4DBF, False),   # CJK Unified Ideographs Extension A (~6,592 glyphs)
    (0x4DC0, 0x4DFF, False),   # Yijing Hexagram Symbols
    (0x4E00, 0x9FFF, False),   # CJK Unified Ideographs (~20,992 glyphs)

    # === BMP: Yi, Lisu, Vai ===
    (0xA000, 0xA48F, True),    # Yi Syllables
    (0xA490, 0xA4CF, True),    # Yi Radicals
    (0xA4D0, 0xA4FF, False),   # Lisu
    (0xA500, 0xA63F, True),    # Vai
    (0xA640, 0xA69F, False),   # Cyrillic Extended-B
    (0xA6A0, 0xA6FF, False),   # Bamum
    (0xA700, 0xA71F, False),   # Modifier Tone Letters
    (0xA720, 0xA7FF, True),    # Latin Extended-D
    (0xA800, 0xA82F, False),   # Syloti Nagri
    (0xA830, 0xA83F, False),   # Common Indic Number Forms
    (0xA840, 0xA87F, False),   # Phags-pa
    (0xA880, 0xA8DF, False),   # Saurashtra
    (0xA8E0, 0xA8FF, False),   # Devanagari Extended
    (0xA900, 0xA92F, False),   # Kayah Li
    (0xA930, 0xA95F, False),   # Rejang
    (0xA960, 0xA97F, False),   # Hangul Jamo Extended-A
    (0xA980, 0xA9DF, False),   # Javanese
    (0xA9E0, 0xA9FF, False),   # Myanmar Extended-B
    (0xAA00, 0xAA5F, True),    # Cham
    (0xAA60, 0xAA7F, False),   # Myanmar Extended-A
    (0xAA80, 0xAADF, False),   # Tai Viet
    (0xAAE0, 0xAAFF, False),   # Meetei Mayek Extensions
    (0xAB00, 0xAB2F, False),   # Ethiopic Extended-A
    (0xAB30, 0xAB6F, True),    # Latin Extended-E
    (0xAB70, 0xABBF, False),   # Cherokee Supplement
    (0xABC0, 0xABFF, False),   # Meetei Mayek

    # === BMP: Hangul Syllables (large block) ===
    (0xAC00, 0xD7AF, False),   # Hangul Syllables (~11,184 glyphs)
    (0xD7B0, 0xD7FF, False),   # Hangul Jamo Extended-B

    # === BMP: Presentation Forms, Halfwidth/Fullwidth ===
    (0xF900, 0xFAFF, False),   # CJK Compatibility Ideographs
    (0xFB00, 0xFB4F, True),    # Alphabetic Presentation Forms
    (0xFB50, 0xFDFF, False),   # Arabic Presentation Forms-A
    (0xFE00, 0xFE0F, False),   # Variation Selectors
    (0xFE10, 0xFE1F, False),   # Vertical Forms
    (0xFE20, 0xFE2F, True),    # Combining Half Marks
    (0xFE30, 0xFE4F, False),   # CJK Compatibility Forms
    (0xFE50, 0xFE6F, True),    # Small Form Variants
    (0xFE70, 0xFEFF, False),   # Arabic Presentation Forms-B
    (0xFF00, 0xFFEF, True),    # Halfwidth and Fullwidth Forms
    (0xFFF0, 0xFFFF, True),    # Specials

    # === SMP: Historic Scripts ===
    (0x10000, 0x1007F, False),  # Linear B Syllabary
    (0x10080, 0x100FF, False),  # Linear B Ideograms
    (0x10100, 0x1013F, False),  # Aegean Numbers
    (0x10140, 0x1018F, False),  # Ancient Greek Numbers
    (0x10190, 0x101CF, False),  # Ancient Symbols
    (0x101D0, 0x101FF, False),  # Phaistos Disc
    (0x10280, 0x1029F, False),  # Lycian
    (0x102A0, 0x102DF, False),  # Carian
    (0x102E0, 0x102FF, False),  # Coptic Epact Numbers
    (0x10300, 0x1032F, False),  # Old Italic
    (0x10330, 0x1034F, False),  # Gothic
    (0x10350, 0x1037F, False),  # Old Permic
    (0x10380, 0x1039F, False),  # Ugaritic
    (0x103A0, 0x103DF, False),  # Old Persian
    (0x10400, 0x1044F, False),  # Deseret
    (0x10450, 0x1047F, False),  # Shavian
    (0x10480, 0x104AF, False),  # Osmanya
    (0x104B0, 0x104FF, False),  # Osage
    (0x10500, 0x1052F, False),  # Elbasan
    (0x10530, 0x1056F, False),  # Caucasian Albanian
    (0x10570, 0x105BF, False),  # Vithkuqi
    (0x10600, 0x1077F, False),  # Linear A
    (0x10780, 0x107BF, False),  # Latin Extended-F
    (0x10800, 0x1083F, False),  # Cypriot Syllabary
    (0x10840, 0x1085F, False),  # Imperial Aramaic
    (0x10860, 0x1087F, False),  # Palmyrene
    (0x10880, 0x108AF, False),  # Nabataean
    (0x108E0, 0x108FF, False),  # Hatran
    (0x10900, 0x1091F, False),  # Phoenician
    (0x10920, 0x1093F, False),  # Lydian
    (0x10980, 0x1099F, False),  # Meroitic Hieroglyphs
    (0x109A0, 0x109FF, False),  # Meroitic Cursive
    (0x10A00, 0x10A5F, False),  # Kharoshthi
    (0x10A60, 0x10A7F, False),  # Old South Arabian
    (0x10A80, 0x10A9F, False),  # Old North Arabian
    (0x10AC0, 0x10AFF, False),  # Manichaean
    (0x10B00, 0x10B3F, False),  # Avestan
    (0x10B40, 0x10B5F, False),  # Inscriptional Parthian
    (0x10B60, 0x10B7F, False),  # Inscriptional Pahlavi
    (0x10B80, 0x10BAF, False),  # Psalter Pahlavi
    (0x10C00, 0x10C4F, False),  # Old Turkic
    (0x10C80, 0x10CFF, False),  # Old Hungarian
    (0x10D00, 0x10D3F, False),  # Hanifi Rohingya
    (0x10E60, 0x10E7F, False),  # Rumi Numeral Symbols
    (0x10E80, 0x10EBF, False),  # Yezidi
    (0x10F00, 0x10F2F, False),  # Old Sogdian
    (0x10F30, 0x10F6F, False),  # Sogdian
    (0x10F70, 0x10FAF, False),  # Old Uyghur
    (0x10FB0, 0x10FDF, False),  # Chorasmian
    (0x10FE0, 0x10FFF, False),  # Elymaic

    # === SMP: Brahmic Scripts ===
    (0x11000, 0x1107F, False),  # Brahmi
    (0x11080, 0x110CF, False),  # Kaithi
    (0x110D0, 0x110FF, False),  # Sora Sompeng
    (0x11100, 0x1114F, False),  # Chakma
    (0x11150, 0x1117F, False),  # Mahajani
    (0x11180, 0x111DF, False),  # Sharada
    (0x111E0, 0x111FF, False),  # Sinhala Archaic Numbers
    (0x11200, 0x1124F, False),  # Khojki
    (0x11280, 0x112AF, False),  # Multani
    (0x112B0, 0x112FF, False),  # Khudawadi
    (0x11300, 0x1137F, False),  # Grantha
    (0x11400, 0x1147F, False),  # Newa
    (0x11480, 0x114DF, False),  # Tirhuta
    (0x11580, 0x115FF, False),  # Siddham
    (0x11600, 0x1165F, False),  # Modi
    (0x11660, 0x1167F, False),  # Mongolian Supplement
    (0x11680, 0x116CF, False),  # Takri
    (0x11700, 0x1174F, False),  # Ahom
    (0x11800, 0x1184F, False),  # Dogra
    (0x118A0, 0x118FF, False),  # Warang Citi
    (0x11900, 0x1195F, False),  # Dives Akuru
    (0x119A0, 0x119FF, False),  # Nandinagari
    (0x11A00, 0x11A4F, False),  # Zanabazar Square
    (0x11A50, 0x11AAF, False),  # Soyombo
    (0x11AB0, 0x11ABF, False),  # Unified Canadian Aboriginal Syllabics Extended-A
    (0x11AC0, 0x11AFF, False),  # Pau Cin Hau
    (0x11C00, 0x11C6F, False),  # Bhaiksuki
    (0x11C70, 0x11CBF, False),  # Marchen
    (0x11D00, 0x11D5F, False),  # Masaram Gondi
    (0x11D60, 0x11DAF, False),  # Gunjala Gondi
    (0x11EE0, 0x11EFF, False),  # Makasar
    (0x11FB0, 0x11FBF, False),  # Lisu Supplement
    (0x11FC0, 0x11FFF, False),  # Tamil Supplement

    # === SMP: Cuneiform, Hieroglyphs ===
    (0x12000, 0x123FF, False),  # Cuneiform
    (0x12400, 0x1247F, False),  # Cuneiform Numbers and Punctuation
    (0x12480, 0x1254F, False),  # Early Dynastic Cuneiform
    (0x12F90, 0x12FFF, False),  # Cypro-Minoan
    (0x13000, 0x1342F, False),  # Egyptian Hieroglyphs
    (0x13430, 0x1345F, False),  # Egyptian Hieroglyph Format Controls
    (0x14400, 0x1467F, False),  # Anatolian Hieroglyphs

    # === SMP: African, Asian, Pacific Scripts ===
    (0x16800, 0x16A3F, False),  # Bamum Supplement
    (0x16A40, 0x16A6F, False),  # Mro
    (0x16A70, 0x16ACF, False),  # Tangsa
    (0x16AD0, 0x16AFF, False),  # Bassa Vah
    (0x16B00, 0x16B8F, False),  # Pahawh Hmong
    (0x16E40, 0x16E9F, False),  # Medefaidrin
    (0x16F00, 0x16F9F, False),  # Miao

    # === SMP: CJK, Tangut, Kana ===
    (0x16FE0, 0x16FFF, False),  # Ideographic Symbols and Punctuation
    (0x17000, 0x187FF, False),  # Tangut (~6,144 glyphs)
    (0x18800, 0x18AFF, False),  # Tangut Components
    (0x18B00, 0x18CFF, False),  # Khitan Small Script
    (0x18D00, 0x18D7F, False),  # Tangut Supplement
    (0x1AFF0, 0x1AFFF, False),  # Kana Extended-B
    (0x1B000, 0x1B0FF, False),  # Kana Supplement
    (0x1B100, 0x1B12F, False),  # Kana Extended-A
    (0x1B130, 0x1B16F, False),  # Small Kana Extension
    (0x1B170, 0x1B2FF, False),  # Nushu

    # === SMP: Shorthand, Music, Math ===
    (0x1BC00, 0x1BC9F, False),  # Duployan
    (0x1BCA0, 0x1BCAF, False),  # Shorthand Format Controls
    (0x1CF00, 0x1CFCF, False),  # Znamenny Musical Notation
    (0x1D000, 0x1D0FF, False),  # Byzantine Musical Symbols
    (0x1D100, 0x1D1FF, False),  # Musical Symbols
    (0x1D200, 0x1D24F, False),  # Ancient Greek Musical Notation
    (0x1D2C0, 0x1D2DF, False),  # Kaktovik Numerals
    (0x1D2E0, 0x1D2FF, False),  # Mayan Numerals
    (0x1D300, 0x1D35F, False),  # Tai Xuan Jing Symbols
    (0x1D360, 0x1D37F, False),  # Counting Rod Numerals
    (0x1D400, 0x1D7FF, False),  # Mathematical Alphanumeric Symbols
    (0x1D800, 0x1DAAF, False),  # Sutton SignWriting

    # === SMP: Extended Latin, Cyrillic, Scripts ===
    (0x1DF00, 0x1DFFF, False),  # Latin Extended-G
    (0x1E000, 0x1E02F, False),  # Glagolitic Supplement
    (0x1E030, 0x1E08F, False),  # Cyrillic Extended-D
    (0x1E100, 0x1E14F, False),  # Nyiakeng Puachue Hmong
    (0x1E290, 0x1E2BF, False),  # Toto
    (0x1E2C0, 0x1E2FF, False),  # Wancho
    (0x1E4D0, 0x1E4FF, False),  # Nag Mundari
    (0x1E7E0, 0x1E7FF, False),  # Ethiopic Extended-B
    (0x1E800, 0x1E8DF, False),  # Mende Kikakui
    (0x1E900, 0x1E95F, False),  # Adlam
    (0x1EC70, 0x1ECBF, False),  # Indic Siyaq Numbers
    (0x1ED00, 0x1ED4F, False),  # Ottoman Siyaq Numbers
    (0x1EE00, 0x1EEFF, False),  # Arabic Mathematical Alphabetic Symbols

    # === SMP: Symbols, Emoji, Pictographs ===
    (0x1F000, 0x1F02F, False),  # Mahjong Tiles
    (0x1F030, 0x1F09F, False),  # Domino Tiles
    (0x1F0A0, 0x1F0FF, False),  # Playing Cards
    (0x1F100, 0x1F1FF, False),  # Enclosed Alphanumeric Supplement
    (0x1F200, 0x1F2FF, False),  # Enclosed Ideographic Supplement
    (0x1F300, 0x1F5FF, False),  # Miscellaneous Symbols and Pictographs
    (0x1F600, 0x1F64F, False),  # Emoticons
    (0x1F650, 0x1F67F, False),  # Ornamental Dingbats
    (0x1F680, 0x1F6FF, False),  # Transport and Map Symbols
    (0x1F700, 0x1F77F, False),  # Alchemical Symbols
    (0x1F780, 0x1F7FF, False),  # Geometric Shapes Extended
    (0x1F800, 0x1F8FF, False),  # Supplemental Arrows-C
    (0x1F900, 0x1F9FF, True),   # Supplemental Symbols and Pictographs
    (0x1FA00, 0x1FA6F, False),  # Chess Symbols
    (0x1FA70, 0x1FAFF, False),  # Symbols and Pictographs Extended-A
    (0x1FB00, 0x1FBFF, False),  # Symbols for Legacy Computing
]
