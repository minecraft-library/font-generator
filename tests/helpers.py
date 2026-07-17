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


def build_color_font_storage(tiles):
    """Assembles the single merged colour TrueType font from raster tile dicts and
    returns the finalized GlyphStorage. Mirrors create_color_font_files: every
    (font_id, codepoint) pair is assigned a stored codepoint from plane 15/16 before
    the tile is added, so the storage's cmap keys on stored codepoints exactly as the
    real single-file compiler does."""
    from fontTools.ttLib import TTFont

    from minecraft_fontgen.table.header import create_font_header_table
    from minecraft_fontgen.table.horizontal_header import create_font_hheader_table
    from minecraft_fontgen.table.maximum_profile import create_font_mprofile_table
    from minecraft_fontgen.table.postscript import create_font_pscript_table
    from minecraft_fontgen.table.horizontal_metrics import create_font_hmetrics_table
    from minecraft_fontgen.table.name import create_font_name_table
    from minecraft_fontgen.table.os2_metrics import create_font_metrics_table
    from minecraft_fontgen.table.glyph_mappings import create_font_mapping_table
    from minecraft_fontgen.table.truetype import create_tt_font_tables
    from minecraft_fontgen.glyph.glyph_storage import GlyphStorage
    from minecraft_fontgen.stored_codepoint import allocate_stored_codepoints

    font = TTFont()
    create_font_header_table(font, use_cff=False)
    create_font_hheader_table(font, use_cff=False)
    create_font_mprofile_table(font, use_cff=False)
    create_font_pscript_table(font, use_cff=False)
    create_font_hmetrics_table(font)
    create_font_name_table(font, False, False)
    create_font_metrics_table(font)
    create_font_mapping_table(font)
    create_tt_font_tables(font)

    stored_by_pair = allocate_stored_codepoints(
        (tile["font_id"], tile["codepoint"]) for tile in tiles)

    storage = GlyphStorage(font, use_cff=False, color_mode=True)
    for tile in tiles:
        tile = dict(tile)
        tile["stored_codepoint"] = stored_by_pair[(tile["font_id"], tile["codepoint"])]
        storage.add(storage.create_glyph(tile))
    storage.add_notdef()
    storage.finalize()
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


def make_color_png_bytes(width, height, colored_pixels):
    """PNG bytes of a transparent RGBA canvas with {(x, y): (r, g, b, a)} painted.

    Unlike make_png_bytes it splices no tEXt marker: colour cells are re-encoded
    crops verified by pixel-equality, not byte-identity, so a synthetic marker
    would only pollute the ancillary-chunk assertions."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for (x, y), rgba in colored_pixels.items():
        img.putpixel((x, y), rgba)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def two_color_block_png(width, height, left=(220, 40, 40, 255), right=(40, 60, 220, 255)):
    """PNG bytes of an opaque cell split into two vertical colour bands (raster icon)."""
    return make_color_png_bytes(width, height, {
        (x, y): (left if x < width // 2 else right)
        for x in range(width) for y in range(height)
    })


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
