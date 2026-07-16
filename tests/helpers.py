import io
import json
import os
import struct
import zipfile
import zlib

from PIL import Image

# Spliced into every fixture PNG so a PIL decode + re-save cannot reproduce the
# original bytes (PIL drops text chunks unless pnginfo is passed explicitly).
# Byte-identity assertions against these fixtures therefore catch any code path
# that re-encodes an image where it should copy the source bytes unchanged.
_PNG_MARKER_CHUNK_DATA = b"Comment\x00fixture marker: a PIL re-save must not reproduce these bytes"


def make_png_bytes(width, height, pixels, color=(255, 255, 255, 255)):
    """Builds PNG bytes: a transparent canvas with the given pixels set to color.

    The bytes carry a tEXt marker chunk that does not survive a PIL decode +
    re-save, so they are safe to use in byte-identity assertions."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for x, y in pixels:
        img.putpixel((x, y), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return _splice_marker_chunk(buf.getvalue())


def _splice_marker_chunk(png_bytes):
    """Inserts the tEXt marker chunk directly after the IHDR chunk."""
    chunk = (struct.pack(">I", len(_PNG_MARKER_CHUNK_DATA)) + b"tEXt" + _PNG_MARKER_CHUNK_DATA
             + struct.pack(">I", zlib.crc32(b"tEXt" + _PNG_MARKER_CHUNK_DATA)))
    ihdr_end = 8 + 4 + 4 + 13 + 4  # signature + IHDR length/type/data/crc
    return png_bytes[:ihdr_end] + chunk + png_bytes[ihdr_end:]


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
