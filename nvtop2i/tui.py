"""Terminal UI for nvtop2i: an nvtop-like view of several hosts, using curses.

Layout code is pure: build_screen() returns lines made of (text, role)
segments, and _paint() maps the roles to curses attributes. That keeps the
layout testable without a terminal.
"""

import curses
import os
import time
from collections import namedtuple

from .chart import WINDOW_S, overlay, step_cells
from .tui_state import History, UIState, process_rows, sparkline

FULL_MIN_WIDTH = 100     # narrower terminals use the compact view
CHART_MIN_LINES = 5      # border + 3 plot rows + border
CHART_MAX_LINES = 18
TABLE_MIN_LINES = 5      # border + header + one row + border + gap
BAR = "|"

from . import __version__

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
    if status == "connecting":
        return "[Connecting]", "badge_nogpu"
    return "[Offline]", "badge_off"


# ── GPU blocks ───────────────────────────────────────────────────────────────

def _has_nvtop_fields(gpu):
    return "clock_gr_mhz" in gpu


def _sys_line(host, width):
    """`CPU 48°C  LOAD 0.8  CPU[||   12%]  MEM[|||   23.1Gi/62.7Gi]`, or None without data."""
    s = host.get("sys")
    if not s or ("mem_total_mb" not in s and "cpu_pct" not in s):
        return None
    cpu, temp, load = s.get("cpu_pct"), s.get("cpu_temp_c"), s.get("load1")
    segs = [(" ", "white")]
    if temp is not None:
        segs += [("CPU ", "white"), (f"{temp:.0f}°C", _temp_role(temp)), ("  ", "white")]
    if load is not None:
        segs += [("LOAD ", "white"), (f"{load:.1f}", "bold"), ("  ", "white")]
    has_mem = "mem_total_mb" in s and "mem_used_mb" in s
    mem_label = (f"{_fmt_gi(s['mem_used_mb'], 1)}/{_fmt_gi(s['mem_total_mb'], 1)}"
                 if has_mem else "")
    used = sum(len(t) for t, _ in segs)
    # two bars share what is left, like the GPU and MEM bars of a GPU block
    left = width - 1 - used - (2 if has_mem else 0) - (10 if has_mem else 5)
    inner = max(len(mem_label) + 2, min(60, left // (2 if has_mem else 1)))
    segs += _bar_segs("CPU", cpu, inner, f"{cpu:.0f}%" if cpu is not None else "--",
                      _usage_role(cpu))
    if has_mem:
        segs += [("  ", "white")] + _bar_segs("MEM", s["mem_pct"], inner, mem_label,
                                              _usage_role(s["mem_pct"]))
    return _fit(segs, width - 1)


def _gpu_full(alias, gpu, history, width, chart_h=0, interval=2, show_temp=False):
    """nvtop-style block for one GPU: three header lines, then the sparkline
    row, or a chart box of `chart_h` lines when chart_h > 0."""
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
    fault = gpu.get("fault")
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
    if fault:
        # the driver cannot read the card: say so instead of a row of "--"
        line2 = [(" ", "white"), (f"! {fault}", "red"),
                 ("  (clocks, fan, power and load cannot be read)", "white"),
                 ("  TEMP ", "white"), (f"{temp:.0f}°C" if temp is not None else "--", _temp_role(temp))]

    inner = max(10, min(80, (width - 1 - 10 - 2 - 1) // 2))
    mem_label = f"{_fmt_gi(gpu['memory_used_mb'])}/{_fmt_gi(gpu['memory_total_mb'])}"
    if len(mem_label) + 4 > inner:
        mem_label = f"{_fmt_gi(gpu['memory_used_mb'], 1)}/{_fmt_gi(gpu['memory_total_mb'], 1)}"
    line3 = ([(" ", "white")]
             + _bar_segs("GPU", util, inner, f"{(util or 0):.0f}%", _usage_role(util))
             + [("  ", "white")]
             + _bar_segs("MEM", mem_pct, inner, mem_label, _usage_role(mem_pct)))

    head = [_fit(line1, width - 1), _fit(line2, width - 1), _fit(line3, width - 1)]
    if chart_h > 0:
        return head + _chart(history, alias, idx, width, chart_h, interval, temp=show_temp)
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
    return head + [_fit(line4, width - 1)]


def _chart(history, alias, idx, width, height, interval, now=None, temp=False):
    """nvtop-style box: the last 60 s of GPU% and mem% as thin step lines."""
    now = time.time() if now is None else now
    label_w = 4
    inner = width - 1 - label_w - 2
    rows = height - 2
    hold = 3 * interval + 1
    layers = [step_cells(history.timed(alias, idx, "gpu"), now, inner, rows, hold=hold),
              step_cells(history.timed(alias, idx, "mem"), now, inner, rows, hold=hold)]
    roles = ("chart_gpu", "chart_mem")
    if temp:   # degrees C share the 0-100 axis
        layers.append(step_cells(history.timed(alias, idx, "temp"), now, inner, rows, hold=hold))
        roles += ("chart_temp",)
    cells = overlay(layers)
    levels = (100, 75, 50, 25, 0) if rows >= 5 else (100, 50, 0)
    ticks = {round(k * (rows - 1) / (len(levels) - 1)): str(v) for k, v in enumerate(levels)}
    legend = {0: f" GPU{idx} %", 1: f" GPU{idx} mem%"} if rows >= 4 else {}
    if temp and rows >= 4:
        legend[2] = f" GPU{idx} temp C"

    lines = [[(" " * label_w + "┌" + "─" * inner + "┐", "dim")]]
    for r in range(rows):
        row = [list(c) for c in cells[r]]
        text = legend.get(r, "")
        role_of = roles[r] if r < len(roles) else "white"
        segs = [(f"{ticks.get(r, ''):>{label_w - 1}} ", "white"), ("│", "dim")]
        run, run_role = "", None
        for c, (ch, owner) in enumerate(row):
            if c < len(text):
                ch, role = text[c], role_of
            else:
                role = roles[owner] if ch != " " else "white"
            if role != run_role and run:
                segs.append((run, run_role))
                run = ""
            run_role = role
            run += ch
        segs.append((run, run_role))
        segs.append(("│", "dim"))
        lines.append(segs)

    axis = ["─"] * inner
    for k in range(5):
        text = f"{int(WINDOW_S - 1) * (4 - k) // 4}s"
        start = round(k * (inner - 1) / 4)
        start = min(max(0, start - (len(text) - 1 if k == 4 else 0)), max(0, inner - len(text)))
        axis[start:start + len(text)] = list(text)
    lines.append([(" " * label_w + "└", "dim"), ("".join(axis), "white"), ("┘", "dim")])
    return [_fit(ln, width - 1) for ln in lines]


def _gpu_compact(alias, gpu, history, width, host_w, selected=False):
    """One line for one GPU (mockup B). Optional parts drop out when narrow."""
    idx = gpu["index"]
    util = gpu.get("gpu_utilization_pct")
    mem_pct = gpu.get("memory_usage_pct")
    temp = gpu.get("temperature_c")
    head_alias = alias[:host_w].ljust(host_w)
    head_rest = f"  {idx} {_short_name(gpu['name'])[:10]:<10} "
    head = " " + head_alias + head_rest
    temp_s = f" {temp:.0f}°C" if temp is not None else " --"

    power, limit, fan = gpu.get("power_w"), gpu.get("power_limit_w"), gpu.get("fan_pct")
    extra = ""
    if gpu.get("fault"):
        extra = " ! " + gpu["fault"].replace("GPU ", "", 1)
    elif fan is not None or power is not None:
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
    segs = ([(" ", "white"), (head_alias, "host_sel" if selected else "white"),
             (head_rest, "white")]
            + _bar_segs("GPU", util, inner, f"{(util or 0):.0f}%", _usage_role(util))
            + [(" ", "white")]
            + _bar_segs("MEM", mem_pct, inner, mem_label, _usage_role(mem_pct))
            + [(temp_s, _temp_role(temp))])
    if use_extra:
        segs.append((extra, "white"))
    if use_spark:
        segs.append((" " + sparkline(gs, spark_w), _usage_role(gs[-1] if gs else None)))
    return _fit(segs, width - 1)


def _host_header(host, selected, collapsed, width, stale_after=None):
    badge, role = _badge(host)
    arrow = "▸" if collapsed else "▾"
    segs = [(f" {arrow} ", "white"),
            (host["alias"], "host_sel" if selected else "bold"),
            (" ", "white"), (badge, role)]
    if host["status"] == "error":
        segs.append(("  " + str(host.get("error") or "unknown error"), "red"))
        if host.get("retry_in") is not None:
            left = max(0, round(host["retry_in"] - (host.get("age_s") or 0)))
            segs.append((f"  retry #{host.get('fails', 1)} in {left}s", "yellow"))
    elif host["status"] == "no_gpu" and host.get("error"):
        segs.append(("  " + str(host["error"]), "dim"))
    age = host.get("age_s")
    if stale_after and age is not None and age > stale_after and host["status"] == "ok":
        segs.append((f"  no update for {age:.0f}s", "yellow"))
    return _fit(segs, width - 1)


# ── process table ────────────────────────────────────────────────────────────

# (title, key, right aligned, max width, droppable on narrow terminals)
_COLUMNS = (
    ("HOST", "host", False, 14, False),
    ("GPU", "gpu", False, 3, False),
    ("PID", "pid", False, 8, False),
    ("USER", "user", False, 14, True),
    ("TYPE", "type", False, 4, True),
    ("GPU MEM", "mem", True, 8, False),
    ("GPU%", "sm", True, 4, False),
)
MIN_COMMAND_WIDTH = 12


def _cell(row, key):
    if key == "mem":
        return _fmt_mem_col(row["mem_mb"])
    if key == "sm":
        return "-" if row["sm_pct"] is None else f"{row['sm_pct']:.0f}%"
    return str(row[key])


def _table(rows, state, width, max_lines):
    """Boxed process table; scrolls so the selected row stays visible.

    USER and TYPE are dropped (in that order of need) when the terminal is too
    narrow to leave room for the command.
    """
    inner_w = width - 3
    cols = list(_COLUMNS)

    def layout(cs):
        ws = [min(max([len(t)] + [len(_cell(r, k)) for r in rows]), cap)
              for t, k, _, cap, _ in cs]
        return ws, inner_w - (sum(ws) + len(ws) + 2)   # width left for COMMAND

    widths, cmd_w = layout(cols)
    for drop in ("TYPE", "USER"):
        if cmd_w >= MIN_COMMAND_WIDTH:
            break
        cols = [c for c in cols if c[0] != drop]
        widths, cmd_w = layout(cols)
    cmd_w = max(cmd_w, 1)

    def fmt_row(vals, cmd):
        out = ""
        for (title, key, right, _, _), w_, v in zip(cols, widths, vals):
            out += (f"{v[:w_]:>{w_}}" if right else f"{v[:w_]:<{w_}}") + " "
        return " " + out + cmd[:cmd_w]

    def boxed(text, role):
        body = text[:inner_w].ljust(inner_w)
        return [("\u2502" + body + "\u2502", role)]

    lines = [[("\u250c" + "\u2500" * inner_w + "\u2510", "dim")],
             boxed(fmt_row([c[0] for c in cols], "COMMAND"), "hdr")]
    visible = max(0, max_lines - 3)
    start = 0
    if len(rows) > visible:
        start = min(max(0, state.proc_index - visible + 1), len(rows) - visible)
    for i in range(start, min(len(rows), start + visible)):
        role = "sel" if i == state.proc_index else "white"
        lines.append(boxed(fmt_row([_cell(rows[i], c[1]) for c in cols],
                                   rows[i]["command"]), role))
    if not rows:
        lines.append(boxed("  no GPU processes", "dim"))
    lines.append([("\u2514" + "\u2500" * inner_w + "\u2518", "dim")])
    return [_fit(ln, width - 1) for ln in lines]


# ── screen assembly ──────────────────────────────────────────────────────────

def _footer(state, width):
    sort = f"s Sort:{state.sort_key}"
    if state.view == "graph":
        segs = [(" h Hosts  ", "white"), ("s Sort  f Filter  F5 Kill", "dim"),
                (f"  i Interval:{state.refresh_interval}s  c Compact  t Temp  v Processes  q Quit", "white"),
                ("    ←/→ host   F-keys work too", "dim")]
        return _fit(segs, width - 1)
    if state.filtering:
        segs = [(" Filter: ", "bold"), (state.filter_text + "_", "yellow"),
                ("   Enter apply  Esc clear", "dim")]
        return _fit(segs, width - 1)
    flt = f"f Filter:{state.filter_text}" if state.filter_text else "f Filter"
    segs = [(f" h Hosts  {sort}  {flt}  ", "white"), ("F5 Kill", "dim"),
            (f"  i Interval:{state.refresh_interval}s  c Compact  v View Graph  q Quit", "white"),
            ("    ←/→ host  ↑/↓ process", "dim")]
    return _fit(segs, width - 1)


def _gpu_section(results, history, state, width, compact, chart_h=0):
    lines = []
    host_w = min(14, max([len(h["alias"]) for h in results] + [4]))
    for hi, host in enumerate(results):
        collapsed = host["alias"] in state.collapsed
        ok = host["status"] == "ok"
        if not compact or not ok or collapsed:
            lines.append(_host_header(host, hi == state.host_index, collapsed, width,
                                      max(10, 3 * state.refresh_interval)))
        if not ok or collapsed:
            if not compact:
                lines.append([])
            continue
        if not compact and state.show_cpu:
            sys_line = _sys_line(host, width)
            if sys_line:
                lines.append(sys_line)
        for gpu in host["gpus"]:
            if compact or not _has_nvtop_fields(gpu):
                lines.append(_gpu_compact(host["alias"], gpu, history, width, host_w,
                                          compact and hi == state.host_index))
            else:
                lines.extend(_gpu_full(host["alias"], gpu, history, width, chart_h,
                                       state.refresh_interval, state.chart_temp))
                lines.append([])
        if not compact and not (host["gpus"] and _has_nvtop_fields(host["gpus"][-1])):
            lines.append([])
    return lines


def build_screen(results, history, state, width, height, meta):
    """Lay out the whole screen as lines of (text, role) segments."""
    width = max(20, width)
    state.host_aliases = [h["alias"] for h in results]
    state.sync_hosts()
    gpu_count = sum(len(h.get("gpus", [])) for h in results if h["status"] == "ok")
    left = [(f" nvtop2i {__version__}  {gpu_count} GPUs on {len(results)} hosts", "title")]
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
    graph = state.view == "graph"
    if graph:
        body = _gpu_section(results, history, state, width, compact, CHART_MIN_LINES)
        extra = height - 1 - len(top) - len(body)
        if not compact and extra < 0:
            compact = True
            body = _gpu_section(results, history, state, width, compact)
        elif not compact:
            n = sum(1 for h in results if h["status"] == "ok" and h["alias"] not in state.collapsed
                    for g in h["gpus"] if _has_nvtop_fields(g))
            grow = min(CHART_MAX_LINES - CHART_MIN_LINES, extra // n) if n else 0
            body = _gpu_section(results, history, state, width, compact,
                                CHART_MIN_LINES + grow)
    else:
        body = _gpu_section(results, history, state, width, compact)
        if not compact and len(top) + len(body) > height - 1 - TABLE_MIN_LINES:
            compact = True   # the full view does not fit: fall back to one line per GPU
            body = _gpu_section(results, history, state, width, compact)

    rows = [] if graph else process_rows(results, state)
    state.sync_procs(rows)
    lines = top + body
    room = height - 1 - len(lines)
    if not graph and room >= TABLE_MIN_LINES:
        lines += _table(rows, state, width, room)
    while len(lines) < height - 1:
        lines.append([])
    lines = lines[:height - 1] + [_footer(state, width)]
    return Screen(lines, len(results), rows, compact)


# ── curses layer ─────────────────────────────────────────────────────────────

def _init_attrs():
    """Map roles to curses attributes; falls back to bold/reverse without colors."""
    bold = curses.A_BOLD
    cp = lambda n: 0  # noqa: E731
    if curses.has_colors():
        curses.start_color()
        bg = -1
        try:
            curses.use_default_colors()
        except curses.error:
            bg = curses.COLOR_BLACK   # terminal cannot keep its own background
        pairs = [(1, curses.COLOR_GREEN), (2, curses.COLOR_YELLOW), (3, curses.COLOR_RED),
                 (4, curses.COLOR_CYAN), (5, curses.COLOR_WHITE), (6, curses.COLOR_BLUE),
                 (7, curses.COLOR_MAGENTA),
                 (8, curses.COLOR_BLACK + 8 if curses.COLORS > 8 else curses.COLOR_WHITE)]
        for n, color in pairs:
            curses.init_pair(n, color, bg)
        cp = curses.color_pair
    dim = cp(8) if curses.has_colors() else curses.A_DIM
    return {
        "green": cp(1), "yellow": cp(2), "red": cp(3), "cyan": cp(4), "white": 0,
        "dim": dim, "bold": bold, "value": bold, "hdr": bold | curses.A_UNDERLINE,
        "title": cp(4) | bold, "sel": curses.A_REVERSE,
        "host_sel": bold | curses.A_UNDERLINE,
        "chart_gpu": cp(4), "chart_mem": cp(2), "chart_temp": cp(3),
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

# Letters for the function keys: desktops often grab F-keys before the terminal.
_ALIASES = {ord("h"): curses.KEY_F2, ord("s"): curses.KEY_F3, ord("f"): curses.KEY_F4,
            ord("/"): curses.KEY_F4, ord("i"): curses.KEY_F6, ord("c"): curses.KEY_F8,
            ord("v"): curses.KEY_F9, ord("\t"): curses.KEY_F9}


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
    if key in (ord("t"), ord("T")):
        state.chart_temp = not state.chart_temp
        return None
    key = _ALIASES.get(key, key)
    if key == curses.KEY_F2:
        state.toggle_collapsed_at(state.host_index)
    elif key == curses.KEY_F9:
        state.toggle_view()
    elif key == curses.KEY_F3 and state.view == "procs":
        state.cycle_sort()
    elif key == curses.KEY_F4 and state.view == "procs":
        state.filtering = True
    elif key == curses.KEY_F6:
        bigger = [i for i in INTERVALS if i > state.refresh_interval]
        state.refresh_interval = bigger[0] if bigger else INTERVALS[0]
        return "interval"
    elif key == curses.KEY_F8:
        state.compact = not state.compact
    elif key == curses.KEY_LEFT:
        state.move_host(-1)
    elif key == curses.KEY_RIGHT:
        state.move_host(1)
    elif key == curses.KEY_UP:
        state.move_proc(-1, screen.rows)
    elif key == curses.KEY_DOWN:
        state.move_proc(1, screen.rows)
    return None


def _tui_main(stdscr, monitor, history, state):
    curses.curs_set(0)
    attrs = _init_attrs()
    stdscr.keypad(True)
    stdscr.timeout(250)
    # Every frame is repainted from scratch, so line insert/delete and scroll
    # regions only add escape sequences some terminals handle badly.
    stdscr.idlok(False)
    stdscr.scrollok(False)
    screen = Screen([], 0, [], False)

    while True:
        key = stdscr.getch()
        action = _handle_key(key, state, screen) if key != -1 else None
        if action == "quit":
            break
        if action in ("refresh", "interval"):
            monitor.refresh()

        h, w = stdscr.getmaxyx()
        data = monitor.snapshot()
        meta = {"last_update": monitor.last_update(), "loading": not data}
        screen = build_screen(data, history, state, w, h, meta)
        _paint(stdscr, screen, attrs)


def run_tui(ssh_config_path=None, refresh_interval=2):
    """Launch the curses TUI dashboard."""
    import nvtop2i.probe as srv
    from .log import setup_logging
    setup_logging()
    if ssh_config_path:
        srv.SSH_CONFIG_PATH = ssh_config_path

    from .monitor import Monitor

    from . import config
    state = UIState(refresh_interval)
    opts = config.load_options()
    state.show_cpu, state.chart_temp = opts["show_cpu"], opts["chart_temp"]
    history = History()
    monitor = Monitor(interval=lambda: state.refresh_interval, on_result=history.record_host)
    monitor.start()
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(_tui_main, monitor, history, state)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
