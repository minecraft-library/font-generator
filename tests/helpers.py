import io
import json
import os
import zipfile

from PIL import Image


def make_png_bytes(width, height, pixels, color=(255, 255, 255, 255)):
    """Builds PNG bytes: a transparent canvas with the given pixels set to color."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for x, y in pixels:
        img.putpixel((x, y), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def block(x0, y0, w, h):
    """Returns pixel coordinates of a filled w x h rectangle at (x0, y0)."""
    return [(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)]


def font_json_bytes(providers):
    return json.dumps({"providers": providers}).encode("utf-8")


def write_pack_dir(root, files):
    """Writes {relative/path: bytes} under root, creating directories. Returns str(root)."""
    for rel, data in files.items():
        dest = os.path.join(str(root), *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
    return str(root)


def write_pack_zip(zip_path, files, root_prefix=""):
    """Writes {relative/path: bytes} into a zip, optionally under a nested root folder."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for rel, data in files.items():
            zf.writestr(root_prefix + rel, data)
    return str(zip_path)


class FakeSource:
    """Dict-backed AssetSource stand-in for unit tests."""

    def __init__(self, name, fonts=None, textures=None, vanilla=False):
        self.name = name
        self.fonts = fonts or {}
        self.textures = textures or {}
        self.is_vanilla = vanilla
        self.closed = False

    @property
    def pack_id(self):
        return self.name

    def get_font_json(self, font_id):
        return self.fonts.get(font_id)

    def get_texture(self, namespace, path):
        return self.textures.get(f"{namespace}:{path}")

    def list_font_ids(self):
        return list(self.fonts)

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# colour-glyph (sbix) test infrastructure
# ---------------------------------------------------------------------------

def color_cell(width, height, pixels, base=(0, 0, 0, 0)):
    """RGBA PIL image on a `base` canvas with {(x, y): (r, g, b, a)} painted."""
    img = Image.new("RGBA", (width, height), base)
    for (x, y), rgba in pixels.items():
        img.putpixel((x, y), rgba)
    return img


def flat_two_color_cell(width, height, left=(220, 40, 40, 255), right=(40, 60, 220, 255)):
    """Opaque cell split into two vertical colour bands (a classic raster icon)."""
    img = Image.new("RGBA", (width, height), left)
    for x in range(width // 2, width):
        for y in range(height):
            img.putpixel((x, y), right)
    return img


def make_raster_tile(codepoint, cell, display_height, ascent, font_id="test:demo"):
    """Builds a raster tile dict shaped exactly like slice_provider_tiles emits one,
    encoding + hashing the cell through the real file_io helpers."""
    from minecraft_fontgen.file_io import encode_cell_png, raster_cell_hash

    width, height = cell.size
    return {
        "unicode": chr(codepoint),
        "codepoint": codepoint,
        "size": (width, height),
        "display_height": display_height,
        "ascent": ascent,
        "font_id": font_id,
        "location": (0, 0),
        "render_mode": "raster",
        "raster_png": encode_cell_png(cell),
        "content_hash": raster_cell_hash(cell),
        "raster_size": (width, height),
    }


def color_font_spec(color_map, space_rows=None, namespace="Testpack", pack_id="testpack"):
    """Builds one colour font spec shaped exactly as file_io.collect_color_fonts emits,
    for create_font_files to consume alongside (or instead of) the mono styles."""
    return {
        "name": namespace,
        "enabled": True,
        "color": True,
        "bold": False,
        "italic": False,
        "pack_id": pack_id,
        "family_qualifier": namespace,
        "color_map": color_map,
        "space_rows": space_rows or {},
    }


def build_one_color_font(color_map, space_rows, outdir, font_name="Minecraft",
                         namespace="Testpack"):
    """Compiles a single pack's merged colour font through the real create_font_files
    loop (no mono styles) and returns (color_file, storage). This is the shared path
    the colour-compile tests drive, so they exercise the same code main() runs."""
    from minecraft_fontgen.font_creator import create_font_files

    spec = color_font_spec(color_map, space_rows, namespace=namespace)
    _, color_results = create_font_files({}, False, [], str(outdir), font_name, "ttf",
                                         color_fonts=[spec])
    _, color_file, storage = color_results[0]
    return color_file, storage


def build_color_font_storage(tiles):
    """Assembles one pack's merged colour TrueType font from raster tile dicts and
    returns the finalized GlyphStorage. Groups the tiles into a per-font-id colour map
    and drives the real create_font_files loop, so stored codepoints are allocated over
    the (font_id, codepoint) pairs exactly as the production compiler does."""
    import os
    import tempfile
    from collections import OrderedDict

    from minecraft_fontgen.file_io import build_color_glyph_map

    color_map = build_color_glyph_map([{"tiles": list(tiles)}])
    with tempfile.TemporaryDirectory() as tmp:
        _, storage = build_one_color_font(color_map, {}, tmp)
    return storage


def stored_cp_for(storage, codepoint, font_id="test:demo"):
    """Returns the stored codepoint the merged font assigned to an original
    (font_id, codepoint) raster pair, read back from the storage's sidecar rows."""
    for row in storage.sidecar_rows:
        if row["codepoint"] == codepoint and row["font_id"] == font_id:
            return row["stored_codepoint"]
    raise KeyError((font_id, codepoint))


def glyph_name_for(storage, codepoint, font_id="test:demo"):
    """Returns the compiled glyph name for an original (font_id, codepoint) raster
    pair. The merged font's cmap keys on stored codepoints, so tests resolve the
    strike by name through the sidecar row rather than getBestCmap()[original_cp]."""
    for row in storage.sidecar_rows:
        if row["codepoint"] == codepoint and row["font_id"] == font_id:
            return row["glyphName"]
    raise KeyError((font_id, codepoint))


def compiled_font_bytes(storage):
    """Compiles a finalized storage's font to bytes and returns them."""
    buf = io.BytesIO()
    storage.font.save(buf)
    return buf.getvalue()


def _encode_png(img):
    """PNG bytes of a PIL image with no spliced tEXt marker: colour cells are re-encoded
    crops verified by pixel-equality, not byte-identity, so a synthetic marker would only
    pollute the ancillary-chunk assertions."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_color_png_bytes(width, height, colored_pixels):
    """PNG bytes of a transparent RGBA canvas with {(x, y): (r, g, b, a)} painted."""
    return _encode_png(color_cell(width, height, colored_pixels))


def two_color_block_png(width, height, left=(220, 40, 40, 255), right=(40, 60, 220, 255)):
    """PNG bytes of an opaque cell split into two vertical colour bands (raster icon)."""
    return _encode_png(flat_two_color_cell(width, height, left=left, right=right))


def color_pack_source(font_id, cells, space_advances=None,
                      name="colorpack", height=8, ascent=7):
    """A FakeSource carrying one colour font file: a single-cell bitmap provider per
    (texture_ref -> (char, png_bytes)) entry plus an optional space provider.
    Everything is synthetic - no real pack assets."""
    providers = []
    textures = {}
    for ref, (char, png) in cells.items():
        providers.append({"type": "bitmap", "file": ref, "ascent": ascent,
                          "height": height, "chars": [char]})
        textures[ref] = png
    if space_advances:
        providers.append({"type": "space", "advances": space_advances})
    return FakeSource(name, fonts={font_id: font_json_bytes(providers)}, textures=textures)
