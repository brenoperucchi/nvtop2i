"""Terminal UI for gnvitop: an nvtop-like view of several hosts, using curses.

Layout code is pure: build_screen() returns lines made of (text, role)
segments, and _paint() maps the roles to curses attributes. That keeps the
layout testable without a terminal.
"""

import curses
import os
import threading
import time
from collections import namedtuple

from .tui_state import History, UIState, SORT_KEYS, process_rows, sparkline

FULL_MIN_WIDTH = 100     # narrower terminals use the compact view
TABLE_MIN_LINES = 5      # border + header + one row + border + gap
BAR = "|"

Screen = namedtuple("Screen", "lines hosts rows compact")


# ── formatting helpers ───────────────────────────────────────────────────────

def _fmt_mb(mb):
    if mb >= 1024:
        return f"{mb / 1024:.1f}G"
    return f"{int(mb)}M"


def _fmt_mem_col(mb):
    if mb >= 1024:
        return f"{mb / 1024:.1f}GiB"
    return f"{int(mb)}MiB"


def _fmt_gi(mb, digits=3):
    return f"{mb / 1024:.{digits}f}Gi"


def _fmt_rate(mbs):
    return "--" if mbs is None else f"{mbs:.1f} MB/s"


def _usage_role(pct):
    """green below 50 %, yellow up to 80 %, red above (same as nvtop)."""
    if pct is None:
        return "white"
    if pct < 50:
        return "green"
    if pct <= 80:
        return "yellow"
    return "red"


def _temp_role(temp):
    if temp is None:
        return "white"
    if temp < 60:
        return "green"
    if temp <= 80:
        return "yellow"
    return "red"


def _short_name(name):
    for prefix in ("NVIDIA ", "GeForce ", "RTX "):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def _seg_len(segs):
    return sum(len(t) for t, _ in segs)


def _fit(segs, width):
    """Cut a line of segments to `width` characters."""
    out, used = [], 0
    for text, role in segs:
        if used >= width:
            break
        if used + len(text) > width:
            text = text[:width - used]
        out.append((text, role))
        used += len(text)
    return out


def _left_right(left, right, width):
    """Left segments, then right segments flush to the right edge."""
    gap = width - _seg_len(left) - _seg_len(right)
    if gap < 1:
        return _fit(left, width)
    return left + [(" " * gap, "white")] + right


def _bar_segs(prefix, pct, inner, label, role):
    """`GPU[|||||     37%]`: the label sits inside the bar, right aligned."""
    inner = max(inner, 1)
    pct = 0 if pct is None else min(100.0, max(0.0, pct))
    filled = int(pct / 100 * inner)
    chars = [BAR] * filled + [" "] * (inner - filled)
    start = max(0, inner - len(label))
    for i, ch in enumerate(label[:inner]):
        chars[start + i] = ch
    segs = [(prefix + "[", "white")]
    # bar characters keep the bar colour, the label is drawn bold white
    run, run_role = "", None
    for i, ch in enumerate(chars):
        r = "value" if i >= start and i - start < len(label) else (role if i < filled else "white")
        if r != run_role and run:
            segs.append((run, run_role))
            run = ""
        run_role = r
        run += ch
    if run:
        segs.append((run, run_role))
    segs.append(("]", "white"))
    return segs


def _badge(host):
    status = host["status"]
    if host.get("is_local"):
        return "[Local]", "badge_local"
    if status == "ok":
        return "[Online]", "badge_ok"
    if status == "no_gpu":
        return "[No GPU]", "badge_nogpu"
    return "[Offline]", "badge_off"


# ── GPU blocks ───────────────────────────────────────────────────────────────

def _has_nvtop_fields(gpu):
    return "clock_gr_mhz" in gpu


def _gpu_full(alias, gpu, history, width):
    """Four-line nvtop-style block for one GPU."""
    idx = gpu["index"]
    util = gpu.get("gpu_utilization_pct")
    mem_pct = gpu.get("memory_usage_pct")
    temp = gpu.get("temperature_c")

    if gpu.get("pcie_gen") is not None:
        link = f"PCIe GEN {gpu['pcie_gen']}@{gpu.get('pcie_width') or '--':>2}x"
    else:
        link = "PCIe --"
    right = [(link + "  ", "white"),
             ("RX: " + _fmt_rate(gpu.get("pcie_rx_mbs")) + "  ", "white"),
             ("TX: " + _fmt_rate(gpu.get("pcie_tx_mbs")), "white")]
    left = [(f" Device {idx} ", "bold"), (f"[{gpu['name']}]", "cyan")]
    line1 = _left_right(left, right, width - 1)

    def mhz(v):
        return "--" if v is None else f"{v:.0f}MHz"

    power, limit = gpu.get("power_w"), gpu.get("power_limit_w")
    power_pct = (power / limit * 100) if power is not None and limit else None
    fan = gpu.get("fan_pct")
    line2 = [
        (" GPU ", "white"), (f"{mhz(gpu.get('clock_gr_mhz')):<8}", "bold"),
        (" MEM ", "white"), (f"{mhz(gpu.get('clock_mem_mhz')):<8}", "bold"),
        (" TEMP ", "white"), (f"{temp:.0f}°C" if temp is not None else "--", _temp_role(temp)),
        ("  FAN ", "white"), (f"{fan:.0f}%" if fan is not None else "--", "bold"),
        ("  POW ", "white"),
        (f"{power:.0f}" if power is not None else "--", _usage_role(power_pct)),
        (" / ", "white"),
        (f"{limit:.0f} W" if limit is not None else "-- W", "bold"),
    ]

    inner = max(10, min(80, (width - 1 - 10 - 2 - 1) // 2))
    mem_label = f"{_fmt_gi(gpu['memory_used_mb'])}/{_fmt_gi(gpu['memory_total_mb'])}"
    if len(mem_label) + 4 > inner:
        mem_label = f"{_fmt_gi(gpu['memory_used_mb'], 1)}/{_fmt_gi(gpu['memory_total_mb'], 1)}"
    line3 = ([(" ", "white")]
             + _bar_segs("GPU", util, inner, f"{(util or 0):.0f}%", _usage_role(util))
             + [("  ", "white")]
             + _bar_segs("MEM", mem_pct, inner, mem_label, _usage_role(mem_pct)))

    fixed = len(" hist GPU   MEM   TEMP ")
    sw = max(8, min(40, (width - 1 - fixed) // 3))
    gs = history.series(alias, idx, "gpu")
    ms = history.series(alias, idx, "mem")
    ts = history.series(alias, idx, "temp")
    line4 = [
        (" hist GPU ", "white"), (sparkline(gs, sw), _usage_role(gs[-1] if gs else None)),
        ("  MEM ", "white"), (sparkline(ms, sw), _usage_role(ms[-1] if ms else None)),
        ("  TEMP ", "white"),
        (sparkline(ts, sw, lo=20, hi=100), _temp_role(ts[-1] if ts else None)),
    ]
    return [_fit(line1, width - 1), _fit(line2, width - 1),
            _fit(line3, width - 1), _fit(line4, width - 1)]


def _gpu_compact(alias, gpu, history, width, host_w):
    """One line for one GPU (mockup B). Optional parts drop out when narrow."""
    idx = gpu["index"]
    util = gpu.get("gpu_utilization_pct")
    mem_pct = gpu.get("memory_usage_pct")
    temp = gpu.get("temperature_c")
    head = f" {alias[:host_w]:<{host_w}}  {idx} {_short_name(gpu['name'])[:10]:<10} "
    temp_s = f" {temp:.0f}°C" if temp is not None else " --"

    power, limit, fan = gpu.get("power_w"), gpu.get("power_limit_w"), gpu.get("fan_pct")
    extra = ""
    if fan is not None or power is not None:
        extra = " " + (f"{fan:.0f}%" if fan is not None else "--")
        extra += " " + (f"{power:.0f}/{limit:.0f}W" if power is not None and limit else "")
    gs = history.series(alias, idx, "gpu")
    spark_w = 8

    def inner_for(opt_len):
        return (width - 1 - len(head) - len(temp_s) - opt_len - 10 - 1) // 2

    opt_extra, opt_spark = len(extra), spark_w + 1
    inner = inner_for(opt_extra + opt_spark)
    use_extra, use_spark = bool(extra), True
    if inner < 12:
        use_spark = False
        inner = inner_for(opt_extra)
    if inner < 12:
        use_extra = False
        inner = inner_for(0)
    inner = max(inner, 4)

    mem_label = f"{gpu['memory_used_mb'] / 1024:.1f}/{gpu['memory_total_mb'] / 1024:.0f}G"
    if len(mem_label) + 3 > inner:
        mem_label = f"{gpu['memory_usage_pct']:.0f}%"
    segs = ([(head, "white")]
            + _bar_segs("GPU", util, inner, f"{(util or 0):.0f}%", _usage_role(util))
            + [(" ", "white")]
            + _bar_segs("MEM", mem_pct, inner, mem_label, _usage_role(mem_pct))
            + [(temp_s, _temp_role(temp))])
    if use_extra:
        segs.append((extra, "white"))
    if use_spark:
        segs.append((" " + sparkline(gs, spark_w), _usage_role(gs[-1] if gs else None)))
    return _fit(segs, width - 1)


def _host_header(host, selected, collapsed, width):
    badge, role = _badge(host)
    arrow = "▸" if collapsed else "▾"
    segs = [(f" {arrow} ", "white"),
            (host["alias"], "host_sel" if selected else "bold"),
            (" ", "white"), (badge, role)]
    if host["status"] == "error":
        segs.append(("  " + str(host.get("error") or "unknown error"), "red"))
    elif host["status"] == "no_gpu" and host.get("error"):
        segs.append(("  " + str(host["error"]), "dim"))
    return _fit(segs, width - 1)


# ── process table ────────────────────────────────────────────────────────────

def _table(rows, state, width, max_lines):
    """Boxed process table; scrolls so the selected row stays visible."""
    headers = ("HOST", "GPU", "PID", "USER", "TYPE", "GPU MEM", "GPU%")
    cells = [(r["host"], str(r["gpu"]), str(r["pid"]), r["user"], r["type"],
              _fmt_mem_col(r["mem_mb"]),
              "-" if r["sm_pct"] is None else f"{r['sm_pct']:.0f}%") for r in rows]
    widths = [max([len(h)] + [len(c[i]) for c in cells]) for i, h in enumerate(headers)]
    widths = [min(w_, cap) for w_, cap in zip(widths, (14, 3, 8, 14, 4, 8, 4))]
    inner_w = width - 3
    used = sum(widths) + 2 * len(widths) + 1
    cmd_w = max(7, inner_w - used)

    def fmt_row(vals, cmd):
        out = ""
        for i, v in enumerate(vals):
            out += (f"{v:>{widths[i]}}" if i in (5, 6) else f"{v:<{widths[i]}}") + " "
        return " " + out + " " + cmd

    def boxed(text, role):
        body = text[:inner_w].ljust(inner_w)
        return [("│" + body + "│", role)]

    lines = [[("┌" + "─" * inner_w + "┐", "dim")],
             boxed(fmt_row(headers, "COMMAND"), "hdr")]
    visible = max(0, max_lines - 3)
    start = 0
    if len(rows) > visible:
        start = min(max(0, state.proc_index - visible + 1), len(rows) - visible)
    for i in range(start, min(len(rows), start + visible)):
        role = "sel" if i == state.proc_index else "white"
        lines.append(boxed(fmt_row(cells[i], rows[i]["command"][:cmd_w]), role))
    if not rows:
        lines.append(boxed("  no GPU processes", "dim"))
    lines.append([("└" + "─" * inner_w + "┘", "dim")])
    return [_fit(ln, width - 1) for ln in lines]


# ── screen assembly ──────────────────────────────────────────────────────────

def _footer(state, width):
    sort = f"F3 Sort:{state.sort_key}"
    if state.filtering:
        segs = [(" Filter: ", "bold"), (state.filter_text + "_", "yellow"),
                ("   Enter apply  Esc clear", "dim")]
        return _fit(segs, width - 1)
    flt = f"F4 Filter:{state.filter_text}" if state.filter_text else "F4 Filter"
    segs = [(f" F2 Hosts  {sort}  {flt}  ", "white"), ("F5 Kill", "dim"),
            (f"  F6 Interval:{state.refresh_interval}s  F8 Compact  F10 Quit", "white"),
            ("    ←/→ host  ↑/↓ process", "dim")]
    return _fit(segs, width - 1)


def _gpu_section(results, history, state, width, compact):
    lines = []
    host_w = min(14, max([len(h["alias"]) for h in results] + [4]))
    for hi, host in enumerate(results):
        collapsed = host["alias"] in state.collapsed
        ok = host["status"] == "ok"
        if not compact or not ok:
            lines.append(_host_header(host, hi == state.host_index, collapsed, width))
        if not ok or collapsed:
            if not compact:
                lines.append([])
            continue
        for gpu in host["gpus"]:
            if compact or not _has_nvtop_fields(gpu):
                lines.append(_gpu_compact(host["alias"], gpu, history, width, host_w))
            else:
                lines.extend(_gpu_full(host["alias"], gpu, history, width))
                lines.append([])
        if not compact and not (host["gpus"] and _has_nvtop_fields(host["gpus"][-1])):
            lines.append([])
    return lines


def build_screen(results, history, state, width, height, meta):
    """Lay out the whole screen as lines of (text, role) segments."""
    width = max(20, width)
    state.host_aliases = [h["alias"] for h in results]
    state.host_index = min(state.host_index, max(0, len(results) - 1))
    gpu_count = sum(len(h.get("gpus", [])) for h in results if h["status"] == "ok")
    left = [(f" gnvitop  {gpu_count} GPUs on {len(results)} hosts", "title")]
    if meta.get("loading") and not meta.get("last_update"):
        right_txt = f"refresh {state.refresh_interval}s   updating..."
    else:
        ts = time.strftime("%H:%M:%S", time.localtime(meta.get("last_update") or time.time()))
        right_txt = f"refresh {state.refresh_interval}s   updated {ts}"
    top = [_left_right(left, [(right_txt, "white")], width - 1),
           [("─" * (width - 2), "dim")], []]

    if not results:
        body = [[(" Waiting for data...", "yellow")]]
        compact = state.compact
        return Screen(top + body + [[]] * max(0, height - len(top) - 3) + [_footer(state, width)],
                      0, [], compact)

    compact = state.compact or width < FULL_MIN_WIDTH
    body = _gpu_section(results, history, state, width, compact)
    if not compact and len(top) + len(body) > height - 1 - TABLE_MIN_LINES:
        compact = True   # the full view does not fit: fall back to one line per GPU
        body = _gpu_section(results, history, state, width, compact)

    rows = process_rows(results, state)
    if rows:
        state.proc_index = min(state.proc_index, len(rows) - 1)
    else:
        state.proc_index = 0
    lines = top + body
    room = height - 1 - len(lines)
    if room >= TABLE_MIN_LINES:
        lines += _table(rows, state, width, room)
    while len(lines) < height - 1:
        lines.append([])
    lines = lines[:height - 1] + [_footer(state, width)]
    return Screen(lines, len(results), rows, compact)


# ── curses layer ─────────────────────────────────────────────────────────────

def _init_attrs():
    curses.start_color()
    curses.use_default_colors()
    pairs = [(1, curses.COLOR_GREEN), (2, curses.COLOR_YELLOW), (3, curses.COLOR_RED),
             (4, curses.COLOR_CYAN), (5, curses.COLOR_WHITE), (6, curses.COLOR_BLUE),
             (7, curses.COLOR_MAGENTA), (8, curses.COLOR_BLACK + 8 if curses.COLORS > 8
                                         else curses.COLOR_BLACK)]
    for n, color in pairs:
        curses.init_pair(n, color, -1)
    cp = curses.color_pair
    bold = curses.A_BOLD
    return {
        "green": cp(1), "yellow": cp(2), "red": cp(3), "cyan": cp(4), "white": 0,
        "dim": cp(8), "bold": bold, "value": bold, "hdr": bold | curses.A_UNDERLINE,
        "title": cp(4) | bold, "sel": curses.A_REVERSE,
        "host_sel": bold | curses.A_UNDERLINE,
        "badge_ok": cp(1) | bold, "badge_local": cp(6) | bold,
        "badge_nogpu": cp(2) | bold, "badge_off": cp(3) | bold,
    }


def _paint(stdscr, screen, attrs):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    for row, segs in enumerate(screen.lines[:h]):
        col = 0
        for text, role in segs:
            if col >= w - 1:
                break
            try:
                stdscr.addstr(row, col, text[:w - 1 - col], attrs.get(role, 0))
            except curses.error:
                pass   # writing the last cell of the last row raises; harmless
            col += len(text)
    stdscr.refresh()


INTERVALS = (1, 2, 5, 10, 30)


def _handle_key(key, state, screen):
    """Apply one key to the UI state. Returns 'quit', 'refresh' or None."""
    if state.filtering:
        if key in (10, 13, curses.KEY_ENTER):
            state.filtering = False
        elif key == 27:
            state.filtering = False
            state.filter_text = ""
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            state.filter_text = state.filter_text[:-1]
        elif 32 <= key < 127:
            state.filter_text += chr(key)
        return None
    if key in (ord("q"), ord("Q"), 27, curses.KEY_F10):
        return "quit"
    if key in (ord("r"), ord("R")):
        return "refresh"
    if key == curses.KEY_F2:
        state.toggle_collapsed_at(state.host_index)
    elif key == curses.KEY_F3:
        state.cycle_sort()
    elif key == curses.KEY_F4:
        state.filtering = True
    elif key == curses.KEY_F6:
        i = INTERVALS.index(state.refresh_interval) if state.refresh_interval in INTERVALS else -1
        state.refresh_interval = INTERVALS[(i + 1) % len(INTERVALS)]
        return "interval"
    elif key == curses.KEY_F8:
        state.compact = not state.compact
    elif key == curses.KEY_LEFT:
        state.move_host(-1, screen.hosts)
    elif key == curses.KEY_RIGHT:
        state.move_host(1, screen.hosts)
    elif key == curses.KEY_UP:
        state.move_proc(-1, len(screen.rows))
    elif key == curses.KEY_DOWN:
        state.move_proc(1, len(screen.rows))
    return None


def _tui_main(stdscr, fetch_fn, refresh_interval):
    curses.curs_set(0)
    attrs = _init_attrs()
    state = UIState(refresh_interval)
    history = History()

    data = []
    meta = {"last_update": 0.0, "loading": True}
    lock = threading.Lock()

    def do_fetch():
        with lock:
            meta["loading"] = True
        result = fetch_fn()
        with lock:
            data[:] = result
            history.record(result)
            meta["last_update"] = time.time()
            meta["loading"] = False

    threading.Thread(target=do_fetch, daemon=True).start()
    next_refresh = time.time() + state.refresh_interval
    stdscr.keypad(True)
    stdscr.timeout(250)
    screen = Screen([], 0, [], False)

    while True:
        key = stdscr.getch()
        action = _handle_key(key, state, screen) if key != -1 else None
        if action == "quit":
            break
        with lock:
            busy = meta["loading"]
        if action == "interval":
            next_refresh = time.time() + state.refresh_interval
        if (action == "refresh" or time.time() >= next_refresh) and not busy:
            threading.Thread(target=do_fetch, daemon=True).start()
            next_refresh = time.time() + state.refresh_interval

        h, w = stdscr.getmaxyx()
        with lock:
            snapshot, snap_meta = list(data), dict(meta)
            screen = build_screen(snapshot, history, state, w, h, snap_meta)
        _paint(stdscr, screen, attrs)


def run_tui(ssh_config_path=None, refresh_interval=2):
    """Launch the curses TUI dashboard."""
    import gnvitop.server as srv
    if ssh_config_path:
        srv.SSH_CONFIG_PATH = ssh_config_path

    from .server import fetch_all_gpu_info

    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(_tui_main, fetch_all_gpu_info, refresh_interval)
    except KeyboardInterrupt:
        pass
