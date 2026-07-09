import json
import os
import re
import requests
import subprocess
import sys

import minecraft_fontgen.config as config

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
