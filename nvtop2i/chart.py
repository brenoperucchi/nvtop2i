"""Braille step charts for the graph view. Pure functions, no curses."""

# Dot bits of a braille cell: (column, row from the top) -> bit.
_BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))


def step_masks(values, cols, rows, lo=0.0, hi=100.0):
    """Braille masks (rows x cols) for a step line through the last 2*cols values.

    The newest value sits at the right edge; a short history leaves the left side
    empty. None draws nothing at that x. Values outside lo..hi are clamped.
    """
    masks = [[0] * cols for _ in range(rows)]
    if cols <= 0 or rows <= 0:
        return masks
    dots_y = rows * 4
    span = (hi - lo) or 1.0
    tail = list(values)[-cols * 2:]
    offset = cols * 2 - len(tail)
    prev = None
    for i, v in enumerate(tail):
        if v is None:
            prev = None
            continue
        frac = min(1.0, max(0.0, (v - lo) / span))
        y = dots_y - 1 - int(round(frac * (dots_y - 1)))   # 0 is the top dot row
        x = offset + i
        lo_y, hi_y = (y, y) if prev is None else (min(prev, y), max(prev, y))
        for yy in range(lo_y, hi_y + 1):
            masks[yy // 4][x // 2] |= _BITS[x % 2][yy % 4]
        prev = y
    return masks


def combine(layers):
    """Merge mask layers into (char, layer index) cells; the first layer wins colour."""
    rows, cols = len(layers[0]), len(layers[0][0]) if layers[0] else 0
    out = []
    for r in range(rows):
        line = []
        for c in range(cols):
            mask, owner = 0, 0
            for li, layer in enumerate(layers):
                if layer[r][c]:
                    if not mask:
                        owner = li
                    mask |= layer[r][c]
            line.append((chr(0x2800 + mask) if mask else " ", owner))
        out.append(line)
    return out
