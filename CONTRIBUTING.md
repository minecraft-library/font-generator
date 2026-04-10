# Contributing to Minecraft Font Generator

Thank you for your interest in contributing! This document explains how to get
started, what to expect during the review process, and the conventions this
project follows.

## Table of Contents

- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Development Setup](#development-setup)
  - [Installing FontForge](#installing-fontforge)
- [Making Changes](#making-changes)
  - [Branching Strategy](#branching-strategy)
  - [Code Style](#code-style)
  - [Commit Messages](#commit-messages)
  - [Validating Output](#validating-output)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Issues](#reporting-issues)
- [Project Architecture](#project-architecture)
- [Legal](#legal)

## Getting Started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Required |
| pip | Latest | Comes with Python |
| Git | 2.x+ | For cloning and contributing |
| [FontForge](https://fontforge.org/) | Latest | Required for font validation (`--validate`) |

### Development Setup

1. **Fork and clone the repository**

   [Fork the repository](https://github.com/minecraft-library/font-generator/fork),
   then clone your fork:

   ```bash
   git clone https://github.com/<your-username>/font-generator.git
   cd font-generator
   ```

2. **Create and activate a virtual environment**

   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install in editable mode**

   This installs the package and all dependencies so that changes to the source
   files are reflected immediately without reinstalling.

   ```bash
   pip install -e .
   ```

4. **Verify the installation**

   ```bash
   python -m minecraft_fontgen --help
   ```

### Installing FontForge

FontForge is used for font validation during development. It runs as a
separate executable, not as a Python dependency - the `--validate` flag
invokes `validate_font.py` through FontForge's own Python interpreter via
subprocess.

<details>
<summary>Linux</summary>

```bash
# Debian / Ubuntu
sudo apt install fontforge

# Fedora
sudo dnf install fontforge

# Arch
sudo pacman -S fontforge
```

</details>

<details>
<summary>macOS</summary>

```bash
brew install fontforge
```

</details>

<details>
<summary>Windows</summary>

Download the installer from the [FontForge website](https://fontforge.org/en-US/downloads/)
and ensure the installation directory is added to your `PATH`. By default this
is `C:\Program Files (x86)\FontForgeBuilds\bin`.

</details>

After installation, confirm FontForge is on your `PATH`:

```bash
fontforge --version
```

## Making Changes

### Branching Strategy

- Create a feature branch from `master` for your work.
- Use a descriptive branch name: `fix/cmap-format12-overflow`, `feat/svg-export`,
  `docs/docker-instructions`.

```bash
git checkout -b feat/my-feature master
```

### Code Style

This project does not currently enforce a linter or formatter, but please follow
these conventions:

- **Imports** - Use absolute imports from the `minecraft_fontgen` package.
  ```python
  from minecraft_fontgen.config import UNITS_PER_EM
  ```
- **Naming** - `snake_case` for functions and variables, `UPPER_SNAKE_CASE` for
  module-level constants, `PascalCase` for classes.
- **Docstrings** - Every public function should have a one-line docstring
  describing what it does.
- **Type hints** - Encouraged but not strictly required. Use them where they
  clarify intent.
- **Line length** - Aim for 120 characters or less.

### Commit Messages

Write clear, concise commit messages that describe *what* changed and *why*.

```
Add MCFONT_VERSION env var for non-interactive version selection

Allows CI/CD and Docker workflows to specify the Minecraft version
without requiring an interactive terminal prompt.
```

- Use the imperative mood ("Add", "Fix", "Update", not "Added", "Fixes").
- Keep the subject line under 72 characters.
- Add a body when the *why* isn't obvious from the subject.

### Validating Output

If your change touches glyph processing, contour tracing, or font table
construction, validate the generated fonts with FontForge (see
[Installing FontForge](#installing-fontforge)). The `--validate` flag runs
FontForge's per-glyph validator on all generated font files after the build:

```bash
# Via CLI flag
python -m minecraft_fontgen --version 1.21.4 --validate

# Via environment variable (useful in IDE run configurations)
MCFONT_VALIDATE=1 python -m minecraft_fontgen --version 1.21.4
```

This reports errors grouped by type (wrong direction contours,
self-intersections, missing extrema, etc.). A clean build produces
`All N glyphs passed validation.` for each font file.

You can also validate an existing font file directly:

```bash
fontforge -lang=py -script minecraft_fontgen/validate_font.py output/Minecraft-Regular.otf
```

When submitting changes that affect font output, include the validation results
in your PR description to help reviewers verify correctness.

## Submitting a Pull Request

1. **Push your branch** to your fork.

   ```bash
   git push origin feat/my-feature
   ```

2. **Open a Pull Request** against the `master` branch of
   [minecraft-library/font-generator](https://github.com/minecraft-library/font-generator).

3. **In the PR description**, include:
   - A summary of the changes and the motivation behind them.
   - Steps to test or verify the changes (e.g., specific Minecraft versions,
     CLI flags, expected output).
   - Screenshots of generated font output if relevant (glyph rendering, debug
     SVGs, etc.).

4. **Respond to review feedback.** PRs may go through one or more rounds of
   review before being merged.

### What gets reviewed

- Correctness of glyph processing and font table output.
- Whether new configuration options follow the existing priority chain
  (CLI arg > env var > `.env` file > `config.py` defaults).
- Impact on the generated font files (any change to glyph tracing, scaling,
  or table construction should be verified with a font validator like
  FontForge or `fontTools.ttLib`).

## Reporting Issues

Use [GitHub Issues](https://github.com/minecraft-library/font-generator/issues)
to report bugs or request features.

When reporting a bug, include:

- **Python version** (`python --version`)
- **Operating system**
- **Minecraft version** you targeted
- **Full error traceback** (if applicable)
- **Steps to reproduce**
- **Expected vs. actual behavior**

## Project Architecture

A brief overview to help you find your way around the codebase:

```
minecraft_fontgen/
├── main.py             # Pipeline entry point (clean → download → parse → build → create)
├── cli.py              # Argument parsing and env var resolution
├── config.py           # All constants and runtime configuration
├── piston.py           # Mojang Piston API interaction, JAR/unifont downloading
├── file_io.py          # Bitmap slicing, contour tracing, glyph map building
├── font_creator.py     # Batch font file creation across all styles
├── functions.py        # Shared utilities (logging, HTTP, codepoint helpers)
├── validate_font.py   # FontForge validation script (--validate)
├── glyph/
│   ├── glyph.py        # Single glyph: scaling, shear transforms, pen drawing
│   └── glyph_storage.py# Glyph accumulation, cmap management, final write
└── table/
    ├── header.py       # head table
    ├── horizontal_header.py  # hhea table
    ├── horizontal_metrics.py # hmtx table
    ├── maximum_profile.py    # maxp table
    ├── postscript.py         # post table
    ├── name.py               # name table
    ├── os2_metrics.py        # OS/2 table
    ├── glyph_mappings.py     # cmap table (Format 4 + Format 12)
    ├── opentype.py           # CFF tables
    └── truetype.py           # glyf/loca tables
```

### Pipeline flow

```
parse_args() → clean_directories() → download_minecraft_assets()
  → parse_provider_file() → build_glyph_map() → create_font_files()
  → validate_fonts()  (optional, with --validate)
```

If your change touches glyph processing (`file_io.py`, `glyph/`), test with
both OpenType (`--type opentype`) and TrueType (`--type truetype`) output,
and run with `--validate` to catch contour winding and geometry issues.

## Legal

By submitting a pull request, you agree that your contributions are licensed
under the [Apache License 2.0](LICENSE.md), the same license that covers this
project.

This project processes copyrighted assets owned by Mojang AB at runtime. Do not
commit any Minecraft assets (textures, JARs, JSON files extracted from the
client) to the repository.
