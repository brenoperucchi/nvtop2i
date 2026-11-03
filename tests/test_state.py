from nvtop2i.tui_state import History, UIState, process_rows, sparkline


def test_sparkline_scales_and_pads():
    s = sparkline([0, 50, 100], 5)
    assert len(s) == 5
    assert s[3:] == "  "
    assert s[0] == "▁" and s[2] == "█"


def test_sparkline_keeps_only_the_tail():
    assert sparkline(list(range(0, 100, 5)), 4) == sparkline([80, 85, 90, 95], 4)
    assert len(sparkline([1] * 100, 10)) == 10


def test_sparkline_none_clamp_and_zero_width():
    assert sparkline([None, 150, -20], 3) == " █▁"
    assert sparkline([1, 2], 0) == ""
    assert sparkline([], 4) == "    "
    assert sparkline([None, 150, -20], 3) == " \u2588\u2581"


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


def _rows(*pids):
    return [{"host": "h", "gpu": 0, "pid": p} for p in pids]


def test_ui_state_navigation():
    st = UIState()
    st.host_aliases = ["a", "b", "c"]
    st.move_host(-1)
    assert st.host_index == 2 and st.selected_alias == "c"
    st.move_host(1)
    assert st.host_index == 0
    st.move_proc(-5, _rows(1, 2, 3, 4))
    assert st.proc_index == 0
    st.move_proc(10, _rows(1, 2, 3, 4))
    assert st.proc_index == 3
    st.move_proc(1, [])
    assert st.proc_index == 0
    first = st.sort_key
    for _ in range(5):
        st.cycle_sort()
    assert st.sort_key == first
    st.toggle_collapsed("x")
    st.toggle_collapsed("x")
    assert st.collapsed == set()


def test_host_selection_follows_the_host_when_the_list_reorders():
    st = UIState()
    st.host_aliases = ["a", "b", "c"]
    st.move_host(1)                       # b
    st.host_aliases = ["c", "b", "a"]     # statuses changed, order changed
    st.sync_hosts()
    assert st.host_index == 1 and st.host_aliases[st.host_index] == "b"
    st.toggle_collapsed_at(st.host_index)
    assert st.collapsed == {"b"}
    st.host_aliases = ["c", "a"]          # b disappeared: clamp, no crash
    st.sync_hosts()
    assert 0 <= st.host_index < 2


def test_process_selection_follows_the_process_when_the_rows_resort():
    st = UIState()
    st.move_proc(1, _rows(10, 20, 30))    # pid 20
    st.sync_procs(_rows(30, 20, 10))
    assert st.proc_index == 1
    st.sync_procs(_rows(30, 10))          # 20 exited: clamp
    assert st.proc_index == 1
    st.sync_procs([])
    assert st.proc_index == 0


def test_without_a_selection_the_index_is_kept():
    st = UIState()
    st.proc_index = 2
    st.sync_procs(_rows(1, 2, 3, 4))
    assert st.proc_index == 2
    st.sync_procs(_rows(1))
    assert st.proc_index == 0
