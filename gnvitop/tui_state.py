"""Pure state for the TUI: sample history, sparklines, process rows, UI flags.

Nothing here touches curses, so it can be tested without a terminal.
"""

import threading
from collections import deque

HISTORY_LEN = 40
SPARK_CHARS = "▁▂▃▄▅▆▇█"  # ▁ .. █

SORT_KEYS = ("mem", "gpu", "pid", "user", "host")


def sparkline(values, width, lo=0.0, hi=100.0):
    """Render the last `width` values as block characters, right padded to `width`.

    A short history grows from the left and scrolls once it fills the width.

    Missing samples (None) are drawn as a space. Values outside lo..hi are clamped.
    """
    if width <= 0:
        return ""
    tail = list(values)[-width:]
    span = (hi - lo) or 1.0
    top = len(SPARK_CHARS) - 1
    out = []
    for v in tail:
        if v is None:
            out.append(" ")
            continue
        frac = min(1.0, max(0.0, (v - lo) / span))
        out.append(SPARK_CHARS[int(round(frac * top))])
    return "".join(out).ljust(width)


class History:
    """GPU%, MEM% and temperature samples per (host alias, gpu index).

    Workers add samples from their own threads while the UI reads them.
    """

    def __init__(self, maxlen=HISTORY_LEN):
        self.maxlen = maxlen
        self._series = {}
        self._lock = threading.Lock()

    def record_host(self, host):
        """Add one sample for every GPU of a host that answered."""
        if host.get("status") != "ok":
            return
        with self._lock:
            for gpu in host.get("gpus", []):
                key = (host["alias"], gpu["index"])
                s = self._series.setdefault(key, {
                    "gpu": deque(maxlen=self.maxlen),
                    "mem": deque(maxlen=self.maxlen),
                    "temp": deque(maxlen=self.maxlen),
                })
                s["gpu"].append(gpu.get("gpu_utilization_pct"))
                s["mem"].append(gpu.get("memory_usage_pct"))
                s["temp"].append(gpu.get("temperature_c"))

    def record(self, results):
        for host in results:
            self.record_host(host)

    def series(self, alias, index, name):
        with self._lock:
            s = self._series.get((alias, index))
            return list(s[name]) if s else []


class UIState:
    """Flags the user changes with the keyboard."""

    def __init__(self, refresh_interval=2):
        self.refresh_interval = refresh_interval
        self.collapsed = set()   # host aliases folded with F2
        self.compact = False     # F8
        self.sort_key = "mem"    # F3 cycles SORT_KEYS
        self.filter_text = ""    # F4
        self.host_index = 0      # left/right
        self.proc_index = 0      # up/down
        self.filtering = False   # typing into the F4 filter
        self.host_aliases = []   # aliases in display order, set by the renderer

    def toggle_collapsed(self, alias):
        if alias in self.collapsed:
            self.collapsed.remove(alias)
        else:
            self.collapsed.add(alias)

    def toggle_collapsed_at(self, index):
        if 0 <= index < len(self.host_aliases):
            self.toggle_collapsed(self.host_aliases[index])

    def cycle_sort(self):
        i = SORT_KEYS.index(self.sort_key)
        self.sort_key = SORT_KEYS[(i + 1) % len(SORT_KEYS)]

    def move_host(self, delta, host_count):
        if host_count <= 0:
            self.host_index = 0
        else:
            self.host_index = (self.host_index + delta) % host_count

    def move_proc(self, delta, proc_count):
        if proc_count <= 0:
            self.proc_index = 0
        else:
            self.proc_index = max(0, min(proc_count - 1, self.proc_index + delta))


def process_rows(results, state):
    """Flat, filtered and sorted process rows for the table.

    Hosts folded in the UI are left out. The filter matches host, user or command,
    ignoring case.
    """
    rows = []
    for host in results:
        if host.get("status") != "ok" or host["alias"] in state.collapsed:
            continue
        for gpu in host.get("gpus", []):
            for p in gpu.get("processes", []):
                rows.append({
                    "host": host["alias"],
                    "gpu": gpu["index"],
                    "pid": p.get("pid", 0),
                    "user": p.get("user", "?"),
                    "type": p.get("type", "") or "",
                    "mem_mb": p.get("gpu_memory_mb", 0) or 0,
                    "sm_pct": p.get("sm_pct"),
                    "command": p.get("command", ""),
                })
    needle = state.filter_text.strip().lower()
    if needle:
        rows = [r for r in rows
                if needle in r["host"].lower() or needle in r["user"].lower()
                or needle in r["command"].lower()]
    key = state.sort_key
    if key == "mem":
        rows.sort(key=lambda r: -r["mem_mb"])
    elif key == "gpu":
        rows.sort(key=lambda r: -(r["sm_pct"] if r["sm_pct"] is not None else -1))
    elif key == "pid":
        rows.sort(key=lambda r: r["pid"])
    elif key == "user":
        rows.sort(key=lambda r: (r["user"], -r["mem_mb"]))
    else:
        rows.sort(key=lambda r: (r["host"], r["gpu"], -r["mem_mb"]))
    return rows
