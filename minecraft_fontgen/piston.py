import binascii
import io
import os
import zipfile

from io import BytesIO

from minecraft_fontgen.config import MINECRAFT_MANIFEST_URL, MINECRAFT_BIN_FILE, MINECRAFT_JSON_FILE, WORK_DIR, UNIFONT_PATH
from minecraft_fontgen.functions import fetch_bytes, fetch_json, fetch_minecraft_resource, fetch_minecraft_resource_bytes, in_unifont_ranges, log


# ==========================================
# === Entry point: download + extract
# ==========================================

def download_minecraft_assets(mc_version=None):
    """Downloads and extracts Minecraft font assets and unifont fallbacks via the Piston API."""
    log(f"🧩 Processing minecraft piston data...")
    version_json = select_minecraft_version(mc_version)
    version_data = fetch_json(version_json["url"], label="version metadata")

    if "assetIndex" not in version_data:
        raise RuntimeError("→ ❌ Missing asset index in version data.")

    # Download and extract client JAR
    jar_data = BytesIO(fetch_bytes(version_data["downloads"]["client"]["url"], label="client.jar"))
    #save_jar_to_disk(jar_data, WORK_DIR)
    files = extract_font_assets(jar_data, WORK_DIR)

    matched_file = None
    matched_format = None
    for file in files:
        if MINECRAFT_BIN_FILE.endswith(file):
            matched_file = MINECRAFT_BIN_FILE
            matched_format = "bin"
        elif MINECRAFT_JSON_FILE.endswith(file):
            matched_file = MINECRAFT_JSON_FILE
            matched_format = "json"

        if matched_file:
            log(f"→ 🔢 Detected {matched_format} format...")
            break

    if not matched_file:
        log("→ ❌ Could not detect font assets format.")

    # Download unifont fallback glyphs (not available in older versions)
    unifont_glyphs = None
    try:
        asset_index = fetch_json(version_data["assetIndex"]["url"], label="asset index")
        unifont_objects, size_overrides = find_unifont_objects(asset_index)
        unifont_glyphs = download_unifont_glyphs(unifont_objects)
    except RuntimeError:
        log("→ ⚠️ Unifont not available for this version, skipping...")

    return matched_file, matched_format, unifont_glyphs


# ==========================================
# === Version selection
# ==========================================

def select_minecraft_version(mc_version=None):
    """Selects a Minecraft version. Uses mc_version directly if provided, otherwise prompts interactively."""
    versions = fetch_minecraft_versions()

    if mc_version:
        if mc_version == "latest":
            mc_version = versions["latest"]["release"]
            log(f"→ 📂 Resolved 'latest' to {mc_version}")
        elif mc_version == "latest-snapshot":
            mc_version = versions["latest"]["snapshot"]
            log(f"→ 📂 Resolved 'latest-snapshot' to {mc_version}")

        for version_type in ["releases", "snapshots"]:
            if mc_version in versions[version_type]:
                log(f"→ 📂 Using version {mc_version}")
                return versions[version_type][mc_version]
        raise RuntimeError(f"Version '{mc_version}' not found in releases or snapshots")

    selected_version = None
    selected_data = None

    while selected_version is None:
        version = input("→ 📂 Enter version number (or 'help'): ").strip().lower()

        def dump_versions(_versions):
            #print(f"Found {len(versions)}:")

            for i, (_version, _) in enumerate(_versions.items(), 1):
                tabs = '\t' * (1 if len(_version) > 3 else 2)
                log(_version, end=tabs)

                if i % 15 == 0:
                    log()  # Newline after every 15 items

            # Final newline if needed
            if len(_versions) % 15 != 0:
                log()

        if version in ["exit", "leave", "quit", "stop"]:
            log("Exiting...")
            break

        if version in ["h", "?", "help"]:
            log("Available commands:")
            log(" - 'exit' or 'quit' to quit")
            log(" - 'h', '?' or 'help' to show this help message")
            log(" - 'r' or 'releases' to list all available releases")
            log(" - 's' or 'snapshots' to list all available releases")
            continue

        if version in ["r", "releases", "release"]:
            dump_versions(versions["releases"])
            continue

        if version in ["s", "snapshots", "snapshot"]:
            dump_versions(versions["snapshots"])
            continue

        for _type in versions:
            if version in versions[_type]:
                selected_version = version
                selected_data = versions[_type][version]
                break

        if not selected_version:
            log("Invalid version. Please try again.")

    return selected_data

def fetch_minecraft_versions():
    """Fetches the Minecraft version manifest and organizes versions by type."""
    manifest = fetch_json(MINECRAFT_MANIFEST_URL, label="version manifest")

    def filter_type(version_type):
        return {
            version["id"]: {
                "type": version["type"],
                "url": version["url"]
            }
            for version in manifest["versions"] if version["type"] == version_type}

    return {
        "latest": manifest["latest"],
        "releases": filter_type("release"),
        "snapshots": filter_type("snapshot")
    }


# ==========================================
# === JAR extraction
# ==========================================

def extract_font_assets(jar_data, output_path):
    """Extracts font-related files (default.json, font textures) from the Minecraft JAR."""
    log("→ 📦 Extracting font assets...")
    os.makedirs(output_path, exist_ok=True)
    extracted = []

    with zipfile.ZipFile(jar_data) as jar:
        for file in jar.namelist():
            if file.endswith("default.json") or "font/" in file:
                jar.extract(file, path=output_path)
                extracted.append(file)

    return extracted

def save_jar_to_disk(jar_data, output_path):
    """Writes the downloaded JAR BytesIO to disk as minecraft.jar."""
    log(f"→ 📦 Extracting client.jar...")
    with open(f"{output_path}/minecraft.jar", "wb") as f:
        f.write(jar_data.getbuffer())


# ==========================================
# === Unifont downloading + parsing
# ==========================================

def find_unifont_objects(asset_index):
    """Locates unifont ZIP file hashes and size overrides in the Minecraft asset index."""
    log(f"🧩 Processing unifont objects...")
    found = {}
    size_overrides = []
    objects = asset_index.get("objects", {})

    # Always read the include file to get hex_file paths
    include_json = objects.get(UNIFONT_PATH)
    if not include_json or "hash" not in include_json:
        raise RuntimeError(f"Could not locate {UNIFONT_PATH} in asset index")

    # Download and parse the include file
    include = fetch_minecraft_resource(include_json["hash"], label="unifont index")

    # Extract hex_file from all providers
    for provider in include.get("providers", []):
        hex_file = provider.get("hex_file", "")

        if hex_file.startswith("minecraft:"):
            # Convert "minecraft:font/unifont.zip" -> "minecraft/font/unifont.zip"
            key = hex_file.replace("minecraft:", "minecraft/", 1)
            obj = objects.get(key)

            if obj and "hash" in obj:
                log(f" → 🔣 Detected {key}...")
                found[key] = obj["hash"]

        # Extract size_overrides for future use
        overrides = provider.get("size_overrides", [])
        if overrides:
            size_overrides.extend(overrides)

    if not found:
        raise RuntimeError("Could not locate unifont ZIPs from include file")

    return found, size_overrides

def download_unifont_glyphs(unifont_objects):
    """Downloads unifont ZIP archives and parses all .hex files into bitmap glyph data."""
    glyphs = {}

    for path, sha1 in unifont_objects.items():
        zip_bytes = fetch_minecraft_resource_bytes(sha1, label=path)
        log(f"→ 📦 Extracting {path}...")

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
            for name in zip_file.namelist():
                if not name.lower().endswith(".hex"):
                    continue

                glyph = parse_unifont_hex_bytes(zip_file.read(name))
                glyphs.update(glyph) # later files override

    return glyphs

def parse_unifont_hex_bytes(hex_bytes: bytes):
    """
    Parse GNU Unifont .hex content -> dict[int, list[list[int]]]
    Each glyph becomes a 16-row bitmap of 0/1 ints (duospaced 8x16 or 16x16; some wider blocks exist).
    """
    glyphs = {}

    for raw_line in hex_bytes.splitlines():
        line = raw_line.strip()

        if not line or b':' not in line:
            continue

        cp_hex, bmp_hex = line.split(b':', 1)
        try:
            codepoint = int(cp_hex, 16)
        except ValueError:
            continue

        # Skip codepoints outside desired ranges
        if not in_unifont_ranges(codepoint):
            continue

        # Each two hex chars -> one byte = 8 horizontal pixels; bitmap is 16 rows high.
        byte_len = len(bmp_hex) // 2
        if byte_len == 0:
            continue

        bytes_per_row = byte_len // 16 # Unifont rows are concatenated with no separators: 16 rows, each width/8 bytes.
        width = bytes_per_row * 8 # Width is commonly 8 (32 hex digits) or 16 (64 hex digits) pixels wide, infer from total hex length.
        img_bits = []
        row_offset = 0
        raw = binascii.unhexlify(bmp_hex)

        for _ in range(16):
            row = []
            row_bytes = raw[row_offset: row_offset + bytes_per_row]
            row_offset += bytes_per_row

            for b in row_bytes:
                for bit in range(7, -1, -1):
                    row.append((b >> bit) & 1)

            # Trim to declared width (safety)
            img_bits.append(row[:width])

        glyphs[codepoint] = img_bits

    return glyphs
