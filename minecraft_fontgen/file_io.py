import math
import os
import shutil
import sys
import numpy as np

from collections import defaultdict, deque, OrderedDict
from tqdm import tqdm
from PIL import Image
from minecraft_fontgen.config import ASCENT, COLUMNS_PER_ROW, DEFAULT_GLYPH_SIZE, OUTPUT_DIR, MINECRAFT_JAR_DIR, WORK_DIR, UNITS_PER_EM, TEXTURE_PATH, FONT_STYLES
from minecraft_fontgen.functions import get_unicode_codepoint, in_unifont_ranges, log, is_silent, parse_json


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

def parse_provider_file(file, format):
    """Reads a font provider file, parses it by format, and slices into glyph tiles."""
    log(f"🧩 Parsing {file}...")
    with open(file, "rb") as f:
        raw_bytes = f.read()

    log(f"→ 🛠️ Decoding {format}...")
    if format == "bin":
        providers = parse_bin_providers(raw_bytes)
    elif format == "json":
        providers = parse_json_providers(raw_bytes)
    else:
        raise ValueError(f"Unsupported file format: {format}")

    slice_provider_tiles(providers)
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
            "chars": chars,
            "file_name": ascii_file,
            "file_path": ascii_path,
            "name": name,
            "output": output,
            "tiles": []
        })

    return providers

def parse_json_providers(byte_data):
    """Parses the JSON font provider format (default.json) into a list of provider dicts."""
    raw_text = byte_data.decode("utf-8", errors="surrogatepass")
    data = parse_json(raw_text)

    log("→ 🛠️ Parsing bitmap providers...")
    providers = []
    for provider in data.get("providers", []):
        if provider.get("type") == "bitmap" and "chars" in provider:
            file_name = provider.get("file", "minecraft:font/").split("minecraft:font/")[-1]
            name = os.path.splitext(file_name)[0]
            output = f"{WORK_DIR}/glyphs/{name}"

            # Create provider directory
            os.makedirs(output, exist_ok=True)

            # Read unicode characters
            chars = [char for row in provider.get("chars", []) for char in row]
            log(f" → 🔢 Detected {len(chars)} unicode characters in '{name}'...")

            providers.append({
                "ascent": provider.get("ascent", 0),
                "height": provider.get("height", DEFAULT_GLYPH_SIZE),
                "chars": chars,
                "file_name": file_name,
                "file_path": f"{MINECRAFT_JAR_DIR}/textures/font/{file_name}",
                "name": name,
                "output": output,
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
        tiles = []

        # Calculate tile dimensions
        width, height = bitmap.size
        glyph_width = width / COLUMNS_PER_ROW

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
                tile_row = i // COLUMNS_PER_ROW
                tile_column = i % COLUMNS_PER_ROW
                tile = {
                    "unicode": unicode,
                    "codepoint": codepoint,
                    "size": (glyph_width, provider.get("height")),
                    "ascent": provider.get("ascent", 0),
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
    """Reads a provider PNG, composites over black, inverts to black-on-white, and binarizes."""
    img = Image.open(provider["file_path"]).convert("RGBA")

    # Composite white glyphs over black background
    bg = Image.new("RGBA", img.size, (0, 0, 0, 255)) # Black background
    img = Image.alpha_composite(bg, img).convert("L") # 1-bit grayscale

    # Invert white glyphs to black
    img = Image.eval(img, lambda x: 255 - x)

    # Binarize to 1-bit: make black glyphs (0) on white (255)
    img = img.point(lambda x: 0 if x < 128 else 255, '1')

    # Copy original and save grayscale
    output_file = provider["output"] + "/" + provider["name"]
    shutil.copyfile(provider["file_path"], output_file + ".png")
    img.save(f"{output_file}_grayscale.png")

    return img

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

def build_glyph_map(providers, unifont_glyphs):
    """Builds a unified glyph map merging provider glyphs (priority) with unifont fallbacks and alternate fonts."""
    log(f"🧩 Building unified glyph map...")
    glyph_map = {"Regular": OrderedDict(), "Bold": OrderedDict()}

    # 1. Add provider glyphs (priority - added first)
    for provider in providers:
        for tile in provider["tiles"]:
            cp = tile["codepoint"]
            for style_key in ("Regular", "Bold"):
                style = style_key.lower()
                flat_tile = {
                    "unicode": tile["unicode"],
                    "codepoint": cp,
                    "size": tile["size"],
                    "ascent": tile["ascent"],
                    "pixels": tile["pixels"][style],
                    "svg": tile["svg"].get(style) if tile.get("svg") else None,
                    "source": "provider"
                }
                glyph_map[style_key][cp] = flat_tile

    provider_count = len(glyph_map["Regular"])
    log(f"→ 🔣 {provider_count} provider glyphs (priority)")

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
    for style in FONT_STYLES:
        if "json_file" not in style or not style["enabled"]:
            continue
        overlay = _process_alternate_font(style, glyph_map["Regular"])
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

def _process_alternate_font(alt_config, regular_map):
    """Processes an alternate font by cloning Regular and overlaying alternate glyphs.

    Reads the alternate font's JSON provider file to get char mappings, processes
    its bitmap PNG into tiles, then overlays those tiles onto a copy of the Regular
    glyph map. Returns the overlay map, or None if the assets are missing.
    """
    name = alt_config["name"]
    json_file = alt_config["json_file"]
    map_lowercase = alt_config.get("map_lowercase", False)

    if not os.path.isfile(json_file):
        return None

    with open(json_file, "rb") as f:
        raw_text = f.read().decode("utf-8", errors="surrogatepass")
    data = parse_json(raw_text)

    # Find the bitmap provider in the JSON
    bitmap_provider = None
    for provider in data.get("providers", []):
        if provider.get("type") == "bitmap" and "chars" in provider:
            bitmap_provider = provider
            break

    if not bitmap_provider:
        return None

    # Resolve the texture file path
    file_name = bitmap_provider.get("file", "").split("minecraft:font/")[-1]
    texture_path = f"{TEXTURE_PATH}/{file_name}"
    if not os.path.isfile(texture_path):
        return None

    ascent = bitmap_provider.get("ascent", 7)
    height = bitmap_provider.get("height", DEFAULT_GLYPH_SIZE)
    chars = [char for row in bitmap_provider.get("chars", []) for char in row]

    # Read and process the bitmap
    img = Image.open(texture_path).convert("RGBA")
    bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
    img = Image.alpha_composite(bg, img).convert("L")
    img = Image.eval(img, lambda x: 255 - x)
    img = img.point(lambda x: 0 if x < 128 else 255, '1')

    img_width, img_height = img.size
    glyph_width = img_width / COLUMNS_PER_ROW

    # Process each glyph tile
    alt_tiles = {}
    for i, unicode_char in enumerate(chars):
        codepoint = get_unicode_codepoint(unicode_char)
        if codepoint is None or codepoint == 0x0000:
            continue

        tile_row = i // COLUMNS_PER_ROW
        tile_column = i % COLUMNS_PER_ROW
        px, py = (int(tile_column * glyph_width), tile_row * height)
        tile_img = img.crop((px, py, px + int(glyph_width), py + height))

        bitmap_grid = np.array(tile_img.convert("L"), dtype=int)
        bitmap_grid = (bitmap_grid < 128).astype(np.uint8)
        pixel_data = _trace_bitmap_contours2(bitmap_grid, bold=False)

        tile = {
            "unicode": unicode_char,
            "codepoint": codepoint,
            "size": (glyph_width, height),
            "ascent": ascent,
            "pixels": pixel_data,
            "svg": None,
            "source": "alternate"
        }
        alt_tiles[codepoint] = tile

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

    # Clone Regular and overlay alternate tiles
    overlay_map = OrderedDict()
    for cp, tile in regular_map.items():
        if cp in alt_tiles:
            overlay_map[cp] = alt_tiles[cp]
        else:
            overlay_map[cp] = tile

    override_count = sum(1 for cp in alt_tiles if cp in regular_map)
    log(f"→ 🔣 {name}: {len(alt_tiles)} alternate glyphs ({override_count} overriding Regular)")

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

                # Compute scale factor.
                # Provider glyphs use a uniform pixel scale (UNITS_PER_EM /
                # DEFAULT_GLYPH_SIZE = 128) so that 1 Minecraft pixel = 1 font
                # unit regardless of provider height.  This keeps the base
                # character of accented glyphs (height=12) the same size as the
                # equivalent standard glyph (height=8), with accents extending
                # above the normal ascent line.
                # Unifont fallback glyphs use ASCENT / ascent to compress 16px
                # rows into the same visual space as 8px provider rows.
                width, height = tile["size"]
                ascent = tile.get("ascent", 0)
                if tile.get("source") == "unifont" and ascent > 0:
                    scale = ASCENT / ascent
                else:
                    scale = UNITS_PER_EM / DEFAULT_GLYPH_SIZE
                tile["units_per_pixel"] = scale

                pixels = tile.get("pixels")
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
                descender_offset = ascent if ascent > 0 else ASCENT / scale

                def transform(pt, _min_x=min_x, _s=scale, _do=descender_offset):
                    x, y = pt
                    return ((x - _min_x) * _s, (_do - y) * _s)

                scaled_outer = [[transform(pt) for pt in path] for path in outer_paths]
                scaled_holes = [[transform(pt) for pt in path] for path in hole_paths]

                scaled_outer = _split_self_touching(scaled_outer)
                scaled_holes = _split_self_touching(scaled_holes)

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

