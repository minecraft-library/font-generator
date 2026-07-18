import json
import os
import re
import requests
import subprocess
import sys
import time

import minecraft_fontgen.config as config

def resolve_source_date_epoch() -> int:
    """Resolves the build timestamp used for reproducible builds.

    Resolution order: the SOURCE_DATE_EPOCH environment variable (the
    reproducible-builds standard name) when set and integer-parseable; else
    config.SOURCE_DATE_EPOCH when it is not None; else the current wall-clock
    time. A non-integer environment value fails loud so a mistyped epoch never
    silently degrades to a live timestamp. Lives here rather than in the header
    module to avoid header<->config coupling."""
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            raise SystemExit(f"SOURCE_DATE_EPOCH must be an integer, got {raw!r}")
    if config.SOURCE_DATE_EPOCH is not None:
        return int(config.SOURCE_DATE_EPOCH)
    return int(time.time())

def set_silent(value):
    """Sets the global silent mode flag."""
    config.SILENT_LOG = value

def is_silent():
    """Returns True if silent mode is enabled."""
    return config.SILENT_LOG

def log(*args, **kwargs):
    """Prints to stdout only when silent mode is disabled."""
    if not config.SILENT_LOG:
        print(*args, **kwargs)

def sanitize_fs_name(name):
    """Reduces a string to a Windows-safe directory name."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "pack"

def get_unicode_codepoint(unicode_char: str):
    """Converts a Unicode character string to its integer codepoint, handling surrogates."""
    try:
        utf16 = unicode_char.encode("utf-16", "surrogatepass")
        real_char = utf16.decode("utf-16")
        return ord(real_char)
    except Exception:
        return None

def get_font_type(bold = False, italic = False):
    """Returns the font style name (Regular, Bold, Italic, or BoldItalic)."""
    gtype = "Bold" if bold else "Regular"
    gtype = "Italic" if italic else gtype
    gtype = "BoldItalic" if bold and italic else gtype
    return gtype

def parse_json(text):
    """Parses JSON text, tolerating trailing commas (which Minecraft's JSONs sometimes include)."""
    cleaned = re.sub(r',\s*([}\]])', r'\1', text)
    return json.loads(cleaned)

def in_unifont_ranges(codepoint):
    """Returns True if the codepoint falls within any enabled UNIFONT_RANGES entry."""
    for start, end, enabled in config.UNIFONT_RANGES:
        if enabled and start <= codepoint <= end:
            return True
    return False

def fetch_bytes(url, label=None):
    """Downloads raw bytes from a URL and returns the response content."""
    log(f"→ 🌐 Downloading {label or url}...")
    request = requests.get(url, timeout=30)
    request.raise_for_status()
    return request.content

def fetch_json(url, label=None):
    """Downloads and parses JSON from a URL, tolerating trailing commas."""
    log(f"→ 🌐 Downloading {label or url}...")
    request = requests.get(url, timeout=30)
    request.raise_for_status()
    return parse_json(request.text)

def fetch_minecraft_resource(sha1, label=None):
    """Fetches a JSON resource from the Mojang CDN by its SHA-1 hash.
    (resources.download.minecraft.net/<first2>/<sha1>)"""
    return fetch_json(f"{config.MINECRAFT_RESOURCE_URL}/{sha1[:2]}/{sha1}", label=label)

def fetch_minecraft_resource_bytes(sha1, label=None):
    """Fetches raw bytes from the Mojang CDN by its SHA-1 hash."""
    return fetch_bytes(f"{config.MINECRAFT_RESOURCE_URL}/{sha1[:2]}/{sha1}", label=label)

def _is_noncharacter(codepoint):
    """A Unicode noncharacter (U+xFFFE / U+xFFFF in every plane) is never assigned a
    stored codepoint: some cmap tooling and renderers reject them, and skipping them
    costs nothing."""
    return (codepoint & 0xFFFF) in (0xFFFE, 0xFFFF)

def allocate_stored_codepoints(pairs):
    """Maps each (font_id, original_codepoint) pair to a synthetic stored codepoint.

    The colour track collapses to one .ttf per pack, but different pack font ids reuse
    the same private-use codepoints for different art. One cmap cannot key on those
    original codepoints, so every (font_id, original_codepoint) raster pair is assigned
    a stored codepoint here; the stored codepoint is what the merged font's cmap carries
    and the original survives only in the sidecar.

    `pairs` is any iterable of (font_id, codepoint) tuples; the result is a dict keyed
    by that tuple. Pairs are sorted lexicographically and assigned linearly from
    U+F0000 into plane 16, skipping noncharacters. Deterministic and total: identical
    input always produces the identical mapping, so the same input yields a
    byte-identical font and sidecar.

    Raises ValueError only when the plane-15+16 budget (131068 codepoints) is
    exhausted, which is 40x+ the reference packs' pair counts."""
    assignment = {}
    cursor = config.STORED_CP_START
    for key in sorted(pairs):
        while _is_noncharacter(cursor):
            cursor += 1
        if cursor > config.STORED_CP_END:
            raise ValueError(
                f"Stored-codepoint budget exhausted: more than {plane_budget()} "
                f"(font_id, codepoint) raster pairs cannot fit planes 15-16.")
        assignment[key] = cursor
        cursor += 1
    return assignment

def plane_budget():
    """Returns the number of assignable stored codepoints across planes 15 and 16
    (the inclusive window minus the four skipped noncharacters: U+FFFFE/F and
    U+10FFFE/F). 131072 - 4 = 131068 on the default window."""
    total = config.STORED_CP_END - config.STORED_CP_START + 1
    noncharacters = sum(1 for cp in range(config.STORED_CP_START, config.STORED_CP_END + 1)
                        if _is_noncharacter(cp))
    return total - noncharacters

def validate_fonts(font_files):
    """Runs FontForge validation on generated font files via subprocess."""
    script = os.path.join(os.path.dirname(__file__), config.VALIDATE_SCRIPT)
    if not os.path.isfile(script):
        log(f"→ ⚠️ Validation script not found: {script}", file=sys.stderr)
        return

    log(f"🔍 Validating {len(font_files)} font files...")
    result = subprocess.run(
        ["fontforge", "-lang=py", "-script", script] + font_files,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        text=True
    )

    if result.stdout:
        log(result.stdout)

    if result.returncode != 0 and result.stderr:
        print(result.stderr, file=sys.stderr)
