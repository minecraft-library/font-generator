# Minecraft Font Generator

Convert Minecraft's bitmap font glyphs into fully functional OpenType (`.otf`) or TrueType (`.ttf`) font files.

> [!IMPORTANT]
> This tool downloads and processes **copyrighted bitmap assets owned by [Mojang AB](https://www.minecraft.net/)** (a Microsoft subsidiary) at runtime. The font textures are extracted directly from the official Minecraft client JAR and are **never distributed** with this repository. You are responsible for ensuring your use of the generated font files complies with the [Minecraft EULA](https://www.minecraft.net/en-us/eula) and [Minecraft Usage Guidelines](https://www.minecraft.net/en-us/usage-guidelines).

## Table of Contents

- [Features](#features)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Usage](#usage)
  - [IntelliJ IDEA](#intellij-idea)
  - [Configuration](#configuration)
- [Output](#output)
- [Unicode Coverage](#unicode-coverage)
- [Docker Compose](#docker-compose)
  - [Basic One-Shot Task](#basic-one-shot-task)
  - [Running the Task](#running-the-task)
- [How It Works](#how-it-works)
  - [Glyph Processing](#glyph-processing)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Any Minecraft version** - Select any release or snapshot via the Mojang Piston API
- **OpenType (CFF) or TrueType** - Choose your preferred outline format
- **Multiple font styles** - Generate Regular, Bold, Italic, BoldItalic, plus alternate scripts (Galactic, Illageralt) on supported versions
- **GNU Unifont fallback** - Optionally include thousands of extra Unicode glyphs from [GNU Unifont](https://unifoundry.com/unifont/) for broad script coverage
- **BMP + SMP support** - Generates cmap Format 4 (Basic Multilingual Plane) and Format 12 (Supplementary Multilingual Plane) tables
- **Pixel-perfect tracing** - Flood-fill contour tracing converts bitmap pixels into clean vector outlines
- **Debug SVG output** - Optionally dump per-glyph SVG files for visual inspection
- **Non-interactive mode** - Fully scriptable with CLI arguments and environment variables for CI/CD and Docker workflows

## Getting Started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| [Python](https://www.python.org/downloads/) | **3.10+** | Required |
| pip | Latest | Included with Python |
| [Git](https://git-scm.com/) | 2.x+ | For cloning the repository |

### Installation

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/minecraft-library/font-generator.git
cd font-generator
```

<details>
<summary>Linux / macOS</summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
```

</details>

<details>
<summary>Windows</summary>

```powershell
python -m venv .venv
.venv\Scripts\activate
```

</details>

Install the package and its dependencies:

```bash
pip install -e .
```

### Usage

#### Interactive Mode

When no `--version` flag or `MCFONT_VERSION` env var is set, the tool launches
an interactive prompt where you can search and select a Minecraft version:

```bash
python -m minecraft_fontgen
```

The interactive prompt supports the following commands:

| Command | Description |
|---------|-------------|
| `<version>` | Enter a version number directly (e.g., `1.21.4`) |
| `r` or `releases` | List all available release versions |
| `s` or `snapshots` | List all available snapshot versions |
| `h`, `?`, or `help` | Show help |
| `exit` or `quit` | Exit the tool |

#### Non-Interactive Mode

For automation, CI/CD pipelines, or Docker, provide the Minecraft version
upfront to skip the interactive prompt entirely:

```bash
# Via CLI argument
python -m minecraft_fontgen --version 1.21.4

# Via environment variable
MCFONT_VERSION=1.21.4 python -m minecraft_fontgen

# Combine multiple options
python -m minecraft_fontgen --version 1.21.4 --styles regular,bold --output dist/fonts --silent
```

### IntelliJ IDEA

The repository includes a shared run configuration for
[IntelliJ IDEA](https://www.jetbrains.com/idea/) and
[PyCharm](https://www.jetbrains.com/pycharm/). After opening the project, the
**main** configuration appears automatically in the **Run/Debug** toolbar.

To run or debug:

1. Open the project in IntelliJ IDEA or PyCharm.
2. Select **main** from the run configuration dropdown in the toolbar.
3. Click **Run** (▶) or **Debug** (🪲) to start the tool.

The configuration runs `python -m minecraft_fontgen` using the project's
Python virtual environment with these environment variables pre-set:

| Variable | Value | Purpose |
|----------|-------|---------|
| `MCFONT_VALIDATE` | `1` | Runs FontForge validation after build |
| `PYTHONUNBUFFERED` | `1` | Ensures real-time console output |

To pass additional arguments (e.g. `--version 1.21.4`), open the configuration
editor (**Run > Edit Configurations**) and add them to the **Parameters** field.
You can also add or override environment variables in the **Environment
variables** section of the same dialog.

### Configuration

All options are optional. Values are resolved in this order (highest priority
first):

```
CLI argument  >  Shell environment variable  >  .env file  >  config.py defaults
```

| CLI | Env Var | Description | Default | Example |
|-----|---------|-------------|---------|---------|
| `--version` | `MCFONT_VERSION` | Minecraft version to compile (skips interactive prompt) | Interactive prompt | `1.21.4` |
| `--output` | `MCFONT_OUTPUT` | Directory for generated font files | `output` | `dist/fonts` |
| `--styles` | `MCFONT_STYLES` | Comma-separated font styles to generate | All enabled in `config.py` | `regular,bold` |
| `--type` | `MCFONT_TYPE` | Font type: `opentype`/`otf` or `truetype`/`ttf` | `opentype` | `opentype` |
| `--silent` | `MCFONT_SILENT` | Suppress all output except errors | Disabled | `true` |
| `--validate` | `MCFONT_VALIDATE` | Run FontForge validation after build (requires `fontforge`) | Disabled | `true` |

Boolean flags accept `1`, `true`, or `yes`. Valid styles: `regular`, `bold`,
`italic`, `bolditalic`, `galactic`, `illageralt`.

```bash
# Only generate Regular and Bold
python -m minecraft_fontgen --styles regular,bold

# Custom output directory
python -m minecraft_fontgen --output build/fonts

# Silent mode for scripts
python -m minecraft_fontgen --silent --version 1.21.4

# Using environment variables
MCFONT_VERSION=1.21.4 MCFONT_STYLES=regular,bold python -m minecraft_fontgen
```

> [!NOTE]
> The `--styles` flag controls which style variants are generated. BoldItalic
> is only produced when both `bold` and `italic` are present *or* `bolditalic`
> is explicitly listed.

<details>
<summary>The <code>.env</code> file</summary>

You can create a `.env` file in the project root to set defaults without
modifying your shell environment. The file is loaded automatically at startup.

```dotenv
# .env
MCFONT_VERSION=1.21.4
MCFONT_OUTPUT=output
MCFONT_STYLES=regular,bold,italic,bolditalic,galactic,illageralt
MCFONT_TYPE=opentype
MCFONT_SILENT=false
MCFONT_VALIDATE=false
```

Values from `.env` will **not** overwrite variables that already exist in your
shell environment. For example, if `MCFONT_OUTPUT=dist` is in your `.env` but
you run `python -m minecraft_fontgen --output build`, the output directory will
be `build`.

</details>

## Output

Generated font files are written to the output directory (default: `output/`):

```
output/
├── Minecraft-Regular.otf
├── Minecraft-Bold.otf
├── Minecraft-Italic.otf
├── Minecraft-BoldItalic.otf
├── Minecraft-Galactic.otf      # Minecraft 1.13+ only
└── Minecraft-Illageralt.otf    # Minecraft 1.13+ only
```

> [!NOTE]
> Galactic (Standard Galactic Alphabet) and Illageralt
> (Illager Runic Script) are only available on Minecraft versions that include their
> font provider JSON files (1.13+). On older versions these styles are
> automatically skipped.

The file extension is `.otf` for OpenType (CFF) or `.ttf` for TrueType,
controlled by `--type` / `MCFONT_TYPE` (or the `OPENTYPE` constant in
[`config.py`](minecraft_fontgen/config.py)).

## Unicode Coverage

The generated fonts include glyphs from two sources:

1. **Minecraft bitmap providers** - Glyphs from the game's PNG textures (always included)
2. **GNU Unifont fallback** - Additional glyphs from [GNU Unifont](https://unifoundry.com/unifont/) for broader script coverage (1.13+)

> [!IMPORTANT]
> Unifont contains ~113,000 glyphs across BMP and SMP, but CFF fonts are limited
> to 65,535 glyphs. The `UNIFONT_RANGES` list in
> [`config.py`](minecraft_fontgen/config.py) controls which Unicode blocks are
> included from Unifont (1.13+) or `glyph_sizes.bin` (1.12.2 and earlier). Each
> block can be toggled `True`/`False` to customize coverage.

<details>
<summary>BMP coverage - Basic Multilingual Plane (U+0000–U+FFFF)</summary>

| Range | Block | Status |
|-------|-------|--------|
| U+0000–U+007F | Basic Latin | ✅ Enabled |
| U+0080–U+00FF | Latin-1 Supplement | ✅ Enabled |
| U+0100–U+017F | Latin Extended-A | ✅ Enabled |
| U+0180–U+024F | Latin Extended-B | ✅ Enabled |
| U+0250–U+02AF | IPA Extensions | ✅ Enabled |
| U+02B0–U+02FF | Spacing Modifier Letters | ✅ Enabled |
| U+0300–U+036F | Combining Diacritical Marks | ✅ Enabled |
| U+0370–U+03FF | Greek and Coptic | ✅ Enabled |
| U+0400–U+04FF | Cyrillic | ✅ Enabled |
| U+0500–U+052F | Cyrillic Supplement | ✅ Enabled |
| U+0530–U+058F | Armenian | ✅ Enabled |
| U+0590–U+05FF | Hebrew | ✅ Enabled |
| U+0600–U+06FF | Arabic | ✅ Enabled |
| U+0700–U+074F | Syriac | ✅ Enabled |
| U+0750–U+077F | Arabic Supplement | ✅ Enabled |
| U+0780–U+07BF | Thaana | ✅ Enabled |
| U+07C0–U+07FF | NKo | ✅ Enabled |
| U+0800–U+083F | Samaritan | ❌ Disabled |
| U+0840–U+085F | Mandaic | ❌ Disabled |
| U+0860–U+086F | Syriac Supplement | ❌ Disabled |
| U+0870–U+089F | Arabic Extended-B | ❌ Disabled |
| U+08A0–U+08FF | Arabic Extended-A | ❌ Disabled |
| U+0900–U+097F | Devanagari | ✅ Enabled |
| U+0980–U+09FF | Bengali | ❌ Disabled |
| U+0A00–U+0A7F | Gurmukhi | ❌ Disabled |
| U+0A80–U+0AFF | Gujarati | ❌ Disabled |
| U+0B00–U+0B7F | Oriya | ❌ Disabled |
| U+0B80–U+0BFF | Tamil | ❌ Disabled |
| U+0C00–U+0C7F | Telugu | ❌ Disabled |
| U+0C80–U+0CFF | Kannada | ❌ Disabled |
| U+0D00–U+0D7F | Malayalam | ✅ Enabled |
| U+0D80–U+0DFF | Sinhala | ✅ Enabled |
| U+0E00–U+0E7F | Thai | ✅ Enabled |
| U+0E80–U+0EFF | Lao | ❌ Disabled |
| U+0F00–U+0FFF | Tibetan | ✅ Enabled |
| U+1000–U+109F | Myanmar | ❌ Disabled |
| U+10A0–U+10FF | Georgian | ✅ Enabled |
| U+1100–U+11FF | Hangul Jamo | ✅ Enabled |
| U+1200–U+137F | Ethiopic | ✅ Enabled |
| U+1380–U+139F | Ethiopic Supplement | ❌ Disabled |
| U+13A0–U+13FF | Cherokee | ❌ Disabled |
| U+1400–U+167F | Unified Canadian Aboriginal Syllabics | ❌ Disabled |
| U+1680–U+169F | Ogham | ❌ Disabled |
| U+16A0–U+16FF | Runic | ❌ Disabled |
| U+1700–U+171F | Tagalog | ❌ Disabled |
| U+1720–U+173F | Hanunoo | ❌ Disabled |
| U+1740–U+175F | Buhid | ❌ Disabled |
| U+1760–U+177F | Tagbanwa | ❌ Disabled |
| U+1780–U+17FF | Khmer | ❌ Disabled |
| U+1800–U+18AF | Mongolian | ✅ Enabled |
| U+18B0–U+18FF | Unified Canadian Aboriginal Syllabics Extended | ❌ Disabled |
| U+1900–U+194F | Limbu | ❌ Disabled |
| U+1950–U+197F | Tai Le | ❌ Disabled |
| U+1980–U+19DF | New Tai Lue | ❌ Disabled |
| U+19E0–U+19FF | Khmer Symbols | ❌ Disabled |
| U+1A00–U+1A1F | Buginese | ❌ Disabled |
| U+1A20–U+1AAF | Tai Tham | ❌ Disabled |
| U+1AB0–U+1AFF | Combining Diacritical Marks Extended | ❌ Disabled |
| U+1B00–U+1B7F | Balinese | ❌ Disabled |
| U+1B80–U+1BBF | Sundanese | ❌ Disabled |
| U+1BC0–U+1BFF | Batak | ❌ Disabled |
| U+1C00–U+1C4F | Lepcha | ❌ Disabled |
| U+1C50–U+1C7F | Ol Chiki | ❌ Disabled |
| U+1C80–U+1C8F | Cyrillic Extended-C | ❌ Disabled |
| U+1C90–U+1CBF | Georgian Extended | ❌ Disabled |
| U+1CC0–U+1CCF | Sundanese Supplement | ❌ Disabled |
| U+1CD0–U+1CFF | Vedic Extensions | ❌ Disabled |
| U+1D00–U+1D7F | Phonetic Extensions | ✅ Enabled |
| U+1D80–U+1DBF | Phonetic Extensions Supplement | ✅ Enabled |
| U+1DC0–U+1DFF | Combining Diacritical Marks Supplement | ✅ Enabled |
| U+1E00–U+1EFF | Latin Extended Additional | ✅ Enabled |
| U+1F00–U+1FFF | Greek Extended | ✅ Enabled |
| U+2000–U+206F | General Punctuation | ✅ Enabled |
| U+2070–U+209F | Superscripts and Subscripts | ✅ Enabled |
| U+20A0–U+20CF | Currency Symbols | ✅ Enabled |
| U+20D0–U+20FF | Combining Diacritical Marks for Symbols | ✅ Enabled |
| U+2100–U+214F | Letterlike Symbols | ✅ Enabled |
| U+2150–U+218F | Number Forms | ✅ Enabled |
| U+2190–U+21FF | Arrows | ✅ Enabled |
| U+2200–U+22FF | Mathematical Operators | ✅ Enabled |
| U+2300–U+23FF | Miscellaneous Technical | ✅ Enabled |
| U+2400–U+243F | Control Pictures | ✅ Enabled |
| U+2440–U+245F | Optical Character Recognition | ✅ Enabled |
| U+2460–U+24FF | Enclosed Alphanumerics | ✅ Enabled |
| U+2500–U+257F | Box Drawing | ✅ Enabled |
| U+2580–U+259F | Block Elements | ✅ Enabled |
| U+25A0–U+25FF | Geometric Shapes | ✅ Enabled |
| U+2600–U+26FF | Miscellaneous Symbols | ✅ Enabled |
| U+2700–U+27BF | Dingbats | ✅ Enabled |
| U+27C0–U+27EF | Miscellaneous Mathematical Symbols-A | ✅ Enabled |
| U+27F0–U+27FF | Supplemental Arrows-A | ✅ Enabled |
| U+2800–U+28FF | Braille Patterns | ✅ Enabled |
| U+2900–U+297F | Supplemental Arrows-B | ✅ Enabled |
| U+2980–U+29FF | Miscellaneous Mathematical Symbols-B | ✅ Enabled |
| U+2A00–U+2AFF | Supplemental Mathematical Operators | ✅ Enabled |
| U+2B00–U+2BFF | Miscellaneous Symbols and Arrows | ✅ Enabled |
| U+2C00–U+2C5F | Glagolitic | ✅ Enabled |
| U+2C60–U+2C7F | Latin Extended-C | ✅ Enabled |
| U+2C80–U+2CFF | Coptic | ✅ Enabled |
| U+2D00–U+2D2F | Georgian Supplement | ❌ Disabled |
| U+2D30–U+2D7F | Tifinagh | ❌ Disabled |
| U+2D80–U+2DDF | Ethiopic Extended | ❌ Disabled |
| U+2DE0–U+2DFF | Cyrillic Extended-A | ❌ Disabled |
| U+2E00–U+2E7F | Supplemental Punctuation | ✅ Enabled |
| U+2E80–U+2EFF | CJK Radicals Supplement | ❌ Disabled |
| U+2F00–U+2FDF | Kangxi Radicals | ❌ Disabled |
| U+2FF0–U+2FFF | Ideographic Description Characters | ❌ Disabled |
| U+3000–U+303F | CJK Symbols and Punctuation | ❌ Disabled |
| U+3040–U+309F | Hiragana | ❌ Disabled |
| U+30A0–U+30FF | Katakana | ❌ Disabled |
| U+3100–U+312F | Bopomofo | ❌ Disabled |
| U+3130–U+318F | Hangul Compatibility Jamo | ❌ Disabled |
| U+3190–U+319F | Kanbun | ❌ Disabled |
| U+31A0–U+31BF | Bopomofo Extended | ❌ Disabled |
| U+31C0–U+31EF | CJK Strokes | ❌ Disabled |
| U+31F0–U+31FF | Katakana Phonetic Extensions | ❌ Disabled |
| U+3200–U+32FF | Enclosed CJK Letters and Months | ❌ Disabled |
| U+3300–U+33FF | CJK Compatibility | ❌ Disabled |
| U+3400–U+4DBF | CJK Unified Ideographs Extension A (~6,592 glyphs) | ❌ Disabled |
| U+4DC0–U+4DFF | Yijing Hexagram Symbols | ❌ Disabled |
| U+4E00–U+9FFF | CJK Unified Ideographs (~20,992 glyphs) | ❌ Disabled |
| U+A000–U+A48F | Yi Syllables | ✅ Enabled |
| U+A490–U+A4CF | Yi Radicals | ✅ Enabled |
| U+A4D0–U+A4FF | Lisu | ❌ Disabled |
| U+A500–U+A63F | Vai | ✅ Enabled |
| U+A640–U+A69F | Cyrillic Extended-B | ❌ Disabled |
| U+A6A0–U+A6FF | Bamum | ❌ Disabled |
| U+A700–U+A71F | Modifier Tone Letters | ❌ Disabled |
| U+A720–U+A7FF | Latin Extended-D | ✅ Enabled |
| U+A800–U+A82F | Syloti Nagri | ❌ Disabled |
| U+A830–U+A83F | Common Indic Number Forms | ❌ Disabled |
| U+A840–U+A87F | Phags-pa | ❌ Disabled |
| U+A880–U+A8DF | Saurashtra | ❌ Disabled |
| U+A8E0–U+A8FF | Devanagari Extended | ❌ Disabled |
| U+A900–U+A92F | Kayah Li | ❌ Disabled |
| U+A930–U+A95F | Rejang | ❌ Disabled |
| U+A960–U+A97F | Hangul Jamo Extended-A | ❌ Disabled |
| U+A980–U+A9DF | Javanese | ❌ Disabled |
| U+A9E0–U+A9FF | Myanmar Extended-B | ❌ Disabled |
| U+AA00–U+AA5F | Cham | ✅ Enabled |
| U+AA60–U+AA7F | Myanmar Extended-A | ❌ Disabled |
| U+AA80–U+AADF | Tai Viet | ❌ Disabled |
| U+AAE0–U+AAFF | Meetei Mayek Extensions | ❌ Disabled |
| U+AB00–U+AB2F | Ethiopic Extended-A | ❌ Disabled |
| U+AB30–U+AB6F | Latin Extended-E | ✅ Enabled |
| U+AB70–U+ABBF | Cherokee Supplement | ❌ Disabled |
| U+ABC0–U+ABFF | Meetei Mayek | ❌ Disabled |
| U+AC00–U+D7AF | Hangul Syllables (~11,184 glyphs) | ❌ Disabled |
| U+D7B0–U+D7FF | Hangul Jamo Extended-B | ❌ Disabled |
| U+F900–U+FAFF | CJK Compatibility Ideographs | ❌ Disabled |
| U+FB00–U+FB4F | Alphabetic Presentation Forms | ✅ Enabled |
| U+FB50–U+FDFF | Arabic Presentation Forms-A | ❌ Disabled |
| U+FE00–U+FE0F | Variation Selectors | ❌ Disabled |
| U+FE10–U+FE1F | Vertical Forms | ❌ Disabled |
| U+FE20–U+FE2F | Combining Half Marks | ✅ Enabled |
| U+FE30–U+FE4F | CJK Compatibility Forms | ❌ Disabled |
| U+FE50–U+FE6F | Small Form Variants | ✅ Enabled |
| U+FE70–U+FEFF | Arabic Presentation Forms-B | ❌ Disabled |
| U+FF00–U+FFEF | Halfwidth and Fullwidth Forms | ✅ Enabled |
| U+FFF0–U+FFFF | Specials | ✅ Enabled |

</details>

<details>
<summary>SMP coverage - Supplementary Multilingual Plane (U+10000–U+1FFFF)</summary>

| Range | Block | Status |
|-------|-------|--------|
| U+10000–U+1007F | Linear B Syllabary | ❌ Disabled |
| U+10080–U+100FF | Linear B Ideograms | ❌ Disabled |
| U+10100–U+1013F | Aegean Numbers | ❌ Disabled |
| U+10140–U+1018F | Ancient Greek Numbers | ❌ Disabled |
| U+10190–U+101CF | Ancient Symbols | ❌ Disabled |
| U+101D0–U+101FF | Phaistos Disc | ❌ Disabled |
| U+10280–U+1029F | Lycian | ❌ Disabled |
| U+102A0–U+102DF | Carian | ❌ Disabled |
| U+102E0–U+102FF | Coptic Epact Numbers | ❌ Disabled |
| U+10300–U+1032F | Old Italic | ❌ Disabled |
| U+10330–U+1034F | Gothic | ❌ Disabled |
| U+10350–U+1037F | Old Permic | ❌ Disabled |
| U+10380–U+1039F | Ugaritic | ❌ Disabled |
| U+103A0–U+103DF | Old Persian | ❌ Disabled |
| U+10400–U+1044F | Deseret | ❌ Disabled |
| U+10450–U+1047F | Shavian | ❌ Disabled |
| U+10480–U+104AF | Osmanya | ❌ Disabled |
| U+104B0–U+104FF | Osage | ❌ Disabled |
| U+10500–U+1052F | Elbasan | ❌ Disabled |
| U+10530–U+1056F | Caucasian Albanian | ❌ Disabled |
| U+10570–U+105BF | Vithkuqi | ❌ Disabled |
| U+10600–U+1077F | Linear A | ❌ Disabled |
| U+10780–U+107BF | Latin Extended-F | ❌ Disabled |
| U+10800–U+1083F | Cypriot Syllabary | ❌ Disabled |
| U+10840–U+1085F | Imperial Aramaic | ❌ Disabled |
| U+10860–U+1087F | Palmyrene | ❌ Disabled |
| U+10880–U+108AF | Nabataean | ❌ Disabled |
| U+108E0–U+108FF | Hatran | ❌ Disabled |
| U+10900–U+1091F | Phoenician | ❌ Disabled |
| U+10920–U+1093F | Lydian | ❌ Disabled |
| U+10980–U+1099F | Meroitic Hieroglyphs | ❌ Disabled |
| U+109A0–U+109FF | Meroitic Cursive | ❌ Disabled |
| U+10A00–U+10A5F | Kharoshthi | ❌ Disabled |
| U+10A60–U+10A7F | Old South Arabian | ❌ Disabled |
| U+10A80–U+10A9F | Old North Arabian | ❌ Disabled |
| U+10AC0–U+10AFF | Manichaean | ❌ Disabled |
| U+10B00–U+10B3F | Avestan | ❌ Disabled |
| U+10B40–U+10B5F | Inscriptional Parthian | ❌ Disabled |
| U+10B60–U+10B7F | Inscriptional Pahlavi | ❌ Disabled |
| U+10B80–U+10BAF | Psalter Pahlavi | ❌ Disabled |
| U+10C00–U+10C4F | Old Turkic | ❌ Disabled |
| U+10C80–U+10CFF | Old Hungarian | ❌ Disabled |
| U+10D00–U+10D3F | Hanifi Rohingya | ❌ Disabled |
| U+10E60–U+10E7F | Rumi Numeral Symbols | ❌ Disabled |
| U+10E80–U+10EBF | Yezidi | ❌ Disabled |
| U+10F00–U+10F2F | Old Sogdian | ❌ Disabled |
| U+10F30–U+10F6F | Sogdian | ❌ Disabled |
| U+10F70–U+10FAF | Old Uyghur | ❌ Disabled |
| U+10FB0–U+10FDF | Chorasmian | ❌ Disabled |
| U+10FE0–U+10FFF | Elymaic | ❌ Disabled |
| U+11000–U+1107F | Brahmi | ❌ Disabled |
| U+11080–U+110CF | Kaithi | ❌ Disabled |
| U+110D0–U+110FF | Sora Sompeng | ❌ Disabled |
| U+11100–U+1114F | Chakma | ❌ Disabled |
| U+11150–U+1117F | Mahajani | ❌ Disabled |
| U+11180–U+111DF | Sharada | ❌ Disabled |
| U+111E0–U+111FF | Sinhala Archaic Numbers | ❌ Disabled |
| U+11200–U+1124F | Khojki | ❌ Disabled |
| U+11280–U+112AF | Multani | ❌ Disabled |
| U+112B0–U+112FF | Khudawadi | ❌ Disabled |
| U+11300–U+1137F | Grantha | ❌ Disabled |
| U+11400–U+1147F | Newa | ❌ Disabled |
| U+11480–U+114DF | Tirhuta | ❌ Disabled |
| U+11580–U+115FF | Siddham | ❌ Disabled |
| U+11600–U+1165F | Modi | ❌ Disabled |
| U+11660–U+1167F | Mongolian Supplement | ❌ Disabled |
| U+11680–U+116CF | Takri | ❌ Disabled |
| U+11700–U+1174F | Ahom | ❌ Disabled |
| U+11800–U+1184F | Dogra | ❌ Disabled |
| U+118A0–U+118FF | Warang Citi | ❌ Disabled |
| U+11900–U+1195F | Dives Akuru | ❌ Disabled |
| U+119A0–U+119FF | Nandinagari | ❌ Disabled |
| U+11A00–U+11A4F | Zanabazar Square | ❌ Disabled |
| U+11A50–U+11AAF | Soyombo | ❌ Disabled |
| U+11AB0–U+11ABF | Unified Canadian Aboriginal Syllabics Extended-A | ❌ Disabled |
| U+11AC0–U+11AFF | Pau Cin Hau | ❌ Disabled |
| U+11C00–U+11C6F | Bhaiksuki | ❌ Disabled |
| U+11C70–U+11CBF | Marchen | ❌ Disabled |
| U+11D00–U+11D5F | Masaram Gondi | ❌ Disabled |
| U+11D60–U+11DAF | Gunjala Gondi | ❌ Disabled |
| U+11EE0–U+11EFF | Makasar | ❌ Disabled |
| U+11FB0–U+11FBF | Lisu Supplement | ❌ Disabled |
| U+11FC0–U+11FFF | Tamil Supplement | ❌ Disabled |
| U+12000–U+123FF | Cuneiform | ❌ Disabled |
| U+12400–U+1247F | Cuneiform Numbers and Punctuation | ❌ Disabled |
| U+12480–U+1254F | Early Dynastic Cuneiform | ❌ Disabled |
| U+12F90–U+12FFF | Cypro-Minoan | ❌ Disabled |
| U+13000–U+1342F | Egyptian Hieroglyphs | ❌ Disabled |
| U+13430–U+1345F | Egyptian Hieroglyph Format Controls | ❌ Disabled |
| U+14400–U+1467F | Anatolian Hieroglyphs | ❌ Disabled |
| U+16800–U+16A3F | Bamum Supplement | ❌ Disabled |
| U+16A40–U+16A6F | Mro | ❌ Disabled |
| U+16A70–U+16ACF | Tangsa | ❌ Disabled |
| U+16AD0–U+16AFF | Bassa Vah | ❌ Disabled |
| U+16B00–U+16B8F | Pahawh Hmong | ❌ Disabled |
| U+16E40–U+16E9F | Medefaidrin | ❌ Disabled |
| U+16F00–U+16F9F | Miao | ❌ Disabled |
| U+16FE0–U+16FFF | Ideographic Symbols and Punctuation | ❌ Disabled |
| U+17000–U+187FF | Tangut (~6,144 glyphs) | ❌ Disabled |
| U+18800–U+18AFF | Tangut Components | ❌ Disabled |
| U+18B00–U+18CFF | Khitan Small Script | ❌ Disabled |
| U+18D00–U+18D7F | Tangut Supplement | ❌ Disabled |
| U+1AFF0–U+1AFFF | Kana Extended-B | ❌ Disabled |
| U+1B000–U+1B0FF | Kana Supplement | ❌ Disabled |
| U+1B100–U+1B12F | Kana Extended-A | ❌ Disabled |
| U+1B130–U+1B16F | Small Kana Extension | ❌ Disabled |
| U+1B170–U+1B2FF | Nushu | ❌ Disabled |
| U+1BC00–U+1BC9F | Duployan | ❌ Disabled |
| U+1BCA0–U+1BCAF | Shorthand Format Controls | ❌ Disabled |
| U+1CF00–U+1CFCF | Znamenny Musical Notation | ❌ Disabled |
| U+1D000–U+1D0FF | Byzantine Musical Symbols | ❌ Disabled |
| U+1D100–U+1D1FF | Musical Symbols | ❌ Disabled |
| U+1D200–U+1D24F | Ancient Greek Musical Notation | ❌ Disabled |
| U+1D2C0–U+1D2DF | Kaktovik Numerals | ❌ Disabled |
| U+1D2E0–U+1D2FF | Mayan Numerals | ❌ Disabled |
| U+1D300–U+1D35F | Tai Xuan Jing Symbols | ❌ Disabled |
| U+1D360–U+1D37F | Counting Rod Numerals | ❌ Disabled |
| U+1D400–U+1D7FF | Mathematical Alphanumeric Symbols | ❌ Disabled |
| U+1D800–U+1DAAF | Sutton SignWriting | ❌ Disabled |
| U+1DF00–U+1DFFF | Latin Extended-G | ❌ Disabled |
| U+1E000–U+1E02F | Glagolitic Supplement | ❌ Disabled |
| U+1E030–U+1E08F | Cyrillic Extended-D | ❌ Disabled |
| U+1E100–U+1E14F | Nyiakeng Puachue Hmong | ❌ Disabled |
| U+1E290–U+1E2BF | Toto | ❌ Disabled |
| U+1E2C0–U+1E2FF | Wancho | ❌ Disabled |
| U+1E4D0–U+1E4FF | Nag Mundari | ❌ Disabled |
| U+1E7E0–U+1E7FF | Ethiopic Extended-B | ❌ Disabled |
| U+1E800–U+1E8DF | Mende Kikakui | ❌ Disabled |
| U+1E900–U+1E95F | Adlam | ❌ Disabled |
| U+1EC70–U+1ECBF | Indic Siyaq Numbers | ❌ Disabled |
| U+1ED00–U+1ED4F | Ottoman Siyaq Numbers | ❌ Disabled |
| U+1EE00–U+1EEFF | Arabic Mathematical Alphabetic Symbols | ❌ Disabled |
| U+1F000–U+1F02F | Mahjong Tiles | ❌ Disabled |
| U+1F030–U+1F09F | Domino Tiles | ❌ Disabled |
| U+1F0A0–U+1F0FF | Playing Cards | ❌ Disabled |
| U+1F100–U+1F1FF | Enclosed Alphanumeric Supplement | ❌ Disabled |
| U+1F200–U+1F2FF | Enclosed Ideographic Supplement | ❌ Disabled |
| U+1F300–U+1F5FF | Miscellaneous Symbols and Pictographs | ❌ Disabled |
| U+1F600–U+1F64F | Emoticons | ❌ Disabled |
| U+1F650–U+1F67F | Ornamental Dingbats | ❌ Disabled |
| U+1F680–U+1F6FF | Transport and Map Symbols | ❌ Disabled |
| U+1F700–U+1F77F | Alchemical Symbols | ❌ Disabled |
| U+1F780–U+1F7FF | Geometric Shapes Extended | ❌ Disabled |
| U+1F800–U+1F8FF | Supplemental Arrows-C | ❌ Disabled |
| U+1F900–U+1F9FF | Supplemental Symbols and Pictographs | ✅ Enabled |
| U+1FA00–U+1FA6F | Chess Symbols | ❌ Disabled |
| U+1FA70–U+1FAFF | Symbols and Pictographs Extended-A | ❌ Disabled |
| U+1FB00–U+1FBFF | Symbols for Legacy Computing | ❌ Disabled |

</details>

## Docker Compose

Minecraft Font Generator can be used as a **one-shot build task** in a Docker
Compose stack. This is useful when another service (a Discord bot, a web app, a
resource pack compiler, etc.) needs the generated font files but you don't want
to host them in a repository or keep a persistent container running.

The pattern:
1. An ephemeral container clones the repo, installs the tool, and compiles the fonts.
2. The output is written to a shared volume.
3. The container exits and is removed automatically.
4. Other services mount the same volume to consume the font files.

### Basic One-Shot Task

Add this service to your project's `docker-compose.yml`:

```yaml
services:
  font-generator:
    image: python:3-slim
    user: "1000:1000"
    working_dir: /build
    environment:
      MCFONT_VERSION: "1.21.4"
      MCFONT_STYLES: "regular,bold"
      MCFONT_SILENT: "true"
      MCFONT_OUTPUT: "/output"
      PATH: "/home/builder/.local/bin:$PATH"
    volumes:
      - fonts:/output
    entrypoint: ["bash", "-c"]
    command:
      - |
        pip install --user --quiet git+https://github.com/minecraft-library/font-generator.git &&
        minecraft-font-generator
    profiles:
      - build

volumes:
  fonts:
```

> [!TIP]
> The `profiles: [build]` setting prevents this service from starting during a
> normal `docker compose up`. It only runs when explicitly invoked.

<details>
<summary>Multi-service example (bot depends on font generation)</summary>

```yaml
services:
  font-generator:
    image: python:3-slim
    user: "1000:1000"
    working_dir: /build
    environment:
      MCFONT_VERSION: "1.21.4"
      MCFONT_STYLES: "regular,bold"
      MCFONT_SILENT: "true"
      MCFONT_OUTPUT: "/output"
      PATH: "/home/builder/.local/bin:$PATH"
    volumes:
      - fonts:/output
    entrypoint: ["bash", "-c"]
    command:
      - |
        pip install --user --quiet git+https://github.com/minecraft-library/font-generator.git &&
        minecraft-font-generator

  bot:
    build: .
    volumes:
      - fonts:/app/fonts:ro
    depends_on:
      font-generator:
        condition: service_completed_successfully
    environment:
      FONT_PATH: /app/fonts

volumes:
  fonts:
```

In this setup:
- `font-generator` runs first, compiles the fonts into the shared `fonts` volume, then exits.
- `bot` waits for `font-generator` to complete successfully before starting.
- The `bot` service mounts the same volume as read-only (`:ro`) at `/app/fonts`.

</details>

### Running the Task

```bash
# Run only the font generation task
docker compose run --rm font-generator

# Or if using profiles
docker compose --profile build run --rm font-generator

# Start the full stack (bot waits for font-generator to finish)
docker compose up
```

> [!NOTE]
> The `--rm` flag automatically removes the container after it exits, so no
> cleanup is needed.

To **rebuild fonts** (e.g., after a Minecraft version update), remove the
existing volume and re-run:

```bash
docker volume rm <project>_fonts
docker compose run --rm font-generator
```

## How It Works

The tool runs a six-stage pipeline:

```
1. Clean       Wipes and recreates work/ and output/ directories
       ↓
2. Download    Fetches the Minecraft version manifest from the Piston API,
               downloads the client JAR, extracts font assets, and optionally
               downloads GNU Unifont hex files
       ↓
3. Parse       Detects the font asset format and parses accordingly:
               - JSON (1.13+): Reads default.json font providers with
                 explicit Unicode character mappings
               - Binary (1.12.2 and earlier): Reads glyph_sizes.bin
                 width data and unicode_page_XX.png / ascii.png textures
               Slices individual glyphs from the bitmap sheets using
               flood-fill contour tracing
       ↓
4. Build       Merges provider glyphs (high priority) with unifont fallback
               glyphs (low priority) into a unified glyph map, keyed by
               codepoint and grouped by style. Processes alternate fonts
               (Galactic, Illageralt) by overlaying their glyphs onto the
               Regular map. Pre-computes scaled coordinates (pixel space →
               font units) for all glyphs
       ↓
5. Create      Initializes fontTools TTFont tables for each enabled style,
               converts all glyphs with a single progress bar, applies italic
               shear transforms where needed, then finalizes and saves the
               font files
       ↓
6. Validate    (Optional, --validate) Runs FontForge validation on all
               generated font files, reporting per-glyph errors by type
```

### Glyph Processing

Each bitmap glyph goes through:

1. **Flood-fill labeling** - Identifies connected pixel groups
2. **Boundary tracing** - Right-hand rule extracts contour edges
3. **Corner extraction** - Converts edges to corner points for vector outlines
4. **Bold expansion** - Bold glyphs get a 1px rightward expansion before tracing
5. **Coordinate scaling** - Pixel coordinates are mapped to font units (`UNITS_PER_EM = 1024`)
6. **Italic shear** - Italic variants apply a shear transform to the pre-computed coordinates
7. **Pen drawing** - `T2CharStringPen` for CFF outlines or `TTGlyphPen` for TrueType

## Project Structure

```
font-generator/
├── minecraft_fontgen/
│   ├── __init__.py
│   ├── __main__.py                # python -m entry point
│   ├── main.py                    # Pipeline orchestration
│   ├── cli.py                     # Argument parsing, env var resolution
│   ├── config.py                  # Constants and runtime configuration
│   ├── piston.py                  # Mojang Piston API, JAR/unifont downloads
│   ├── file_io.py                 # Bitmap slicing, contour tracing, glyph maps
│   ├── font_creator.py            # Batch font file creation
│   ├── functions.py               # Shared utilities (logging, HTTP, codepoints)
│   ├── validate_font.py           # FontForge validation script (--validate)
│   ├── glyph/
│   │   ├── glyph.py               # Glyph scaling, transforms, pen drawing
│   │   └── glyph_storage.py       # Glyph accumulation, cmap, final output
│   └── table/                     # One file per OpenType/TrueType table
│       ├── header.py              # head
│       ├── horizontal_header.py   # hhea
│       ├── horizontal_metrics.py  # hmtx
│       ├── maximum_profile.py     # maxp
│       ├── postscript.py          # post
│       ├── name.py                # name
│       ├── os2_metrics.py         # OS/2
│       ├── glyph_mappings.py      # cmap (Format 4 + 12)
│       ├── opentype.py            # CFF tables
│       └── truetype.py            # glyf/loca tables
├── pyproject.toml
├── LICENSE.md
├── COPYRIGHT.md
├── CONTRIBUTING.md
└── CLAUDE.md
```

### Runtime Directories

These are created during execution and excluded from version control:

| Directory | Contents |
|-----------|----------|
| `work/` | Downloaded JAR, extracted assets, sliced tile bitmaps, debug SVGs |
| `output/` | Generated `.otf` or `.ttf` font files |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style
guidelines, and how to submit a pull request.

## License

This project is licensed under the **Apache License 2.0** - see [LICENSE](LICENSE.md)
for the full text.

See [COPYRIGHT.md](COPYRIGHT.md) for third-party attribution notices, including
information about Mojang AB's copyrighted assets and GNU Unifont licensing.
