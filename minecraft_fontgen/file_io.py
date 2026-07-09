import math
import os
import shutil
import sys
import numpy as np

from collections import defaultdict, deque, OrderedDict
from tqdm import tqdm
from PIL import Image
from minecraft_fontgen.asset_source import AssetStack, VanillaSource, split_resource_ref
from minecraft_fontgen.config import ALT_FONT_IDS, ASCENT, BOLD_PACK_GLYPHS, DEFAULT_GLYPH_SIZE, INK_ALPHA_THRESHOLD, OUTPUT_DIR, MINECRAFT_JAR_DIR, PACK_FONT_IDS, WORK_DIR, UNITS_PER_EM, TEXTURE_PATH, FONT_STYLES
from minecraft_fontgen.functions import get_unicode_codepoint, in_unifont_ranges, log, is_silent, parse_json, sanitize_fs_name


# ==========================================
# === Stage 1: Clean work/output directories
# ==========================================

def clean_directories(output_dir=None):
    """Removes and recreates the work/ and output/ directories."""
    if output_dir is None:
        output_dir = OUTPUT_DIR

    log("🧹 Cleaning work directory...")
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    os.makedirs(WORK_DIR, exist_ok=True)

    log("🧹 Cleaning output directory...")
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)


# ==========================================
# === Stage 2: Parse providers + slice tiles
# ==========================================

def parse_provider_file(file, format, stack=None):
    """Reads a font provider file, parses it by format, and slices into glyph tiles."""
    log(f"🧩 Parsing {file}...")
    with open(file, "rb") as f:
        raw_bytes = f.read()

    log(f"→ 🛠️ Decoding {format}...")
    if format == "bin":
        providers = parse_bin_providers(raw_bytes)
    elif format == "json":
        providers = parse_json_providers(raw_bytes, stack)
    else:
        raise ValueError(f"Unsupported file format: {format}")

    slice_provider_tiles(providers)
    return providers


def collect_pack_providers(stack):
    """Parses and slices the default-font providers contributed by resource packs.

    The returned list is ordered so that appending it after the vanilla
    providers reproduces the game's priority under build_glyph_map's last-wins
    merge: later packs beat earlier packs, every pack beats vanilla, a pack's
    default.json beats its include/default.json, and within one file the
    first-listed provider wins."""
    providers = []
    for font_id in PACK_FONT_IDS:
        for source in stack.pack_sources():
            raw = source.get_font_json(font_id)
            if raw is None:
                continue
            try:
                layer = parse_json_providers(raw, stack, layer_name=source.name)
            except (ValueError, AttributeError) as error:
                log(f" → ⚠️ Skipping malformed font JSON '{font_id}' in pack '{source.name}': {error}")
                continue
            layer.reverse()  # the game walks a font's providers first-wins; the merge is last-wins
            providers += layer

    if providers:
        slice_provider_tiles(providers)

    for source in stack.pack_sources():
        for font_id in source.list_font_ids():
            if font_id not in PACK_FONT_IDS and font_id not in ALT_FONT_IDS:
                log(f"→ ⚠️ Pack '{source.name}' defines font '{font_id}', which this tool does not build")

    return providers

def parse_bin_providers(byte_data):
    """Parses legacy binary glyph_sizes.bin format (Minecraft 1.8.9 and earlier).

    Scans for ascii.png (8x8 glyphs) and unicode_page_XX.png (16x16 glyphs)
    in the extracted font textures directory. Creates provider dicts compatible
    with the JSON provider pipeline.
    """
    glyph_widths = list(byte_data)
    providers = []

    glyph_count = sum(1 for w in glyph_widths if w != 0)
    log(f"→ 🛠️ Parsing bitmap providers ({glyph_count} non-empty in glyph_sizes.bin)...")

    # 1. Discover unicode_page_XX.png files (16x16 glyphs, 256 chars per page)
    #    Added first so ascii.png can override codepoints 0-255
    with tqdm(range(256), desc=" → 🔢 Pages", unit="page",
              ncols=80, leave=False, file=sys.stdout, disable=is_silent()) as pages_progress:
        for page in pages_progress:
            page_hex = f"{page:02x}"
            pages_progress.set_description(f" → 🔢 Page {page_hex}")
            page_file = f"unicode_page_{page_hex}.png"
            page_path = f"{TEXTURE_PATH}/{page_file}"

            if not os.path.isfile(page_path):
                continue

            base_cp = page * 256
            chars = []
            for i in range(256):
                cp = base_cp + i
                if cp < len(glyph_widths) and glyph_widths[cp] != 0 and in_unifont_ranges(cp):
                    chars.append(chr(cp))
                else:
                    chars.append(chr(0))

            valid_count = sum(1 for c in chars if c != chr(0))
            if valid_count == 0:
                continue

            name = f"unicode_page_{page_hex}"
            output = f"{WORK_DIR}/glyphs/{name}"
            os.makedirs(output, exist_ok=True)

            providers.append({
                "ascent": 15,
                "height": 16,
                "rows": 16,
                "columns": 16,
                "layer": "vanilla",
                "chars": chars,
                "file_name": page_file,
                "file_path": page_path,
                "name": name,
                "output": output,
                "tiles": []
            })

    unicode_glyph_count = sum(sum(1 for c in p["chars"] if c != chr(0)) for p in providers)
    log(f" → 🔢 Detected {unicode_glyph_count} glyphs across {len(providers)} unicode pages...")

    # 2. ascii.png (8x8 glyphs, codepoints 0-255)
    #    Added last so it takes priority over unicode_page_00 for overlapping codepoints
    name = "ascii"
    ascii_file = f"{name}.png"
    ascii_path = f"{TEXTURE_PATH}/{ascii_file}"

    if os.path.isfile(ascii_path):
        chars = [chr(i) for i in range(256)]
        name = "ascii"
        output = f"{WORK_DIR}/glyphs/{name}"
        os.makedirs(output, exist_ok=True)

        log(f" → 🔢 Detected 256 glyphs in {ascii_file}...")

        providers.append({
            "ascent": 7,
            "height": 8,
            "rows": 16,
            "columns": 16,
            "layer": "vanilla",
            "chars": chars,
            "file_name": ascii_file,
            "file_path": ascii_path,
            "name": name,
            "output": output,
            "tiles": []
        })

    return providers

def parse_json_providers(byte_data, stack=None, layer_name="vanilla"):
    """Parses the JSON font provider format into a list of provider dicts.

    Texture references resolve through the asset stack, so resource packs can
    override vanilla textures and reference their own namespaces."""
    if stack is None:
        stack = AssetStack([VanillaSource()])
    raw_text = byte_data.decode("utf-8", errors="surrogatepass").lstrip("\ufeff")
    data = parse_json(raw_text)

    log(f"→ 🛠️ Parsing bitmap providers ({layer_name})...")
    providers = []
    for index, provider in enumerate(data.get("providers", [])):
        provider_type = provider.get("type")
        if provider_type != "bitmap":
            log(f" → ⚠️ Skipping unsupported '{provider_type}' provider in {layer_name} (only bitmap providers are converted)")
            continue

        rows = provider.get("chars", [])
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (chars grid is not a list of strings)")
            continue
        if not rows or not rows[0]:
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (no chars grid)")
            continue
        if any(len(row) != len(rows[0]) for row in rows):
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (chars rows have unequal lengths)")
            continue

        if "height" in provider and type(provider["height"]) not in (int, float):
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (height {provider['height']} is not a number)")
            continue
        height = provider.get("height", DEFAULT_GLYPH_SIZE)
        if height <= 0:
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (height {height} is not positive)")
            continue
        if "ascent" in provider and type(provider["ascent"]) not in (int, float):
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (ascent {provider['ascent']} is not a number)")
            continue
        if "ascent" not in provider:
            log(f" → ⚠️ Bitmap provider {index} in {layer_name} has no ascent, defaulting to 0")
        ascent = provider.get("ascent", 0)
        if ascent > height:
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (ascent {ascent} exceeds height {height})")
            continue

        ref = provider.get("file")
        if not ref:
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (no file reference)")
            continue
        file_path = stack.materialize_texture(ref)
        if file_path is None:
            log(f" → ⚠️ Skipping bitmap provider {index} in {layer_name} (texture '{ref}' not found in any layer)")
            continue

        namespace, rel_path = split_resource_ref(ref)
        name = sanitize_fs_name(f"{layer_name}_{namespace}_{os.path.splitext(rel_path)[0]}_{index}")
        output = f"{WORK_DIR}/glyphs/{name}"
        os.makedirs(output, exist_ok=True)

        chars = [char for row in rows for char in row]
        log(f" → 🔢 Detected {len(chars)} unicode characters in '{name}'...")

        providers.append({
            "ascent": ascent,
            "height": height,
            "rows": len(rows),
            "columns": len(rows[0]),
            "chars": chars,
            "file_name": ref,
            "file_path": file_path,
            "name": name,
            "output": output,
            "layer": layer_name,
            "tiles": []
        })

    return providers

def slice_provider_tiles(providers):
    """Slices each provider's bitmap PNG into individual glyph tiles with contour and SVG data."""
    log(f"→ ✂️ Slicing bitmap providers into tiles...")

    debug_svg_regular = any(s.get("debug", {}).get("svg") for s in FONT_STYLES if s["pixel_style"] == "Regular")
    debug_svg_bold = any(s.get("debug", {}).get("svg") for s in FONT_STYLES if s["pixel_style"] == "Bold")
    debug_svg = debug_svg_regular or debug_svg_bold
    debug_bmp = any(s.get("debug", {}).get("bmp") for s in FONT_STYLES)

    for provider in providers:
        bitmap = binarize_provider_bitmap(provider)
        if bitmap is None:
            log(f" → ⚠️ Skipping '{provider['name']}' (texture missing: {provider['file_path']})")
            provider["tiles"] = []
            continue
        tiles = []

        # Calculate tile dimensions from the chars grid (the game divides the
        # texture evenly by the grid; the JSON height field is display scaling)
        width, height = bitmap.size
        columns = provider["columns"]
        rows = provider["rows"]
        glyph_width = width // columns
        tile_px_height = height // rows
        if glyph_width == 0 or tile_px_height == 0:
            log(f" → ⚠️ Skipping '{provider['name']}' (texture {width}x{height} is smaller than its {columns}x{rows} chars grid)")
            provider["tiles"] = []
            continue
        if width % columns or height % rows:
            log(f" → ⚠️ '{provider['name']}': texture {width}x{height} does not divide evenly into a {columns}x{rows} grid")

        with tqdm(enumerate(provider["chars"]), total=len(provider["chars"]),
                  desc=f" → 🔣 {provider['file_name']}", unit="tile",
                  ncols=80, leave=False, file=sys.stdout, disable=is_silent()) as tiles_progress:
            for i, unicode in tiles_progress:
                # Skip .notdef
                codepoint = get_unicode_codepoint(unicode)
                if codepoint == 0x0000:
                    continue

                # Update progress bar
                tiles_progress.set_description(f" → 🔣 0x{codepoint:02X}")

                # Collate tile data
                tile_row = i // columns
                tile_column = i % columns
                tile = {
                    "unicode": unicode,
                    "codepoint": codepoint,
                    "size": (glyph_width, tile_px_height),
                    "display_height": provider["height"],
                    "ascent": provider.get("ascent", 0),
                    "layer": provider.get("layer", "vanilla"),
                    "location": (tile_column, tile_row),
                    "output": f"{provider['output']}/tiles/{tile_row:02}_{tile_column:02}_{codepoint:04X}"
                }
                tiles.append(tile)

                # Crop tile bitmap from full bitmap
                tile["bitmap"] = crop_tile(bitmap, tile, save=debug_bmp)

                # Trace contours for regular and bold styles
                tile["pixels"] = trace_tile_contours(tile)

                # Create svg debug output
                tile["svg"] = None
                if debug_svg:
                    if not debug_bmp:
                        os.makedirs(tile["output"], exist_ok=True)
                    svg = {}
                    if debug_svg_regular:
                        svg["regular"] = _write_tile_svg(tile["pixels"]["regular"]["grid"], tile["size"], f"{tile['output']}/regular.svg")
                    if debug_svg_bold:
                        svg["bold"] = _write_tile_svg(tile["pixels"]["bold"]["grid"], tile["size"], f"{tile['output']}/bold.svg")
                    tile["svg"] = svg

        provider["tiles"] = tiles

    total_tiles = sum(len(p["tiles"]) for p in providers)
    log(f" → 🔢 Sliced {total_tiles} glyphs across {len(providers)} providers...")

def binarize_provider_bitmap(provider):
    """Reads a provider PNG and binarizes it to black ink on white.

    Coverage follows the game's rule: a pixel is part of the glyph when its
    alpha exceeds INK_ALPHA_THRESHOLD. Images with no transparency at all fall
    back to the legacy luminance threshold. Returns None when the texture file
    is missing."""
    if not os.path.isfile(provider["file_path"]):
        return None
    img = Image.open(provider["file_path"]).convert("RGBA")

    alpha = img.getchannel("A")
    if alpha.getextrema() == (255, 255):
        bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
        flat = Image.alpha_composite(bg, img).convert("L")
        flat = Image.eval(flat, lambda x: 255 - x)
        binary = flat.point(lambda x: 0 if x < 128 else 255, '1')
    else:
        binary = alpha.point(lambda a: 0 if a > INK_ALPHA_THRESHOLD else 255, '1')

    # Copy original and save grayscale
    output_file = provider["output"] + "/" + provider["name"]
    shutil.copyfile(provider["file_path"], output_file + ".png")
    binary.save(f"{output_file}_grayscale.png")

    return binary

def crop_tile(bitmap, tile, save=True):
    """Crops a single glyph tile from a full provider bitmap and optionally saves it to disk."""
    x, y = tile["location"]
    width, height = tile["size"]
    glyph_width = int(width)
    px, py = (x * glyph_width, y * height)

    bitmap = {
        "image": bitmap.crop((px, py, px + glyph_width, py + height)),
        "file": f"{tile['output']}/glyph.bmp"
    }

    if save:
        os.makedirs(tile["output"], exist_ok=True)
        bitmap["image"].save(bitmap["file"])
    return bitmap

def trace_tile_contours(tile):
    """Traces contours from a tile's bitmap for both regular and bold styles."""
    return {
        "regular": _trace_tile_style(tile, False),
        "bold": _trace_tile_style(tile, True)
    }

def _trace_tile_style(tile, bold: bool = False):
    """Converts a tile's PIL bitmap image to a binary numpy grid and traces its contours."""
    bitmap_grid = np.array(tile["bitmap"]["image"].convert("L"), dtype=int)
    bitmap_grid = (bitmap_grid < 128).astype(np.uint8)
    return _trace_bitmap_contours2(bitmap_grid, bold)

def _trace_bitmap_contours(bitmap_grid, bold: bool = False):
    """Traces contours from a binary bitmap grid using flood-fill labeling and right-hand edge
    tracing. Returns contour data with labeled grid, path corners, hole corners, advance width,
    and left side bearing for font glyph construction.
    """
    height, width = bitmap_grid.shape
    pixel_grid = np.full((height, width), -999, dtype=int) # Create empty grid

    if bold: # iterate from bottom to top, right to left
        for i in range(bitmap_grid.shape[0] - 1, -1, -1):
            for j in range(bitmap_grid.shape[1] - 1, -1, -1):
                if bitmap_grid[i, j] == 1 and j + 1 < bitmap_grid.shape[1] and bitmap_grid[i, j + 1] == 0:
                    bitmap_grid[i, j + 1] = 1 # copy 1 to the right

    def update_grid(queue, bit_match, next_label, neighbours = None):
        while queue:
            cy, cx = queue.popleft()

            # Ensure the current pixel is labeled
            if pixel_grid[cy, cx] == -999:
                pixel_grid[cy, cx] = next_label

            for dy, dx in neighbours or [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = cy + dy, cx + dx

                if 0 <= ny < height and 0 <= nx < width:
                    if bitmap_grid[ny, nx] == bit_match and pixel_grid[ny, nx] == -999:
                        pixel_grid[ny, nx] = next_label
                        queue.append((ny, nx))

    def label_groups(bit_match, increment, neighbours = None):
        next_label = 0 + increment
        labels = []

        for y in range(height):
            for x in range(width):
                if bitmap_grid[y, x] == bit_match and pixel_grid[y, x] == -999:
                    q = deque()
                    q.append((y, x))
                    pixel_grid[y, x] = next_label
                    labels.append(next_label)
                    update_grid(q, bit_match, next_label, neighbours)
                    next_label += increment

        return labels

    # Label glyph groups as 1 and above
    path_labels = label_groups(1, 1, [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)])

    # Flood-fill outer background as 0
    q = deque()
    for x in range(width):
        if bitmap_grid[0, x] == 0: q.append((0, x))
        if bitmap_grid[height - 1, x] == 0: q.append((height - 1, x))
    for y in range(height):
        if bitmap_grid[y, 0] == 0: q.append((y, 0))
        if bitmap_grid[y, width - 1] == 0: q.append((y, width - 1))
    update_grid(q, 0, 0)

    hole_labels = label_groups(0, -1)

    def trace_pixel_edge_turns(pixel_grid, label):
        # Get all (x, y) tile coords for the hole
        coords = [tuple([x, y]) for y, x in np.argwhere(pixel_grid == label)]
        black_set = set(coords)

        def is_valid_pixel(x, y):
            return (x, y) in black_set

        # Get edge segments around each black pixel
        def get_edges(x, y):
            # edges are (from, to) pairs going clockwise around a square
            return [((x, y), (x+1, y)),
                    ((x+1, y), (x+1, y+1)),
                    ((x+1, y+1), (x, y+1)),
                    ((x, y+1), (x, y))]

        edge_count = {}
        for x, y in black_set:
            if not is_valid_pixel(x, y):
                continue
            for edge in get_edges(x, y):
                if edge[::-1] in edge_count:
                    edge_count[edge[::-1]] -= 1
                else:
                    edge_count[edge] = edge_count.get(edge, 0) + 1

        # Only keep boundary edges (ones not shared by two valid pixels)
        boundary_edges = {e for e, count in edge_count.items() if count > 0}
        if not boundary_edges:
            return {"coords": coords, "corners": []}

        # Start from the top-left most edge
        start_edge = min(boundary_edges, key=lambda e: (e[0][1], e[0][0]))
        path = [] # [start_edge[0]]
        current_edge = start_edge
        visited = set()

        # Right-hand rule
        def direction(a, b): return b[0] - a[0], b[1] - a[1]
        def rotate_right(d): return d[1], -d[0]
        def rotate_left(d): return -d[1], d[0]

        while True:
            a, b = current_edge
            dir = direction(a, b)
            found = False
            for turn in [rotate_right, lambda d: d, rotate_left]:
                ndir = turn(dir)
                next_point = (b[0] + ndir[0], b[1] + ndir[1])
                next_edge = (b, next_point)
                if next_edge in boundary_edges and next_edge not in visited:
                    path.append(b)
                    visited.add(next_edge)
                    current_edge = next_edge
                    found = True
                    break
            if not found or current_edge == start_edge:
                break

        return path

    def extract_corners_from_path(path):
        def direction(a, b):
            return b[0] - a[0], b[1] - a[1]

        corners = []
        n = len(path)

        if n < 3:
            return path.copy()  # fallback

        for i in range(len(path)):
            prev = path[(i - 1) % n]
            curr = path[i]
            next = path[(i + 1) % n]
            dir1 = direction(prev, curr)
            dir2 = direction(curr, next)
            if dir1 != dir2:
                corners.append(curr)

        return corners

    def get_path_data(pixel_grid, label):
        coords = trace_pixel_edge_turns(pixel_grid, label)
        return {
            "coords": coords,
            "corners": extract_corners_from_path(coords)
        }

    # Determine glyph sides
    col_sums = pixel_grid.sum(axis=0) # Sum each column to see where 1's exist
    col_ones = np.where(col_sums > 0)[0] # Find indices where there is at least one 1 in that column
    min_x = col_ones[0] if len(col_ones) > 0 else 0
    max_x = col_ones[-1] if len(col_ones) > 0 else DEFAULT_GLYPH_SIZE - 1
    width = col_ones[-1] - col_ones[0] + 1 if len(col_ones) > 0 else DEFAULT_GLYPH_SIZE

    return {
        "bitmap": bitmap_grid,
        "grid": pixel_grid,
        "width": (max_x - min_x + 1),
        "lsb": min_x,
        "advance": (min_x + width + 1),
        "paths": {label: get_path_data(pixel_grid, label) for label in path_labels},
        "holes": {label: get_path_data(pixel_grid, label) for label in hole_labels}
    }

def _trace_bitmap_contours2(bitmap_grid, bold: bool = False):
    """Traces contours from a binary bitmap grid using flood-fill labeling and multi-loop
    boundary-edge extraction. Unlike _trace_bitmap_contours which uses a single right-hand
    rule traversal per label (capturing only one loop), this function collects ALL boundary
    edges for each labeled region and extracts every closed loop, correctly handling
    regions with complex internal topology (e.g. U+26C3 chess rook where battlements
    create disconnected boundary loops that a single traversal misses).

    For labels whose boundary edges form multiple disconnected loops, the largest-area
    loop is kept as the primary contour for that label. The smaller sub-loops represent
    islands of the opposite type (filled islands inside holes, or hole islands inside
    filled regions) and are redistributed to the opposite dict (paths or holes) so that
    downstream even-odd nesting depth logic correctly determines fill.

    Returns contour data with labeled grid, path corners, hole corners, advance width,
    and left side bearing for font glyph construction. The return format matches
    _trace_bitmap_contours: paths and holes dicts map integer keys to dicts with
    "coords" (full-edge vertex loop) and "corners" (direction-change vertices only).
    """
    height, width = bitmap_grid.shape
    pixel_grid = np.full((height, width), -999, dtype=int)

    if bold:
        for i in range(bitmap_grid.shape[0] - 1, -1, -1):
            for j in range(bitmap_grid.shape[1] - 1, -1, -1):
                if bitmap_grid[i, j] == 1 and j + 1 < bitmap_grid.shape[1] and bitmap_grid[i, j + 1] == 0:
                    bitmap_grid[i, j + 1] = 1

    def update_grid(queue, bit_match, next_label, neighbours=None):
        while queue:
            cy, cx = queue.popleft()
            if pixel_grid[cy, cx] == -999:
                pixel_grid[cy, cx] = next_label
            for dy, dx in neighbours or [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < height and 0 <= nx < width:
                    if bitmap_grid[ny, nx] == bit_match and pixel_grid[ny, nx] == -999:
                        pixel_grid[ny, nx] = next_label
                        queue.append((ny, nx))

    def label_groups(bit_match, increment, neighbours=None):
        next_label = 0 + increment
        labels = []
        for y in range(height):
            for x in range(width):
                if bitmap_grid[y, x] == bit_match and pixel_grid[y, x] == -999:
                    q = deque()
                    q.append((y, x))
                    pixel_grid[y, x] = next_label
                    labels.append(next_label)
                    update_grid(q, bit_match, next_label, neighbours)
                    next_label += increment
        return labels

    # Label glyph groups as 1 and above (8-connectivity)
    path_labels = label_groups(1, 1, [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)])

    # Flood-fill outer background as 0
    q = deque()
    for x in range(width):
        if bitmap_grid[0, x] == 0: q.append((0, x))
        if bitmap_grid[height - 1, x] == 0: q.append((height - 1, x))
    for y in range(height):
        if bitmap_grid[y, 0] == 0: q.append((y, 0))
        if bitmap_grid[y, width - 1] == 0: q.append((y, width - 1))
    update_grid(q, 0, 0)

    # Label interior holes as -1 and below (4-connectivity)
    hole_labels = label_groups(0, -1)

    def _get_boundary_edges(pixel_grid, label):
        """Collects all CW-directed boundary edges for a labeled region.

        Each pixel contributes 4 edges going CW around its square. Edges shared
        by two same-label pixels cancel out, leaving only boundary edges.
        Returns pixel coords list and the set of directed boundary edges.
        """
        coords = [(int(x), int(y)) for y, x in np.argwhere(pixel_grid == label)]
        label_set = set(coords)

        def pixel_edges(x, y):
            return [((x, y), (x + 1, y)),
                    ((x + 1, y), (x + 1, y + 1)),
                    ((x + 1, y + 1), (x, y + 1)),
                    ((x, y + 1), (x, y))]

        edge_count = {}
        for x, y in label_set:
            for edge in pixel_edges(x, y):
                rev = edge[::-1]
                if rev in edge_count:
                    edge_count[rev] -= 1
                else:
                    edge_count[edge] = edge_count.get(edge, 0) + 1

        boundary = {e for e, count in edge_count.items() if count > 0}
        return coords, boundary

    def _extract_all_loops(boundary_edges):
        """Extracts ALL closed loops from the set of CW boundary edges.

        Builds an adjacency map from edge endpoints, then repeatedly picks an
        unvisited edge and traces a loop by always taking the tightest CW turn
        at each vertex (smallest clockwise angle from the reverse of the arrival
        direction).

        Only the original CW boundary edges are used (no CCW reverse edges).
        Returns a list of loops, where each loop is a list of vertex coordinates.
        """
        if not boundary_edges:
            return []

        # Build adjacency: vertex -> set of outgoing edge endpoints
        adj = defaultdict(set)
        for (a, b) in boundary_edges:
            adj[a].add(b)

        remaining = set(boundary_edges)
        loops = []

        while remaining:
            # Pick the topmost-leftmost starting edge for determinism
            start_edge = min(remaining, key=lambda e: (e[0][1], e[0][0]))
            loop = [start_edge[0]]
            prev, curr = start_edge
            remaining.discard(start_edge)

            for _ in range(len(boundary_edges) + 1):
                loop.append(curr)

                # Compute arrival direction (reversed) to measure CW turns from
                arrival_dx = curr[0] - prev[0]
                arrival_dy = curr[1] - prev[1]
                reverse_angle = math.atan2(-(-arrival_dy), -arrival_dx)

                # Find all outgoing edges from curr that are still in remaining
                candidates = [n for n in adj[curr] if (curr, n) in remaining]

                if not candidates:
                    break

                # Pick the tightest CW turn: smallest positive angle difference
                # from reverse_angle going clockwise
                best = None
                best_diff = None
                for n in candidates:
                    dx = n[0] - curr[0]
                    dy = n[1] - curr[1]
                    out_angle = math.atan2(-dy, dx)
                    diff = reverse_angle - out_angle
                    while diff <= 0:
                        diff += 2 * math.pi
                    while diff > 2 * math.pi:
                        diff -= 2 * math.pi
                    if best_diff is None or diff < best_diff:
                        best_diff = diff
                        best = n

                remaining.discard((curr, best))
                prev, curr = curr, best

                if curr == loop[0]:
                    break

            # Close the loop: remove trailing duplicate of start
            if len(loop) >= 2 and loop[-1] == loop[0]:
                loop.pop()

            if len(loop) >= 3:
                loops.append(loop)

        return loops

    def _extract_corners(path):
        """Extracts corner points where direction changes along the path."""
        n = len(path)
        if n < 3:
            return list(path)

        corners = []
        for i in range(n):
            prev = path[(i - 1) % n]
            curr = path[i]
            nxt = path[(i + 1) % n]
            dir1 = (curr[0] - prev[0], curr[1] - prev[1])
            dir2 = (nxt[0] - curr[0], nxt[1] - curr[1])
            if dir1 != dir2:
                corners.append(curr)

        return corners

    def _loop_area(loop):
        """Computes the absolute area of a closed loop using the shoelace formula."""
        n = len(loop)
        return abs(sum(
            (loop[(i + 1) % n][0] - loop[i][0]) * (loop[(i + 1) % n][1] + loop[i][1])
            for i in range(n)
        )) / 2.0

    def _merge_loops_via_halfedge(boundary_edges):
        """Merges multi-loop boundaries into a single contour using half-edge face traversal.

        When the simple edge-following extraction produces multiple loops (due to
        pinch points where the boundary touches itself), this function adds reverse
        (CCW) half-edges and performs a planar face traversal. The largest CW face
        (in screen coords) is the correctly indented boundary that traces around
        internal islands.

        Only called when simple extraction produces >1 loop; single-loop boundaries
        use the simple result directly to avoid spurious faces.
        """
        ccw_edges = {(b, a) for (a, b) in boundary_edges}
        all_he = boundary_edges | ccw_edges

        adj = defaultdict(list)
        for (a, b) in all_he:
            adj[a].append(b)
        for v in adj:
            adj[v].sort(key=lambda n: math.atan2(-(n[1] - v[1]), n[0] - v[0]))

        def _screen_angle(dx, dy):
            return math.atan2(-dy, dx)

        used = set()
        cw_faces = []

        sorted_he = sorted(all_he, key=lambda e: (e[0][1], e[0][0], e[1][1], e[1][0]))
        for start_he in sorted_he:
            if start_he in used:
                continue
            face = [start_he[0]]
            u, v = start_he
            used.add(start_he)

            for _ in range(len(all_he)):
                face.append(v)
                arrival_dx = v[0] - u[0]
                arrival_dy = v[1] - u[1]
                reverse_angle = _screen_angle(-arrival_dx, -arrival_dy)

                candidates = [n for n in adj[v] if (v, n) in all_he and (v, n) not in used]
                if not candidates:
                    break

                best = min(candidates, key=lambda c: (
                    lambda d: (d if d > 0 else d + 2 * math.pi)
                )(reverse_angle - _screen_angle(c[0] - v[0], c[1] - v[1])))

                used.add((v, best))
                u, v = v, best
                if v == face[0]:
                    break

            if len(face) >= 2 and face[-1] == face[0]:
                face.pop()
            if len(face) >= 3:
                n = len(face)
                area = sum(
                    (face[(i + 1) % n][0] - face[i][0]) * (face[(i + 1) % n][1] + face[i][1])
                    for i in range(n)
                ) / 2
                if area > 0:
                    cw_faces.append((face, area))

        if not cw_faces:
            return None
        # Return the largest CW face
        cw_faces.sort(key=lambda x: x[1], reverse=True)
        return cw_faces[0][0]

    def _get_primary_contour(pixel_grid, label):
        """Extracts the primary boundary contour for a labeled region.

        Uses simple loop extraction first. If only one loop is found, uses it
        directly. If multiple loops are found (pinch points), falls back to
        half-edge face traversal to produce the correctly indented boundary.
        """
        coords, boundary = _get_boundary_edges(pixel_grid, label)
        loops = _extract_all_loops(boundary)

        if not loops:
            return {"coords": coords, "corners": []}

        if len(loops) == 1:
            corners = _extract_corners(loops[0])
            return {"coords": loops[0], "corners": corners}

        # Multiple loops: use half-edge merge to get the indented boundary
        merged = _merge_loops_via_halfedge(boundary)
        if merged:
            corners = _extract_corners(merged)
            return {"coords": merged, "corners": corners}

        # Fallback: largest simple loop
        loops.sort(key=_loop_area, reverse=True)
        corners = _extract_corners(loops[0])
        return {"coords": loops[0], "corners": corners}

    # Build paths and holes dicts.
    # Path labels: keep only the largest loop. Sub-loops are inner boundaries
    # that hole contours already cover (e.g. the inner ring of letter O).
    # Hole labels: if multiple loops exist, merge via half-edge to produce
    # the indented boundary that traces around path-pixel islands (e.g. the
    # battlements inside U+26C3's Hole -4). Single-loop holes use the loop directly.
    paths = {}
    for label in path_labels:
        coords, boundary = _get_boundary_edges(pixel_grid, label)
        loops = _extract_all_loops(boundary)
        if loops:
            loops.sort(key=_loop_area, reverse=True)
            corners = _extract_corners(loops[0])
            paths[label] = {"coords": loops[0], "corners": corners}
        else:
            paths[label] = {"coords": coords, "corners": []}

    holes = {}
    for label in hole_labels:
        coords, boundary = _get_boundary_edges(pixel_grid, label)
        loops = _extract_all_loops(boundary)
        if not loops:
            holes[label] = {"coords": coords, "corners": []}
        elif len(loops) == 1:
            corners = _extract_corners(loops[0])
            holes[label] = {"coords": loops[0], "corners": corners}
        else:
            # Multiple loops: merge via half-edge to get indented boundary
            merged = _merge_loops_via_halfedge(boundary)
            if merged:
                corners = _extract_corners(merged)
                holes[label] = {"coords": merged, "corners": corners}
            else:
                loops.sort(key=_loop_area, reverse=True)
                corners = _extract_corners(loops[0])
                holes[label] = {"coords": loops[0], "corners": corners}

    # Determine glyph sides
    col_sums = pixel_grid.sum(axis=0)
    col_ones = np.where(col_sums > 0)[0]
    min_x = col_ones[0] if len(col_ones) > 0 else 0
    max_x = col_ones[-1] if len(col_ones) > 0 else DEFAULT_GLYPH_SIZE - 1
    glyph_width = col_ones[-1] - col_ones[0] + 1 if len(col_ones) > 0 else DEFAULT_GLYPH_SIZE

    return {
        "bitmap": bitmap_grid,
        "grid": pixel_grid,
        "width": (max_x - min_x + 1),
        "lsb": min_x,
        "empty": len(col_ones) == 0,
        "advance": (min_x + glyph_width + 1),
        "paths": paths,
        "holes": holes
    }

def _write_tile_svg(grid, size, output_file):
    """Renders a pixel grid as an SVG file with 1x1 rect elements."""
    width, height = size

    svg_rects = [
        f'<rect x="{x}" y="{y}" width="1" height="1" />'
        for y, row in enumerate(grid)
        for x, val in enumerate(row)
        if val >= 1
    ]

    svg = {
        "xml": f'''<?xml version="1.0" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 {width} {height}" shape-rendering="crispEdges">
    <g fill="black">
        {''.join(svg_rects)}
    </g>
</svg>
''',
        "file": output_file
    }

    with open(svg["file"], "w", encoding="utf-8") as f:
        f.write(svg["xml"])

    return svg


# ==========================================
# === Stage 3: Build unified glyph map
# ==========================================

def build_glyph_map(providers, unifont_glyphs, stack=None):
    """Builds a unified glyph map merging provider glyphs (priority) with unifont fallbacks and alternate fonts."""
    log(f"🧩 Building unified glyph map...")
    glyph_map = {"Regular": OrderedDict(), "Bold": OrderedDict()}

    # 1. Add provider glyphs (priority - added first)
    for provider in providers:
        for tile in provider["tiles"]:
            cp = tile["codepoint"]
            for style_key in ("Regular", "Bold"):
                style = style_key.lower()
                if style_key == "Bold" and not BOLD_PACK_GLYPHS and tile.get("layer", "vanilla") != "vanilla":
                    style = "regular"
                flat_tile = {
                    "unicode": tile["unicode"],
                    "codepoint": cp,
                    "size": tile["size"],
                    "display_height": tile.get("display_height"),
                    "ascent": tile["ascent"],
                    "layer": tile.get("layer", "vanilla"),
                    "pixels": tile["pixels"][style],
                    "svg": tile["svg"].get(style) if tile.get("svg") else None,
                    "source": "provider"
                }
                glyph_map[style_key][cp] = flat_tile

    provider_count = len(glyph_map["Regular"])
    pack_count = sum(1 for t in glyph_map["Regular"].values() if t.get("layer", "vanilla") != "vanilla")
    log(f"→ 🔣 {provider_count} provider glyphs ({pack_count} from resource packs)")

    # 2. Add unifont glyphs (fallback - skip if codepoint exists)
    if unifont_glyphs:
        log(f"→ 🔣 Processing unifont fallback glyphs...")
        for style_key, bold in [("Regular", False), ("Bold", True)]:
            unifont_tiles = trace_unifont_tiles(unifont_glyphs, bold)
            for cp, tile in unifont_tiles.items():
                if cp not in glyph_map[style_key]:
                    glyph_map[style_key][cp] = tile

    # 3. Sort by codepoint
    for key in glyph_map:
        glyph_map[key] = OrderedDict(sorted(glyph_map[key].items()))

    # 4. Process alternate fonts (Galactic, Illageralt)
    if stack is not None:
        for style in FONT_STYLES:
            if "font_id" not in style or not style["enabled"]:
                continue
            overlay = _process_alternate_font(style, glyph_map["Regular"], stack)
            if overlay is not None:
                glyph_map[style["name"]] = overlay

    # 5. Print summary
    unifont_count = sum(1 for t in glyph_map["Regular"].values() if t["source"] == "unifont")
    total = len(glyph_map["Regular"])
    log(f"→ 🔢 Prepared {total} glyphs ({provider_count} provider, {unifont_count} unifont)")

    # 6. Pre-compute scaling
    precompute_glyph_scaling(glyph_map)

    return glyph_map

def trace_unifont_tiles(unifont_glyphs, bold=False):
    """Traces contours from parsed unifont hex bitmap data into tile dicts."""
    tiles = {}
    style_label = "Bold" if bold else "Regular"
    debug_unifont = any(s.get("debug", {}).get("unifont") for s in FONT_STYLES if s["pixel_style"] == style_label)

    with tqdm(unifont_glyphs.items(), total=len(unifont_glyphs),
              desc=f" → 🔣 {style_label}", unit="glyph",
              ncols=80, leave=False, file=sys.stdout, disable=is_silent()) as progress:
        for codepoint, bitmap_rows in progress:
            bitmap_grid = np.array(bitmap_rows, dtype=np.uint8)
            pixel_data = _trace_bitmap_contours2(bitmap_grid, bold)
            width = len(bitmap_rows[0]) if bitmap_rows else 8

            svg = None
            if debug_unifont:
                output = f"{WORK_DIR}/glyphs/unifont/{style_label.lower()}/{codepoint:04X}"
                os.makedirs(output, exist_ok=True)
                svg = _write_tile_svg(pixel_data["grid"], (width, 16), f"{output}/{style_label.lower()}.svg")

            tiles[codepoint] = {
                "unicode": chr(codepoint),
                "codepoint": codepoint,
                "size": (width, 16),
                "ascent": 15,
                "pixels": pixel_data,
                "svg": svg,
                "source": "unifont"
            }

    return tiles

def _process_alternate_font(alt_config, regular_map, stack):
    """Builds an alternate-font overlay map (Galactic/Illageralt) from all asset layers.

    Collects the font id's providers across the stack (packs override vanilla),
    slices them with the shared pipeline, and overlays the tiles onto a clone of
    the Regular map. Codepoints new to the font are appended. Returns None when
    no layer defines the font or no tiles survive."""
    name = alt_config["name"]
    font_id = alt_config["font_id"]
    map_lowercase = alt_config.get("map_lowercase", False)

    providers = []
    for source_name, raw in stack.font_json_layers(font_id):
        try:
            layer = parse_json_providers(raw, stack, layer_name=sanitize_fs_name(f"{source_name}_{name}"))
        except (ValueError, AttributeError) as error:
            log(f" → ⚠️ Skipping malformed font JSON '{font_id}' in layer '{source_name}': {error}")
            continue
        layer.reverse()  # the game walks a font's providers first-wins; the merge below is last-wins
        providers += layer
    if not providers:
        return None

    slice_provider_tiles(providers)

    alt_tiles = {}
    for provider in providers:
        for tile in provider["tiles"]:
            alt_tiles[tile["codepoint"]] = {
                "unicode": tile["unicode"],
                "codepoint": tile["codepoint"],
                "size": tile["size"],
                "display_height": tile["display_height"],
                "ascent": tile["ascent"],
                "pixels": tile["pixels"]["regular"],
                "svg": None,
                "source": "alternate"
            }
    if not alt_tiles:
        return None

    # If map_lowercase, duplicate uppercase glyphs onto lowercase codepoints
    if map_lowercase:
        for cp in list(alt_tiles.keys()):
            if 0x41 <= cp <= 0x5A:  # A-Z
                lower_cp = cp + 0x20  # a-z
                if lower_cp not in alt_tiles:
                    lower_tile = dict(alt_tiles[cp])
                    lower_tile["unicode"] = chr(lower_cp)
                    lower_tile["codepoint"] = lower_cp
                    alt_tiles[lower_cp] = lower_tile

    # Clone Regular, overlay alternate tiles, and append codepoints new to the font
    overlay_map = OrderedDict()
    for cp, tile in regular_map.items():
        overlay_map[cp] = alt_tiles.get(cp, tile)
    new_cps = [cp for cp in alt_tiles if cp not in regular_map]
    for cp in new_cps:
        overlay_map[cp] = alt_tiles[cp]
    if new_cps:
        overlay_map = OrderedDict(sorted(overlay_map.items()))

    override_count = len(alt_tiles) - len(new_cps)
    log(f"→ 🔣 {name}: {len(alt_tiles)} alternate glyphs ({override_count} overriding Regular, {len(new_cps)} new)")

    return overlay_map

def precompute_glyph_scaling(glyph_map):
    """Scales glyph coordinates from pixel space to font units, splits self-touching contours, and insets shared vertices."""
    styles = len(glyph_map)
    per_style = len(next(iter(glyph_map.values())))
    total = per_style * styles
    log(f"→ ✖️ Pre-scaling {per_style} glyphs ({styles} styles)...")

    with tqdm(total=total, desc=" → 🔣 Scaling", unit="glyph",
              ncols=80, leave=False, file=sys.stdout, disable=is_silent()) as progress:
        for style_key in glyph_map:
            for cp, tile in glyph_map[style_key].items():
                progress.update(1)

                # Scale factor.
                # Tiles carrying display_height use the game's bitmap-provider
                # semantics: the tile renders display_height virtual pixels
                # tall (display_scale = display_height / tile pixel height)
                # with its top edge ascent virtual pixels above the baseline.
                # Negative ascent is legal and hangs the glyph below the
                # baseline. Every vanilla provider has display_height equal to
                # its tile pixel height, so this reduces to the legacy uniform
                # 128 units per pixel.
                # Unifont fallback glyphs use ASCENT / ascent to compress 16px
                # rows into the same visual space as 8px provider rows.
                width, height = tile["size"]
                ascent = tile.get("ascent", 0)
                display_height = tile.get("display_height")
                display_scale = None
                if tile.get("source") == "unifont" and ascent > 0:
                    scale = ASCENT / ascent
                elif display_height is not None:
                    display_scale = display_height / height if height else 1.0
                    scale = (UNITS_PER_EM / DEFAULT_GLYPH_SIZE) * display_scale
                else:
                    scale = UNITS_PER_EM / DEFAULT_GLYPH_SIZE
                tile["units_per_pixel"] = scale

                pixels = tile.get("pixels")
                if display_scale is not None and pixels:
                    ink_width = 0 if pixels.get("empty") else pixels.get("width", 0)
                    tile["advance_units"] = int(
                        (math.floor(0.5 + ink_width * display_scale) + 1)
                        * (UNITS_PER_EM / DEFAULT_GLYPH_SIZE))

                if not pixels:
                    tile["scaled"] = {"outer": [], "holes": []}
                    continue

                paths = pixels.get("paths", {})
                holes = pixels.get("holes", {})

                outer_paths = [p["corners"] for p in paths.values() if len(p.get("corners", [])) >= 3]
                hole_paths = [h["corners"] for h in holes.values() if len(h.get("corners", [])) >= 3]

                all_points = [pt for path in outer_paths + hole_paths for pt in path]
                if not all_points:
                    tile["scaled"] = {"outer": [], "holes": []}
                    continue

                min_x = min(x for x, y in all_points)
                if display_scale is not None:
                    descender_offset = ascent * height / display_height
                elif ascent > 0:
                    descender_offset = ascent
                else:
                    descender_offset = ASCENT / scale

                def transform(pt, _min_x=min_x, _s=scale, _do=descender_offset):
                    x, y = pt
                    return ((x - _min_x) * _s, (_do - y) * _s)

                scaled_outer = [[transform(pt) for pt in path] for path in outer_paths]
                scaled_holes = [[transform(pt) for pt in path] for path in hole_paths]

                scaled_outer = _split_self_touching(scaled_outer)
                scaled_holes = _split_self_touching(scaled_holes)
                scaled_outer, scaled_holes = _inset_shared_vertices(scaled_outer, scaled_holes)

                tile["scaled"] = {
                    "outer": scaled_outer,
                    "holes": scaled_holes
                }

def _split_self_touching(contours):
    """Splits self-touching contours at duplicate vertices.

    Pixel contour tracing can produce figure-eight paths that revisit the
    same vertex at pinch points. Each loop becomes its own contour.
    """
    result = []
    for contour in contours:
        pending = [contour]
        while pending:
            c = pending.pop()
            seen = {}
            split = False
            for i, pt in enumerate(c):
                key = (round(pt[0]), round(pt[1]))
                if key in seen:
                    loop = c[seen[key]:i]
                    rest = c[:seen[key]] + c[i:]
                    if len(loop) >= 3:
                        result.append(loop)
                    if len(rest) >= 3:
                        pending.append(rest)
                    split = True
                    break
                seen[key] = i
            if not split and len(c) >= 3:
                result.append(c)

    return result

def _inset_shared_vertices(scaled_outer, scaled_holes):
    """Insets shared vertices by 1 font unit along the bisector of adjacent edges.

    Breaks vertex sharing between contours (a pixel font artifact that
    triggers FontForge's wrong-direction false positive).
    """
    all_contours = scaled_outer + scaled_holes
    if len(all_contours) <= 1:
        return scaled_outer, scaled_holes

    shared_pts = set()
    for i, ci in enumerate(all_contours):
        si = {(round(x), round(y)) for x, y in ci}
        for j, cj in enumerate(all_contours):
            if i < j:
                sj = {(round(x), round(y)) for x, y in cj}
                shared_pts |= si & sj

    if not shared_pts:
        return scaled_outer, scaled_holes

    for i, contour in enumerate(all_contours):
        inset = []
        n = len(contour)
        for k, (x, y) in enumerate(contour):
            if (round(x), round(y)) in shared_pts:
                px, py = contour[(k - 1) % n]
                nx, ny = contour[(k + 1) % n]
                dx = (px - x) + (nx - x)
                dy = (py - y) + (ny - y)
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > 0:
                    x += dx / dist
                    y += dy / dist
            inset.append((x, y))
        all_contours[i] = inset

    outer_count = len(scaled_outer)
    return all_contours[:outer_count], all_contours[outer_count:]
