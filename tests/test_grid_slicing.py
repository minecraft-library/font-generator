from minecraft_fontgen.file_io import _trace_bitmap_contours2, slice_provider_tiles

from helpers import block, make_png_bytes

import numpy as np
import os


def _provider(png_bytes, chars_rows, columns, rows, height=7, ascent=7, name="p"):
    os.makedirs(f"work/glyphs/{name}", exist_ok=True)
    path = f"work/{name}.png"
    with open(path, "wb") as f:
        f.write(png_bytes)
    return {
        "ascent": ascent,
        "height": height,
        "rows": rows,
        "columns": columns,
        "chars": [char for row in chars_rows for char in row],
        "file_name": f"{name}.png",
        "file_path": path,
        "name": name,
        "output": f"work/glyphs/{name}",
        "layer": "skypack",
        "tiles": [],
    }


def test_skyblock_grid_slices_7px_tiles():
    png = make_png_bytes(56, 42, block(7, 7, 3, 4))
    chars = ["\x00" * 8, "\x00" + "\x00" * 6] + ["\x00" * 8] * 4
    provider = _provider(png, chars, columns=8, rows=6)

    slice_provider_tiles([provider])

    tile = provider["tiles"][0]
    assert tile["codepoint"] == 0xE001
    assert tile["size"] == (7, 7)
    assert tile["display_height"] == 7
    assert tile["layer"] == "skypack"
    assert tile["pixels"]["regular"]["width"] == 3
    assert tile["pixels"]["regular"]["empty"] is False


def test_single_cell_non_square_tile():
    png = make_png_bytes(3, 7, block(0, 0, 2, 7))
    provider = _provider(png, ["ዞ"], columns=1, rows=1, name="staff")

    slice_provider_tiles([provider])

    tile = provider["tiles"][0]
    assert tile["size"] == (3, 7)
    assert tile["pixels"]["regular"]["width"] == 2


def test_non_divisible_texture_warns(capsys):
    png = make_png_bytes(10, 8, block(0, 0, 2, 2))
    provider = _provider(png, ["ab\x00"], columns=3, rows=1, height=8)

    slice_provider_tiles([provider])

    assert "does not divide evenly" in capsys.readouterr().out


def test_grid_larger_than_texture_skips_provider(capsys):
    png = make_png_bytes(2, 7, block(0, 0, 2, 7))
    provider = _provider(png, ["abc"], columns=3, rows=1)

    slice_provider_tiles([provider])

    assert provider["tiles"] == []
    assert "smaller than" in capsys.readouterr().out


def test_missing_texture_skips_provider(capsys):
    provider = _provider(make_png_bytes(8, 8, []), ["a"], columns=1, rows=1)
    os.remove(provider["file_path"])

    slice_provider_tiles([provider])

    assert provider["tiles"] == []
    assert "missing" in capsys.readouterr().out


def test_trace_marks_empty_tiles():
    assert _trace_bitmap_contours2(np.zeros((7, 3), dtype=np.uint8))["empty"] is True
    grid = np.zeros((7, 3), dtype=np.uint8)
    grid[0, 0] = 1
    assert _trace_bitmap_contours2(grid)["empty"] is False
