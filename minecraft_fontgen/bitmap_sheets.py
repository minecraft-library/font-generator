import hashlib
import json
import os

from minecraft_fontgen.asset_source import VanillaSource, split_resource_ref
from minecraft_fontgen.config import BITMAP_SHEETS_DIR_NAME, BITMAP_SHEETS_MANIFEST_NAME, DEFAULT_GLYPH_SIZE
from minecraft_fontgen.functions import log, parse_json

MANIFEST_PROVIDER_KEYS = ("type", "file", "height", "ascent", "chars")  # bitmap provider keys carried into the manifest


def emit_bitmap_sheets(provider_file, provider_format, output_dir, game_version, source=None):
    """Copies the vanilla bitmap font sheets byte-identical and writes a manifest of their provider metrics.

    Walks the bitmap providers of the vanilla default-font provider file
    (include/default.json) in provider order, copies each referenced texture PNG
    unchanged into <output_dir>/bitmap-sheets/<namespace>/<path>, and writes
    <output_dir>/bitmap-sheets/manifest.json containing the source game version
    plus each provider's verbatim definition (type, file, height with the
    default 8 made explicit, ascent, chars rows) and the sha256 of its emitted
    PNG. Non-bitmap providers are skipped. Bitmap provider keys outside
    MANIFEST_PROVIDER_KEYS (e.g. a filter block) are omitted from the manifest
    with a warning naming them, so schema drift in the vanilla chain is visible.

    Unlike the lenient OTF glyph pipeline, this mode fails loudly: a missing
    sheet texture or a provider the game itself would reject raises a
    RuntimeError instead of a skip-with-warn, because consumers rely on the
    emitted set being complete and vanilla-exact. Returns the manifest path.
    """
    if provider_format != "json":
        raise RuntimeError(
            f"--emit-bitmap-sheets requires the include/default.json font layout (Minecraft 1.20+), "
            f"got the '{provider_format}' format")

    log(f"🧩 Emitting vanilla bitmap sheets from {provider_file}...")
    if source is None:
        source = VanillaSource()

    with open(provider_file, "rb") as f:
        raw_text = f.read().decode("utf-8", errors="surrogatepass").lstrip("\ufeff")
    data = parse_json(raw_text)

    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, list):
        raise RuntimeError(f"'{provider_file}' has no providers array")

    sheets_dir = os.path.join(output_dir, BITMAP_SHEETS_DIR_NAME)
    entries = []
    emitted = {}  # ref -> sha256, so repeated references copy once

    for index, provider in enumerate(providers):
        if not isinstance(provider, dict):
            raise RuntimeError(f"Provider {index} is not a JSON object")
        if provider.get("type") != "bitmap":
            log(f"→ ⚠️ Skipping non-bitmap provider {index} (only bitmap sheets are emitted)")
            continue

        unknown_keys = sorted(key for key in provider if key not in MANIFEST_PROVIDER_KEYS)
        if unknown_keys:
            log(f"→ ⚠️ Bitmap provider {index} carries keys the manifest omits: {', '.join(unknown_keys)}")

        ref = _require_file_ref(provider, index)
        height, ascent = _require_metrics(provider, index)
        rows = _require_chars_rows(provider, index)

        if ref not in emitted:
            emitted[ref] = _copy_sheet(source, ref, sheets_dir, index)
        entries.append({
            "type": "bitmap",
            "file": ref,
            "height": height,
            "ascent": ascent,
            "chars": rows,
            "sha256": emitted[ref],
        })

    if not entries:
        raise RuntimeError(f"'{provider_file}' contains no bitmap providers")

    manifest_path = os.path.join(sheets_dir, BITMAP_SHEETS_MANIFEST_NAME)
    manifest = {"game_version": game_version, "providers": entries}
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    log(f"→ 🧾 Wrote {manifest_path} ({len(entries)} providers, {len(emitted)} sheets)")
    return manifest_path


def _require_file_ref(provider, index):
    """Returns the provider's validated texture resource location, or raises RuntimeError."""
    ref = provider.get("file")
    if not ref or not isinstance(ref, str):
        raise RuntimeError(f"Bitmap provider {index} has no file reference")
    try:
        split_resource_ref(ref)
    except ValueError as error:
        raise RuntimeError(f"Bitmap provider {index} has an invalid file reference '{ref}': {error}")
    return ref


def _require_metrics(provider, index):
    """Returns (height, ascent) with the default height made explicit, or raises RuntimeError.

    Mirrors the game's bitmap provider codec: height is optional (default 8)
    and must be positive, ascent is required and may not exceed height."""
    height = provider.get("height", DEFAULT_GLYPH_SIZE)
    if type(height) not in (int, float):
        raise RuntimeError(f"Bitmap provider {index} height {height!r} is not a number")
    if height <= 0:
        raise RuntimeError(f"Bitmap provider {index} height {height} is not positive")
    if "ascent" not in provider:
        raise RuntimeError(f"Bitmap provider {index} has no ascent")
    ascent = provider["ascent"]
    if type(ascent) not in (int, float):
        raise RuntimeError(f"Bitmap provider {index} ascent {ascent!r} is not a number")
    if ascent > height:
        raise RuntimeError(f"Bitmap provider {index} ascent {ascent} exceeds height {height}")
    return height, ascent


def _require_chars_rows(provider, index):
    """Returns the provider's verbatim chars rows, or raises RuntimeError."""
    rows = provider.get("chars")
    if not isinstance(rows, list) or not rows or any(not isinstance(row, str) for row in rows):
        raise RuntimeError(f"Bitmap provider {index} chars grid is not a non-empty list of strings")
    if not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise RuntimeError(f"Bitmap provider {index} chars rows are empty or have unequal lengths")
    return rows


def _copy_sheet(source, ref, sheets_dir, index):
    """Copies one sheet texture byte-identical into the sheets dir and returns its sha256 hex digest."""
    namespace, path = split_resource_ref(ref)
    data = source.get_texture(namespace, path)
    if data is None:
        raise RuntimeError(f"Bitmap provider {index} references sheet '{ref}', which is missing from the assets")

    dest = os.path.join(sheets_dir, namespace, *path.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)

    digest = hashlib.sha256(data).hexdigest()
    log(f"→ 📄 Copied {ref} ({len(data)} bytes, sha256 {digest[:12]}...)")
    return digest
