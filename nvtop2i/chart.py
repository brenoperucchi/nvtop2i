"""Step charts drawn with line characters, like nvtop's history graph. Pure functions."""

from bisect import bisect_right

WINDOW_S = 60


def step_cells(samples, now, cols, rows, window=WINDOW_S, hold=None, lo=0.0, hi=100.0):
    """Grid (rows x cols) of characters for one series.

    `samples` is a list of (timestamp, value) in time order. Column 0 is `window`
    seconds before `now`, the last column is `now`. A sample is held until the next
    one arrives, but not longer than `hold` seconds (None: no limit), so a host
    that went quiet leaves a gap instead of a flat line. Missing values draw nothing.
    """
    grid = [[" "] * cols for _ in range(rows)]
    if cols <= 0 or rows <= 0 or not samples:
        return grid
    times = [t for t, _ in samples]
    span = (hi - lo) or 1.0
    prev = None   # row of the previous column
    for c in range(cols):
        t = now - window * (cols - 1 - c) / max(1, cols - 1)
        i = bisect_right(times, t) - 1
        value = None
        if i >= 0 and samples[i][1] is not None and (hold is None or t - times[i] <= hold):
            value = samples[i][1]
        if value is None:
            prev = None
            continue
        frac = min(1.0, max(0.0, (value - lo) / span))
        y = int(round((1 - frac) * (rows - 1)))
        if prev is None or prev == y:
            grid[y][c] = "─"
        else:
            top, bottom = min(prev, y), max(prev, y)
            for r in range(top + 1, bottom):
                grid[r][c] = "│"
            if y < prev:   # going up: the old level turns up, the new one continues right
                grid[prev][c], grid[y][c] = "┘", "┌"
            else:
                grid[prev][c], grid[y][c] = "┐", "└"
        prev = y
    return grid


def overlay(layers):
    """Merge grids into (char, layer index) cells.

    When several layers want the same cell, they take turns column by column, so
    two lines on the same level stay visible as a two-coloured dashed line.
    """
    rows = len(layers[0])
    cols = len(layers[0][0]) if rows else 0
    out = []
    for r in range(rows):
        line = []
        for c in range(cols):
            used = [li for li, layer in enumerate(layers) if layer[r][c] != " "]
            if used:
                li = used[c % len(used)]
                line.append((layers[li][r][c], li))
            else:
                line.append((" ", 0))
        out.append(line)
    return out
