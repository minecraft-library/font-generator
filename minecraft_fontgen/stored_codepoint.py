"""Deterministic stored-codepoint allocation for the single-file colour font.

The colour track collapses to one .ttf per pack, but different pack font ids reuse
the same private-use codepoints for different art (a 2345-pair collision census on
the reference packs). One cmap cannot key on those original codepoints, so every
(font_id, original_codepoint) raster pair is assigned a synthetic STORED codepoint
here. The stored codepoint is what the merged font's cmap actually carries; the
original codepoint survives only in the sidecar, which bridges pack + original
codepoint back to the stored codepoint (and the authoritative gid).

Allocation is deterministic per build: the pairs are sorted lexicographically by
(font_id, original_codepoint) and assigned linearly from U+F0000 onward. The same
input yields a byte-identical font and sidecar; across pack updates the assignment
may shift, which is why the font and sidecar ship as a matched pair.
"""
from minecraft_fontgen.config import STORED_CP_START, STORED_CP_END


def _is_noncharacter(codepoint):
    """A Unicode noncharacter (U+xFFFE / U+xFFFF in every plane) is never assigned:
    some cmap tooling and renderers reject them, and skipping them costs nothing."""
    return (codepoint & 0xFFFF) in (0xFFFE, 0xFFFF)


def allocate_stored_codepoints(pairs):
    """Maps each (font_id, original_codepoint) pair to a stored codepoint.

    `pairs` is any iterable of (font_id, codepoint) tuples; the result is a dict
    keyed by that tuple. Pairs are sorted lexicographically and assigned in order
    from U+F0000 into plane 16, skipping noncharacters. Deterministic and total:
    identical input always produces the identical mapping.

    Raises SystemExit-free ValueError only when the plane-15+16 budget (131068
    codepoints) is exhausted, which is 40x+ the reference packs' pair counts."""
    assignment = {}
    cursor = STORED_CP_START
    for key in sorted(pairs):
        while _is_noncharacter(cursor):
            cursor += 1
        if cursor > STORED_CP_END:
            raise ValueError(
                f"Stored-codepoint budget exhausted: more than {plane_budget()} "
                f"(font_id, codepoint) raster pairs cannot fit planes 15-16.")
        assignment[key] = cursor
        cursor += 1
    return assignment


def plane_budget():
    """Returns the number of assignable stored codepoints across planes 15 and 16
    (the inclusive window minus the four skipped noncharacters: U+FFFE/F and
    U+10FFFE/F). 131072 - 4 = 131068 on the default window."""
    total = STORED_CP_END - STORED_CP_START + 1
    noncharacters = sum(1 for cp in range(STORED_CP_START, STORED_CP_END + 1)
                        if _is_noncharacter(cp))
    return total - noncharacters
