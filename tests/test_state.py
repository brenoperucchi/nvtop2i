from gnvitop.tui_state import History, UIState, process_rows, sparkline


def test_sparkline_scales_and_pads():
    s = sparkline([0, 50, 100], 5)
    assert len(s) == 5
    assert s[:2] == "  "
    assert s[2] == "▁" and s[4] == "█"


def test_sparkline_keeps_only_the_tail():
    assert sparkline(list(range(0, 100, 5)), 4) == sparkline([80, 85, 90, 95], 4)
    assert len(sparkline([1] * 100, 10)) == 10


def test_sparkline_none_clamp_and_zero_width():
    assert sparkline([None, 150, -20], 3) == " █▁"
    assert sparkline([1, 2], 0) == ""
    assert sparkline([], 4) == "    "


def test_sparkline_custom_range_for_temperature():
    # 20..100 C: 20 is the lowest block, 100 the highest
    s = sparkline([20, 100], 2, lo=20, hi=100)
    assert s == "▁█"


def _host(alias, gpus, status="ok"):
    return {"alias": alias, "status": status, "gpus": gpus}


def _gpu(i, util, mem, temp, procs=()):
    return {"index": i, "gpu_utilization_pct": util, "memory_usage_pct": mem,
            "temperature_c": temp, "processes": list(procs)}


def test_history_records_only_ok_hosts_and_caps_length():
    h = History(maxlen=3)
    for n in range(5):
        h.record([_host("a", [_gpu(0, n * 10, 5, 40)]),
                  _host("b", [], status="error")])
    assert h.series("a", 0, "gpu") == [20, 30, 40]
    assert h.series("b", 0, "gpu") == []
    assert h.series("a", 1, "gpu") == []


def _proc(pid, user, cmd, mem, sm=None, t="C"):
    return {"pid": pid, "user": user, "command": cmd, "gpu_memory_mb": mem,
            "sm_pct": sm, "type": t}


RESULTS = [
    _host("local", [_gpu(0, 1, 1, 1, [_proc(3, "bob", "Hyprland", 500, 30, "G"),
                                       _proc(1, "bob", "voxtype", 700)])]),
    _host("ryzen9", [_gpu(0, 1, 1, 1, [_proc(2, "wsl", "ollama", 31000, 69)])]),
    _host("down", [], status="error"),
]


def test_process_rows_sorted_by_memory_by_default():
    rows = process_rows(RESULTS, UIState())
    assert [r["command"] for r in rows] == ["ollama", "voxtype", "Hyprland"]
    assert rows[0]["host"] == "ryzen9" and rows[0]["gpu"] == 0


def test_process_rows_sort_filter_and_collapse():
    st = UIState()
    st.sort_key = "pid"
    assert [r["pid"] for r in process_rows(RESULTS, st)] == [1, 2, 3]
    st.sort_key = "gpu"
    assert [r["pid"] for r in process_rows(RESULTS, st)] == [2, 3, 1]
    st.filter_text = "BOB"
    assert {r["user"] for r in process_rows(RESULTS, st)} == {"bob"}
    st.filter_text = ""
    st.collapsed.add("ryzen9")
    assert all(r["host"] != "ryzen9" for r in process_rows(RESULTS, st))


def test_ui_state_navigation():
    st = UIState()
    st.move_host(-1, 3)
    assert st.host_index == 2
    st.move_host(1, 3)
    assert st.host_index == 0
    st.move_proc(-5, 4)
    assert st.proc_index == 0
    st.move_proc(10, 4)
    assert st.proc_index == 3
    st.move_proc(1, 0)
    assert st.proc_index == 0
    first = st.sort_key
    for _ in range(5):
        st.cycle_sort()
    assert st.sort_key == first
    st.toggle_collapsed("x")
    st.toggle_collapsed("x")
    assert st.collapsed == set()
