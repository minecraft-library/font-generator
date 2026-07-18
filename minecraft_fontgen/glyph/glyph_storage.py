from collections import OrderedDict
from math import ceil, floor

from fontTools.ttLib import newTable
from fontTools.ttLib.tables.sbixStrike import Strike
from fontTools.ttLib.tables.sbixGlyph import Glyph as SbixGlyph

from minecraft_fontgen.glyph.glyph import Glyph
from minecraft_fontgen.config import (
    NOTDEF, DEFAULT_GLYPH_SIZE, UNITS_PER_EM, UNITS_PER_PIXEL_BASE,
    PPEM_ROUND_EPS, SBIX_RESOLUTION, SBIX_GRAPHIC_TYPE,
    SBIX_INT16_MIN, SBIX_INT16_MAX, SBIX_UINT16_MAX,
)
from minecraft_fontgen.functions import log

def _clamp(value, low, high):
    """Clamps value into the inclusive [low, high] range."""
    return max(low, min(high, value))

class GlyphStorage:
    """Accumulates drawn glyphs, manages cmap entries, and writes final font data."""

    def __init__(self, font, use_cff: bool = True, color_mode: bool = False, pack_id=None):
        """Initializes storage bound to a TTFont, extracting CFF or glyf table references.

        pack_id records the identity of the source this font was built from (the vanilla
        id for the mono styles, the pack's id for a colour font); it does not affect the
        compiled bytes."""
        self.font = font
        self.tables = font["cmap"].tables
        self.use_cff = use_cff
        self.color_mode = color_mode
        self.pack_id = pack_id
        self.glyphs = OrderedDict()
        self.cpr = [0xFFFFFF, 0]
        self.hmtx = {}
        self.y_min = 0
        self.y_max = 0

        # Colour (sbix) accumulators. sbix_strikes maps ppem -> {name: (png, ox, oy)};
        # embed_cache dedups (content_hash, ppem, origin, advance) -> glyph name;
        # sidecar_rows collect the per-(font_id, codepoint) rows for the JSON sidecar;
        # the raster_* extents re-synthesize head/OS2 after maxp.recalc clobbers them.
        self.sbix_strikes = OrderedDict()
        self.embed_cache = {}
        self.sidecar_rows = []
        self.raster_y_top = None
        self.raster_y_bot = None
        self.raster_x_max = 0

        if self.use_cff:
            cff = font["CFF "]
            self.top_dict = cff.cff.topDictIndex[0]
            self.charstrings = self.top_dict.CharStrings
        else:
            self.glyf = font["glyf"]

    def create_glyph(self, tile):
        """Creates a new Glyph instance from tile data using this storage's font format."""
        return Glyph(tile, self.use_cff)

    def _map_codepoint(self, codepoint, name):
        """Maps a codepoint to a glyph name in every applicable cmap subtable (format 4
        for the BMP, format 12 for the SMP). Shared by the mono and raster add paths."""
        for table in self.tables:
            if table.format == 4 and codepoint <= 0xFFFF:  # BMP (U+0000 - U+FFFF)
                table.cmap[codepoint] = name
            elif table.format == 12:  # SMP (U+10000 - U+10FFFF)
                table.cmap[codepoint] = name

    def add(self, glyph: Glyph):
        """Adds a drawn glyph to storage with its advance width, LSB, and cmap mappings."""
        if glyph.is_raster:
            self._add_raster(glyph)
            return

        name = glyph.name
        if name in ("space", "uni0020"):
            advance_width = UNITS_PER_EM // 2
        elif glyph.advance_units is not None:
            advance_width = glyph.advance_units
        else:
            advance_width = int(round((glyph.width + 1) * glyph.units_per_pixel))
        lsb = 0

        # Adjust metrics from actual glyph extents (italic shear may widen glyphs)
        all_contours = list(glyph.outer_scaled) + list(glyph.holes_scaled)
        if all_contours:
            all_points = [pt for contour in all_contours for pt in contour]
            x_max = max(x for x, y in all_points)
            y_max = max(y for x, y in all_points)
            y_min = min(y for x, y in all_points)

            if x_max > advance_width:
                advance_width = ceil(x_max)

            self.y_max = max(self.y_max, y_max)
            self.y_min = min(self.y_min, y_min)

        self.hmtx[name] = (advance_width, lsb)

        # Draw font glyph
        font_glyph = glyph.build()
        if self.use_cff:
            font_glyph.width = advance_width
            if font_glyph.program and isinstance(font_glyph.program[0], (int, float)):
                font_glyph.program[0] = advance_width
            font_glyph.private = self.top_dict.Private
        self.glyphs[name] = font_glyph

        # Update min/max codepoint
        if glyph.codepoint != 0x0000:
            self.cpr[0] = min(self.cpr[0], glyph.codepoint)
            self.cpr[1] = max(self.cpr[1], glyph.codepoint)

        # Add to glyph mapping
        self._map_codepoint(glyph.codepoint, name)

    def _add_raster(self, glyph: Glyph):
        """Adds a colour (raster) glyph: an empty glyf outline plus an sbix strike
        entry keyed by display-scale ppem, deduped on pixels + geometry + advance.

        The uint16 hmtx advance is clamped non-negative; the true signed advance
        rides in the sidecar row (the consumer positions from the sidecar because
        Java2D zeroes GlyphVector advances on any font carrying an sbix table)."""
        native_w, native_h = glyph.raster_size
        display_height = glyph.display_height
        ascent = glyph.ascent

        # Units per NATIVE pixel at the cell's display scale. The vertical model
        # below spans display_height * UNITS_PER_PIXEL_BASE, so the horizontal
        # advance and x-extent must use the same display-scale-aware factor.
        # native_h and display_height routinely differ (a 256px cell shown at
        # height 8, an icon shown at height 32), so glyph.units_per_pixel
        # (UNITS_PER_EM / native_h) is wrong here: it silently assumes the cell
        # is displayed at 8px and under-advances everything else by 8/display_height.
        upp = UNITS_PER_PIXEL_BASE * display_height / native_h if native_h else UNITS_PER_PIXEL_BASE

        # Advance is the full cell footprint: art spaces by its own width. Negative
        # or fractional space-provider advances live in the sidecar, never here.
        advance_signed = int(round(native_w * upp))
        advance_clamped = max(0, min(0xFFFF, advance_signed))

        ppem = self._strike_ppem(native_h, display_height, glyph)
        # origin_units is authoritative for the Java consumer; the sbix int16 pixel
        # originOffset is spec-compliant for native renderers but not load-bearing here.
        origin_units = (0, (ascent - display_height) * UNITS_PER_PIXEL_BASE)
        ox_px, oy_px = self._sbix_origin_px(ascent, display_height, native_h)

        # Dedup only when pixels AND geometry AND advance all match: two codepoints
        # with identical art but a different strike ppem / advance must stay distinct.
        dedup_key = (glyph.content_hash, ppem, origin_units, advance_clamped)
        name = self.embed_cache.get(dedup_key)
        if name is None:
            name = glyph.name
            # A stored-codepoint-derived name is unique across the whole pack, but
            # never silently overwrite a distinct glyph if one ever collides.
            if name in self.glyphs:
                base = name
                suffix = 1
                while name in self.glyphs:
                    name = f"{base}.{suffix}"
                    suffix += 1

            self.glyphs[name] = glyph.build()  # empty TTGlyph (numberOfContours == 0)
            self.hmtx[name] = (advance_clamped, 0)
            self.sbix_strikes.setdefault(ppem, OrderedDict())[name] = (glyph.raster_png, ox_px, oy_px)

            top = ascent * UNITS_PER_PIXEL_BASE
            bot = (ascent - display_height) * UNITS_PER_PIXEL_BASE
            x_max = native_w * upp
            self.raster_y_top = top if self.raster_y_top is None else max(self.raster_y_top, top)
            self.raster_y_bot = bot if self.raster_y_bot is None else min(self.raster_y_bot, bot)
            self.raster_x_max = max(self.raster_x_max, x_max)
            self.embed_cache[dedup_key] = name

        # The cmap and OS/2 char-index range key on the STORED codepoint (what the
        # merged font actually carries); the original codepoint lives only in the
        # sidecar row so the consumer can bridge pack + original codepoint -> row.
        stored_cp = glyph.stored_codepoint
        if stored_cp is not None and stored_cp != 0x0000:
            self.cpr[0] = min(self.cpr[0], stored_cp)
            self.cpr[1] = max(self.cpr[1], stored_cp)

        # Many stored codepoints may point at one (deduped) name.
        if stored_cp is not None:
            self._map_codepoint(stored_cp, name)

        self._append_sidecar_row(glyph.font_id, glyph.codepoint, stored_cp, name,
                                 advance_signed, origin_units, ppem)

    def _append_sidecar_row(self, font_id, codepoint, stored_codepoint, glyph_name,
                            advance, origin_units, strike_ppem):
        """Appends one JSON-sidecar row. gid is resolved later against the compiled
        glyph order (see colour_sidecar.build_sidecar). Shared by the raster-glyph and
        the space-row paths so their row shape can never drift."""
        self.sidecar_rows.append({
            "font_id": font_id,
            "codepoint": codepoint,
            "stored_codepoint": stored_codepoint,
            "glyphName": glyph_name,
            "gid": None,
            "advance": advance,
            "origin_units": list(origin_units),
            "strike_ppem": strike_ppem,
        })

    def _strike_ppem(self, native_h, display_height, glyph):
        """Returns the sbix strike ppem for a cell's display scale.

        ppem == round(8 / display_scale) == round(8 * native_h / display_height).
        Counterintuitively a DOWNSCALED cell (native taller than its display height)
        gets a LARGER ppem, not smaller. Warns and clamps on non-integer rounding."""
        display_scale = display_height / native_h if native_h else 1.0
        raw = UNITS_PER_EM / (UNITS_PER_PIXEL_BASE * display_scale)
        ppem = int(round(raw))
        if abs(raw - ppem) > PPEM_ROUND_EPS:
            log(f" → ⚠️ Non-integer strike ppem {raw:.4f} for {glyph.font_id} "
                f"U+{glyph.codepoint:04X}; rounding to {ppem}")
        return max(1, min(0xFFFF, ppem))

    def _sbix_origin_px(self, ascent, display_height, native_h):
        """Returns the int16 sbix pixel originOffset (x, y) for a cell.

        Sign/convention is pinned by a FreeType golden-image test, not asserted here;
        the Java consumer reads origin_units from the sidecar instead."""
        oy = round((ascent - display_height) * native_h / display_height) if display_height else 0
        ox = max(SBIX_INT16_MIN, min(SBIX_INT16_MAX, 0))
        oy = max(SBIX_INT16_MIN, min(SBIX_INT16_MAX, oy))
        return ox, oy

    def add_space_row(self, font_id, codepoint, advance_signed):
        """Appends a sidecar-only row for a space-provider advance: no glyph is minted
        (no cmap / hmtx / glyf / strike). The signed, possibly fractional advance is
        the sole carrier of negative/fractional spacing to the consumer."""
        self._append_sidecar_row(font_id, codepoint, None, None, advance_signed, (0, 0), None)

    def name_to_gid(self):
        """Maps each glyph name to its gid in the compiled glyph order. The sidecar
        keys on gid because post format 3.0 renames glyphs to uniXXXX on reload."""
        return {name: gid for gid, name in enumerate(self.font.getGlyphOrder())}

    def add_notdef(self):
        """Creates and adds the .notdef placeholder glyph."""
        self.add(Glyph({
            "unicode": None,
            "codepoint": 0x0000,
            "size": (DEFAULT_GLYPH_SIZE, DEFAULT_GLYPH_SIZE),
            "location": (0, 0),
            "output": None
        }, self.use_cff))

    def finalize(self):
        """Finalizes the font by setting glyph order, charstrings/glyf entries, and metrics."""
        # Colour fonts carry sbix strikes and need a different bbox synthesis order
        # (maxp.recalc clobbers head's bbox from contours only, dropping tall art).
        if self.sbix_strikes:
            self._finalize_color()
            return

        # Sort glyphs
        self.glyphs = OrderedDict([(NOTDEF, self.glyphs[NOTDEF])] + list(self.glyphs.items()))

        # Set glyph order
        self.font.setGlyphOrder(list(self.glyphs.keys()))

        # Set glyph mappings
        if self.use_cff:
            self.top_dict.charset = list(self.glyphs.keys())

            for name, glyph in self.glyphs.items():
                self.charstrings[name] = glyph
        else:
            self.glyf.glyphOrder = self.font.getGlyphOrder()

            for name, glyph in self.glyphs.items():
                self.glyf.glyphs[name] = glyph

        # Set glyph metrics
        total_glyphs = len(self.glyphs)
        self.font["hmtx"].metrics = self.hmtx
        self.font["hhea"].numberOfHMetrics = total_glyphs # Number of advanceWidth + leftSideBearing pairs in the hmtx table
        self.font["maxp"].numGlyphs = total_glyphs # Total number of glyphs in the font
        self.font["OS/2"].usFirstCharIndex = self.cpr[0] # First Unicode codepoint in the font
        self.font["OS/2"].usLastCharIndex = self.cpr[1] # Last Unicode codepoint in the font

        advances = [aw for (aw, _lsb) in self.hmtx.values() if aw is not None]
        self.font["OS/2"].xAvgCharWidth = int(round(sum(advances) / len(advances))) # Average character width (mean of the advanced widths)

        # Update head table bounding box to encompass all glyph extents
        y_max = ceil(self.y_max)
        y_min = floor(self.y_min)
        if y_max > self.font["head"].yMax:
            self.font["head"].yMax = y_max
        if y_min < self.font["head"].yMin:
            self.font["head"].yMin = y_min

        # Update Windows clipping metrics to prevent clipping of accented glyphs
        if y_max > self.font["OS/2"].usWinAscent:
            self.font["OS/2"].usWinAscent = y_max
        if abs(y_min) > self.font["OS/2"].usWinDescent:
            self.font["OS/2"].usWinDescent = abs(y_min)

    def _finalize_color(self):
        """Finalizes a colour (sbix) font: empty-glyf raster glyphs plus contour-bearing
        mono glyphs, an sbix table, and a head/OS2 bbox re-synthesized to enclose the
        raster art after maxp.recalc (which sees contours only) clobbers it."""
        # 1. .notdef first, set glyph order, populate glyf.
        self.glyphs = OrderedDict([(NOTDEF, self.glyphs[NOTDEF])] + list(self.glyphs.items()))
        self.font.setGlyphOrder(list(self.glyphs.keys()))
        self.glyf.glyphOrder = self.font.getGlyphOrder()
        for name, glyph in self.glyphs.items():
            self.glyf.glyphs[name] = glyph

        # 2. save() must not recompute head's bbox from glyf (that would re-drop the
        #    tall raster extents synthesized in step 6, since sbix has zero contours).
        self.font.recalcBBoxes = False

        # hmtx must be populated before maxp.recalc, which reads hmtx[name][1] for
        # every contour-bearing glyph (e.g. .notdef) to fold in the LSB check.
        self.font["hmtx"].metrics = self.hmtx

        # 3. Set bounds on contour-bearing glyphs only; empty raster glyphs (nc == 0)
        #    are skipped, which also avoids a KeyError('xMin') inside maxp.recalc.
        for name, glyph in self.glyf.glyphs.items():
            if getattr(glyph, "numberOfContours", 0):
                glyph.recalcBounds(self.glyf)

        # 4. Recompute maxp (and, as a side effect, head's bbox from CONTOURS ONLY).
        self.font["maxp"].recalc(self.font)

        # 5. Build the sbix table, one strike per display-scale ppem.
        #
        # sbix (verbatim per-cell RGBA PNG) is the chosen colour format. COLR/CPAL
        # is rejected on two counts: the packs' colour is baked raster, not
        # parametric vector (COLR would need lossy per-plane vectorization that
        # explodes on gradients), and Java2D renders COLRv0 as a mono black outline
        # so it would not even show in the target consumer. CBDT/CBLC is a non-goal:
        # fontTools ships no writer for the colour CBDT formats, and CBDT's uint8
        # glyph height overflows at the 256px art sbix carries. A test pins that no
        # COLR/CPAL/CBDT/CBLC table is emitted.
        sbix = newTable("sbix")
        sbix.version = 1
        sbix.flags = 1  # bit0 only; the glyf glyphs are empty so no outline draws
        sbix.numStrikes = 0
        sbix.strikes = {}
        for ppem in sorted(self.sbix_strikes):
            strike = Strike(ppem=ppem, resolution=SBIX_RESOLUTION)
            for gname, (png, ox, oy) in self.sbix_strikes[ppem].items():
                strike.glyphs[gname] = SbixGlyph(
                    glyphName=gname, graphicType=SBIX_GRAPHIC_TYPE,
                    imageData=png, originOffsetX=ox, originOffsetY=oy,
                )
            sbix.strikes[ppem] = strike
        self.font["sbix"] = sbix

        # 6. Re-synthesize the bbox that maxp.recalc just clobbered so tall art (whose
        #    contours are empty) is enclosed by head and the Windows clipping metrics.
        # head's bbox fields are int16 and the OS/2 clipping metrics are uint16, so
        # very tall/wide art (a large display height puts extents past 256px * 128
        # upp) is clamped to the field range; the exact geometry lives in the sbix
        # strikes and the sidecar, so a saturated advisory bbox loses nothing.
        head = self.font["head"]
        os2 = self.font["OS/2"]
        if self.raster_y_top is not None:
            head.yMax = _clamp(max(head.yMax, ceil(self.raster_y_top)), SBIX_INT16_MIN, SBIX_INT16_MAX)
            os2.usWinAscent = _clamp(max(os2.usWinAscent, ceil(self.raster_y_top)), 0, SBIX_UINT16_MAX)
        if self.raster_y_bot is not None:
            head.yMin = _clamp(min(head.yMin, floor(self.raster_y_bot)), SBIX_INT16_MIN, SBIX_INT16_MAX)
            if self.raster_y_bot < 0:
                os2.usWinDescent = _clamp(max(os2.usWinDescent, ceil(-self.raster_y_bot)), 0, SBIX_UINT16_MAX)
        head.xMax = _clamp(max(head.xMax, ceil(self.raster_x_max)), SBIX_INT16_MIN, SBIX_INT16_MAX)

        # 7. Metrics (maxp.recalc already set numGlyphs; restate for symmetry).
        #    The OS/2 char-index fields are uint16 and xAvgCharWidth is int16, so an
        #    SMP colour codepoint or a very wide cell advance is clamped to the field
        #    range (the spec's own rule for usLastCharIndex past U+FFFF is 0xFFFF).
        total_glyphs = len(self.glyphs)
        self.font["hhea"].numberOfHMetrics = total_glyphs
        self.font["maxp"].numGlyphs = total_glyphs
        self.font["OS/2"].usFirstCharIndex = _clamp(self.cpr[0], 0, SBIX_UINT16_MAX)
        self.font["OS/2"].usLastCharIndex = _clamp(self.cpr[1], 0, SBIX_UINT16_MAX)

        advances = [aw for (aw, _lsb) in self.hmtx.values() if aw is not None]
        if advances:
            mean_advance = int(round(sum(advances) / len(advances)))
            self.font["OS/2"].xAvgCharWidth = _clamp(mean_advance, SBIX_INT16_MIN, SBIX_INT16_MAX)

    def save(self, output_file):
        """Saves the assembled font to an output file."""
        self.font.save(output_file)
