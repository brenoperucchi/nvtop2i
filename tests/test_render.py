import pytest

from nvtop2i import tui
from nvtop2i.tui_state import History, UIState


def gpu(i, name, util, mem_used, mem_total, temp, procs=(), **extra):
    g = {
        "index": i, "name": name,
        "memory_total_mb": mem_total, "memory_used_mb": mem_used,
        "memory_free_mb": mem_total - mem_used,
        "memory_usage_pct": round(mem_used / mem_total * 100, 1),
        "gpu_utilization_pct": util, "temperature_c": temp,
        "clock_gr_mhz": 1230, "clock_mem_mhz": 810, "fan_pct": 45,
        "power_w": 47, "power_limit_w": 300, "pcie_gen": 2, "pcie_width": 8,
        "pcie_rx_mbs": 5.4, "pcie_tx_mbs": 2.0, "processes": list(procs),
    }
    g.update(extra)
    return g


def proc(pid, user, cmd, mem, sm=None, t="G"):
    return {"pid": pid, "user": user, "command": cmd, "gpu_memory_mb": mem,
            "sm_pct": sm, "type": t}


def results():
    return [
        {"alias": "localhost", "status": "ok", "is_local": True, "gpus": [
            gpu(0, "NVIDIA GeForce RTX 3080 Ti", 37, 3611, 12288, 45,
                [proc(3093, "brenoperucchi", "Hyprland", 515, 35)]),
            gpu(1, "NVIDIA GeForce RTX 4090", 0, 402, 24564, 36)]},
        {"alias": "ryzen9", "status": "ok", "gpus": [
            gpu(0, "NVIDIA GeForce RTX 5090", 69, 31948, 32607, 45,
                [proc(41200, "wsl", "ollama", 31744, 69, "C")])]},
        {"alias": "ks3", "status": "error", "error": "ssh: Permission denied (publickey)",
         "gpus": []},
        {"alias": "ks2", "status": "no_gpu", "error": None, "gpus": []},
    ]


def _procs_state(n=2):
    st = UIState(n)
    st.view = "procs"
    return st


def render(res, w, h, compact=False, state=None, history=None):
    st = state or _procs_state(2)
    st.compact = compact
    hist = history or History()
    for _ in range(5):
        hist.record(res)
    screen = tui.build_screen(res, hist, st, w, h, {"last_update": 1_700_000_000.0})
    text = ["".join(t for t, _ in line) for line in screen.lines]
    return screen, text


@pytest.mark.parametrize("w,h", [(160, 50), (120, 40), (100, 30), (80, 24), (60, 20), (40, 12), (20, 6)])
def test_no_line_overflows_and_height_is_exact(w, h):
    screen, text = render(results(), w, h)
    assert len(text) == h
    assert all(len(line) <= w - 1 for line in text), [l for l in text if len(l) > w - 1]


def test_full_view_matches_mockup_a():
    screen, text = render(results(), 160, 60)
    joined = "\n".join(text)
    assert not screen.compact
    assert "4 GPUs on 4 hosts" not in joined and "3 GPUs on 4 hosts" in joined
    assert "▾ localhost [Local]" in joined
    assert "Device 0 [NVIDIA GeForce RTX 3080 Ti]" in joined
    assert "PCIe GEN 2@ 8x" in joined and "RX: 5.4 MB/s" in joined
    assert "GPU 1230MHz  MEM 810MHz   TEMP 45\u00b0C  FAN 45%  POW 47 / 300 W" in joined
    assert "TEMP 45°C" in joined and "FAN 45%" in joined and "POW 47 / 300 W" in joined
    assert "GPU[" in joined and "MEM[" in joined and "37%" in joined
    assert "3.526Gi/12.000Gi" in joined
    assert "hist GPU" in joined and "TEMP" in joined
    assert "ryzen9 [Online]" in joined
    # mockup C
    assert "ks3 [Offline]  ssh: Permission denied (publickey)" in joined
    assert "ks2 [No GPU]" in joined
    # process table
    assert "┌" in joined and "COMMAND" in joined
    assert "ollama" in joined and "31.0GiB" in joined and "Hyprland" in joined
    # footer
    assert "F2 Hosts" in text[-1] and "F10 Quit" in text[-1]


def test_compact_view_matches_mockup_b():
    screen, text = render(results(), 120, 30, compact=True)
    joined = "\n".join(text)
    assert screen.compact
    assert "Device 0" not in joined          # no per-GPU header
    assert "localhost  0 3080 Ti" in joined
    assert "ryzen9     0 5090" in joined
    assert "[Offline]" in joined and "[No GPU]" in joined


def test_narrow_terminal_falls_back_to_compact():
    screen, _ = render(results(), 80, 24)
    assert screen.compact


def test_tall_content_falls_back_to_compact():
    screen, text = render(results(), 160, 24)
    assert screen.compact
    assert "COMMAND" in "\n".join(text)  # the table still fits


def test_gpu_without_extra_fields_uses_simple_line():
    # MetaX / TPU entries only have the old keys
    old = {"index": 0, "name": "MetaX C500", "memory_total_mb": 65536,
           "memory_used_mb": 858, "memory_usage_pct": 1.3,
           "gpu_utilization_pct": 0, "temperature_c": 36, "processes": []}
    res = [{"alias": "mx1", "status": "ok", "gpus": [old]}]
    screen, text = render(res, 160, 30)
    joined = "\n".join(text)
    assert "MetaX C500" in joined and "Device 0" not in joined


def test_missing_values_show_dashes():
    res = [{"alias": "wsl", "status": "ok", "gpus": [
        gpu(0, "NVIDIA GeForce RTX 5090", 3, 100, 32607, 42, fan_pct=None,
            power_w=None, power_limit_w=None, pcie_gen=None, pcie_width=None,
            pcie_rx_mbs=None, pcie_tx_mbs=None, clock_gr_mhz=None, clock_mem_mhz=None)]}]
    _, text = render(res, 160, 30)
    joined = "\n".join(text)
    assert "PCIe --" in joined and "RX: --" in joined and "FAN --" in joined
    assert "POW -- / -- W" in joined


def test_collapsed_host_hides_gpus_and_shows_arrow():
    st = _procs_state(2)
    st.collapsed.add("localhost")
    _, text = render(results(), 160, 60, state=st)
    joined = "\n".join(text)
    assert "▸ localhost" in joined and "RTX 3080 Ti]" not in joined
    assert "Hyprland" not in joined   # its processes leave the table too


def test_filter_and_sort_reach_the_table_and_footer():
    st = _procs_state(2)
    st.filter_text = "ollama"
    _, text = render(results(), 160, 60, state=st)
    joined = "\n".join(text)
    assert "ollama" in joined and "Hyprland" not in joined
    assert "F4 Filter:ollama" in text[-1]
    st.filtering = True
    _, text = render(results(), 160, 60, state=st)
    assert text[-1].startswith(" Filter: ollama_")


def test_empty_results_show_waiting():
    _, text = render([], 80, 10)
    assert "Waiting for data" in "\n".join(text)


def test_usage_and_temperature_thresholds():
    assert [tui._usage_role(v) for v in (0, 49.9, 50, 80, 80.1, 100)] == \
        ["green", "green", "yellow", "yellow", "red", "red"]
    assert [tui._temp_role(v) for v in (30, 59, 60, 80, 81)] == \
        ["green", "green", "yellow", "yellow", "red"]


def test_bar_has_label_inside_and_right_aligned():
    segs = tui._bar_segs("GPU", 37, 30, "37%", "green")
    text = "".join(t for t, _ in segs)
    assert text.startswith("GPU[") and text.endswith("37%]")
    assert text.count("|") == int(0.37 * 30)
    assert len(text) == 4 + 30 + 1
    full = "".join(t for t, _ in tui._bar_segs("MEM", 100, 20, "31.2Gi/31.8Gi", "red"))
    assert "31.2Gi/31.8Gi" in full and len(full) == 4 + 20 + 1


def test_selected_row_scrolls_into_view():
    procs = [proc(i, "u", f"cmd{i}", 100 + i, i) for i in range(1, 40)]
    res = [{"alias": "h", "status": "ok", "gpus": [gpu(0, "NVIDIA X", 1, 1, 2, 3, procs)]}]
    st = _procs_state(2)
    st.sort_key = "pid"
    st.proc_index = 35
    _, text = render(res, 100, 20, state=st)
    assert "cmd36" in "\n".join(text)
    assert "cmd1 " not in "\n".join(text)


def test_key_handling():
    import curses
    st = _procs_state(2)
    st.host_aliases = ["a", "b", "c"]
    scr = tui.Screen([], 3, [{"host": "a", "gpu": 0, "pid": p} for p in (1, 2, 3, 4)], False)
    assert tui._handle_key(curses.KEY_F8, st, scr) is None and st.compact
    tui._handle_key(curses.KEY_F3, st, scr)
    assert st.sort_key != "mem"
    tui._handle_key(curses.KEY_RIGHT, st, scr)
    tui._handle_key(curses.KEY_F2, st, scr)
    assert st.collapsed == {"b"}
    tui._handle_key(curses.KEY_DOWN, st, scr)
    assert st.proc_index == 1
    assert tui._handle_key(curses.KEY_F6, st, scr) == "interval" and st.refresh_interval == 5
    assert tui._handle_key(ord("r"), st, scr) == "refresh"
    assert tui._handle_key(curses.KEY_F10, st, scr) == "quit"
    tui._handle_key(curses.KEY_F4, st, scr)
    for ch in "gp":
        tui._handle_key(ord(ch), st, scr)
    tui._handle_key(127, st, scr)
    assert st.filtering and st.filter_text == "g"
    assert tui._handle_key(ord("q"), st, scr) is None and st.filter_text == "gq"
    tui._handle_key(10, st, scr)
    assert not st.filtering and st.filter_text == "gq"
    tui._handle_key(curses.KEY_F4, st, scr)
    tui._handle_key(27, st, scr)
    assert not st.filtering and st.filter_text == ""


def test_host_without_recent_update_is_marked_stale():
    res = results()
    res[0]["age_s"] = 45.0     # interval 2 s: stale after max(10, 6) s
    res[1]["age_s"] = 1.0
    _, text = render(res, 160, 60)
    joined = "\n".join(text)
    assert "localhost [Local]  no update for 45s" in joined
    assert "ryzen9 [Online]  no update" not in joined


def test_init_attrs_without_color_support(monkeypatch):
    import curses
    monkeypatch.setattr(curses, "has_colors", lambda: False)
    attrs = tui._init_attrs()          # must not touch start_color/init_pair
    assert attrs["green"] == 0 and attrs["badge_off"] == curses.A_BOLD
    assert attrs["dim"] == curses.A_DIM and attrs["sel"] == curses.A_REVERSE


def test_init_attrs_when_default_colors_are_unsupported(monkeypatch):
    import curses
    calls = []
    monkeypatch.setattr(curses, "has_colors", lambda: True)
    monkeypatch.setattr(curses, "start_color", lambda: None)
    monkeypatch.setattr(curses, "COLORS", 8, raising=False)

    def no_default():
        raise curses.error("ERR")
    monkeypatch.setattr(curses, "use_default_colors", no_default)
    monkeypatch.setattr(curses, "init_pair", lambda n, fg, bg: calls.append((n, bg)))
    monkeypatch.setattr(curses, "color_pair", lambda n: n << 8)
    attrs = tui._init_attrs()
    assert all(bg == curses.COLOR_BLACK for _, bg in calls) and len(calls) == 8
    assert attrs["green"] == 1 << 8


def test_connecting_host_gets_a_badge_and_never_looks_stale():
    res = results() + [{"alias": "slow", "status": "connecting", "error": None,
                        "gpus": [], "age_s": 120.0}]
    _, text = render(res, 160, 60)
    joined = "\n".join(text)
    assert "slow [Connecting]" in joined and "no update" not in joined


def test_narrow_table_drops_user_and_type_to_keep_the_command_readable():
    _, wide = render(results(), 160, 60)
    assert any("USER" in l and "TYPE" in l for l in wide)
    _, narrow = render(results(), 60, 24)
    header = next(l for l in narrow if "COMMAND" in l)
    assert "USER" not in header and "TYPE" not in header
    row = next(l for l in narrow if "ollama" in l)
    assert "ollama" in row and "31.0GiB" in row


def test_f6_goes_to_the_next_larger_interval_even_from_an_odd_value():
    import curses
    scr = tui.Screen([], 1, [], False)
    st = _procs_state(3)
    tui._handle_key(curses.KEY_F6, st, scr)
    assert st.refresh_interval == 5
    st.refresh_interval = 30
    tui._handle_key(curses.KEY_F6, st, scr)
    assert st.refresh_interval == 1


def test_compact_view_keeps_a_collapsed_host_visible_and_marks_the_selected_one():
    st = _procs_state(2)
    st.collapsed.add("ryzen9")
    screen, text = render(results(), 120, 30, compact=True, state=st)
    joined = "\n".join(text)
    assert screen.compact
    assert "\u25b8 ryzen9 [Online]" in joined          # folded, but still listed
    assert "ryzen9     0 5090" not in joined
    # the selected host (first one) is drawn with its own role in the rows
    sel_roles = [(t, r) for line in screen.lines for t, r in line if r == "host_sel"]
    assert sel_roles and sel_roles[0][0].strip() == "localhost"


def test_graph_view_is_default_and_draws_boxes_instead_of_the_table():
    st = UIState(2)
    assert st.view == "graph"
    _, text = render(results(), 120, 40, state=st)
    assert any("GPU0 %" in l and "mem%" in l and l.lstrip().startswith("┌") for l in text)
    assert not any("COMMAND" in l for l in text)
    assert any("F9 View:graph" in l for l in text)
    assert any(any("\u2800" <= c <= "\u28ff" for c in l) for l in text)


def test_f9_toggles_between_graph_and_process_table():
    import curses
    st = UIState(2)
    scr = tui.Screen([], 0, [], False)
    tui._handle_key(curses.KEY_F9, st, scr)
    assert st.view == "procs"
    _, text = render(results(), 120, 40, state=st)
    assert any("COMMAND" in l for l in text)
    tui._handle_key(curses.KEY_F9, st, scr)
    assert st.view == "graph"
    tui._handle_key(curses.KEY_F3, st, scr)
    assert st.sort_key == "mem"   # F3 does nothing in the graph view


def test_step_chart_marks_the_newest_value_at_the_right_edge():
    from nvtop2i.chart import step_masks
    m = step_masks([0, 100], cols=3, rows=2)
    assert m[0][2] & 0x10 and m[1][2] & 0x08   # right column: the step goes from bottom to top
    assert not any(m[r][0] for r in range(2))
