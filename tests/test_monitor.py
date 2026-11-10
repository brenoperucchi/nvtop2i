import threading
import time

import pytest

from nvtop2i import monitor as mon
from nvtop2i import probe as srv
from nvtop2i.tui_state import History


def ok_result(alias, util=10):
    return {"alias": alias, "hostname": alias, "user": "u", "port": 22, "status": "ok",
            "error": None, "gpus": [{"index": 0, "name": "G", "gpu_utilization_pct": util,
                                     "memory_usage_pct": 5, "temperature_c": 40,
                                     "processes": []}]}


class FakeClient:
    def __init__(self, alias):
        self.alias = alias
        self.closed = False

    def get_transport(self):
        return None

    def close(self):
        self.closed = True


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def fake_server(monkeypatch):
    """Replace the network layer: a set of hosts with scripted behaviour."""
    state = {"opens": {}, "polls": {}, "clients": [], "behaviour": {}}

    hosts = [{"alias": a, "hostname": a, "user": "u", "port": 22,
              "identity_file": None} for a in ("alpha", "beta")]
    monkeypatch.setattr(srv, "parse_ssh_config", lambda path: [dict(h) for h in hosts])
    monkeypatch.setattr(srv, "discover_gadi_nodes", lambda by_alias: [])
    monkeypatch.setattr(srv, "query_local_gpu",
                        lambda: dict(ok_result("localhost"), is_local=True))
    monkeypatch.setattr(srv, "local_alias", lambda: "localhost")
    monkeypatch.setattr(mon, "poll_delay", lambda interval, fails: 0.02)

    def open_connection(host_info, by_alias=None):
        alias = host_info["alias"]
        state["opens"][alias] = state["opens"].get(alias, 0) + 1
        client = FakeClient(alias)
        state["clients"].append(client)
        return client, None

    def run_on_client(client, host_info):
        alias = host_info["alias"]
        n = state["polls"][alias] = state["polls"].get(alias, 0) + 1
        return state["behaviour"].get(alias, lambda n: ok_result(alias))(n)

    monkeypatch.setattr(srv, "open_connection", open_connection)
    monkeypatch.setattr(srv, "run_on_client", run_on_client)
    return state


def test_one_connection_is_reused_for_many_polls(fake_server):
    m = mon.Monitor(interval=lambda: 0.02)
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 5)
    finally:
        m.stop()
    assert fake_server["opens"]["alpha"] == 1
    assert fake_server["opens"]["beta"] == 1


def test_snapshot_has_local_and_remote_hosts_sorted_with_age(fake_server):
    m = mon.Monitor(interval=lambda: 0.02)
    m.start()
    try:
        assert wait_for(lambda: len(m.snapshot()) == 3)
        snap = m.snapshot()
    finally:
        m.stop()
    assert [r["alias"] for r in snap] == ["localhost", "alpha", "beta"]
    assert all(r["age_s"] >= 0 for r in snap)
    assert m.last_update() > 0


def test_a_single_dropped_connection_is_retried_without_going_offline(fake_server):
    def drops_once(n):
        if n == 2:
            raise OSError("connection reset")
        return ok_result("alpha")
    fake_server["behaviour"]["alpha"] = drops_once

    seen = []
    m = mon.Monitor(interval=lambda: 0.02, on_result=lambda r: seen.append(
        (r["alias"], r["status"])))
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 5)
    finally:
        m.stop()
    assert fake_server["opens"]["alpha"] == 2               # reconnected once
    assert fake_server["clients"][0].closed                 # the dead one was closed
    assert ("alpha", "error") not in seen                   # no Offline flicker


def test_persistent_failure_is_reported_and_then_recovers(fake_server):
    def down_then_up(n):
        if n in (2, 3):
            raise OSError("connection reset")
        return ok_result("alpha")
    fake_server["behaviour"]["alpha"] = down_then_up

    seen = []
    m = mon.Monitor(interval=lambda: 0.02, on_result=lambda r: seen.append(
        (r["alias"], r["status"], r["error"])))
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 6)
    finally:
        m.stop()
    alpha = [x for x in seen if x[0] == "alpha"]
    assert ("alpha", "error", "Connection failed: connection reset") in alpha
    assert alpha[-1][1] == "ok"


def test_unparsable_answer_keeps_the_connection(fake_server):
    def garbled(n):
        if n == 2:
            raise ValueError("could not convert string to float: '[N/A]'")
        return ok_result("alpha")
    fake_server["behaviour"]["alpha"] = garbled

    seen = []
    m = mon.Monitor(interval=lambda: 0.02, on_result=lambda r: seen.append(
        (r["alias"], r["status"], r["error"])))
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 4)
    finally:
        m.stop()
    assert fake_server["opens"]["alpha"] == 1
    assert any(x[0] == "alpha" and x[1] == "error" and "ValueError" in x[2] for x in seen)


def test_hosts_without_gpu_are_polled_slowly(fake_server, monkeypatch):
    monkeypatch.setattr(mon, "NO_GPU_DELAY", 60)
    fake_server["behaviour"]["alpha"] = lambda n: {
        **ok_result("alpha"), "status": "no_gpu", "gpus": []}
    m = mon.Monitor(interval=lambda: 0.02)
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("beta", 0) >= 5)
    finally:
        m.stop()
    assert fake_server["polls"]["alpha"] == 1


def test_unreadable_ssh_config_is_shown_instead_of_swallowed(fake_server, monkeypatch):
    def boom(path):
        raise ValueError("invalid literal for int() with base 10: '${PORT}'")
    monkeypatch.setattr(srv, "parse_ssh_config", boom)
    m = mon.Monitor(interval=lambda: 0.02)
    m.start()
    try:
        assert wait_for(lambda: any(r["alias"] == "(ssh config)" for r in m.snapshot()))
        row = next(r for r in m.snapshot() if r["alias"] == "(ssh config)")
    finally:
        m.stop()
    assert row["status"] == "error" and "${PORT}" in row["error"]


def test_nodes_discovered_later_get_a_worker_and_discovery_repeats(fake_server, monkeypatch):
    monkeypatch.setattr(mon, "DISCOVERY_EVERY", 0.05)
    calls = []

    def discover(by_alias):
        calls.append(1)
        if len(calls) < 3:
            return []
        return [{"alias": "gadi-gpu-1", "hostname": "gadi-gpu-1", "user": "u",
                 "port": 22, "identity_file": None}]
    monkeypatch.setattr(srv, "discover_gadi_nodes", discover)
    m = mon.Monitor(interval=lambda: 0.02)
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("gadi-gpu-1", 0) >= 2)
    finally:
        m.stop()
    assert len(calls) >= 3


def test_slow_discovery_does_not_delay_the_configured_hosts(fake_server, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(srv, "discover_gadi_nodes", lambda by_alias: release.wait(5) and [])
    m = mon.Monitor(interval=lambda: 0.02)
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 3)
    finally:
        release.set()
        m.stop()


def test_slow_host_does_not_block_the_others(fake_server):
    release = threading.Event()

    def slow(n):
        release.wait(5)
        return ok_result("alpha")
    fake_server["behaviour"]["alpha"] = slow

    m = mon.Monitor(interval=lambda: 0.02)
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("beta", 0) >= 5)
        status = {r["alias"]: r["status"] for r in m.snapshot()}
        assert status["beta"] == "ok" and status["localhost"] == "ok"
        assert status["alpha"] == "connecting"   # visible, still waiting
    finally:
        release.set()
        m.stop()


def test_refresh_wakes_workers_before_the_interval(fake_server):
    m = mon.Monitor(interval=lambda: 60)
    m.start()
    try:
        assert wait_for(lambda: len(m.snapshot()) == 3)
        before = fake_server["polls"]["alpha"]
        m.refresh()
        assert wait_for(lambda: fake_server["polls"]["alpha"] > before)
    finally:
        m.stop()


def test_stop_ends_polling_and_closes_connections(fake_server):
    m = mon.Monitor(interval=lambda: 0.02)
    m.start()
    assert wait_for(lambda: len(m.snapshot()) == 3)
    m.stop()
    assert wait_for(lambda: all(c.closed for c in fake_server["clients"]))
    n = fake_server["polls"]["alpha"]
    time.sleep(0.15)
    assert fake_server["polls"]["alpha"] <= n + 1


def test_on_result_feeds_history_once_per_poll(fake_server):
    hist = History()
    m = mon.Monitor(interval=lambda: 0.02, on_result=hist.record_host)
    m.start()
    try:
        assert wait_for(lambda: len(hist.series("alpha", 0, "gpu")) >= 3)
    finally:
        m.stop()
    assert set(hist.series("alpha", 0, "gpu")) == {10}


def test_poll_delay_grows_with_failures_up_to_a_cap():
    import importlib
    real = importlib.reload(mon)
    try:
        assert real.poll_delay(2, 0) == 2
        assert real.poll_delay(2, 1) == 2
        assert real.poll_delay(2, 3) == 8
        assert real.poll_delay(2, 20) == real.MAX_BACKOFF
        assert real.poll_delay(60, 3) == 60
    finally:
        importlib.reload(mon)


def test_connecting_placeholders_sort_after_ok_hosts():
    rows = [{"alias": "c", "status": "error", "gpus": []},
            {"alias": "b", "status": "connecting", "gpus": []},
            {"alias": "a", "status": "ok", "gpus": []}]
    assert [r["alias"] for r in srv._sort_results(rows)] == ["a", "b", "c"]


def test_outage_is_logged_published_with_retry_info_and_recovery_is_logged(fake_server, caplog):
    def down_then_up(n):
        if n in (2, 3, 4, 5):          # a dropped poll plus its immediate retry, twice
            raise OSError("Connection timed out")
        return ok_result("alpha")
    fake_server["behaviour"]["alpha"] = down_then_up

    seen = []
    m = mon.Monitor(interval=lambda: 0.02, on_result=lambda r: seen.append(r))
    with caplog.at_level("INFO", logger="nvtop2i"):
        m.start()
        try:
            assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 9)
        finally:
            m.stop()

    errors = [r for r in seen if r["alias"] == "alpha" and r["status"] == "error"]
    assert errors and all(r["fails"] >= 1 and r["retry_in"] >= 0 for r in errors)
    text = caplog.text
    assert "alpha: connection lost: " in text and "retrying in" in text
    assert "alpha: reconnected after" in text
    assert "localhost" not in text                       # the local row never logs outages


def test_hung_gpu_query_reports_nvidia_smi_and_keeps_the_connection(fake_server):
    def hangs(n):
        raise srv.CommandTimeout("nvidia-smi did not answer in 15s")
    fake_server["behaviour"]["alpha"] = hangs

    seen = []
    m = mon.Monitor(interval=lambda: 0.02, on_result=lambda r: seen.append(r))
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 4)
    finally:
        m.stop()
    assert fake_server["opens"]["alpha"] == 1               # no reconnect, no stacked retry
    errs = [r for r in seen if r["alias"] == "alpha" and r["status"] == "error"]
    assert errs and errs[0]["error"] == "nvidia-smi did not answer in 15s"


def test_run_on_client_cuts_a_hung_command_and_closes_its_channel():
    import socket

    class Chan:
        closed = False

        def close(self):
            self.closed = True

    class Out:
        channel = Chan()

        def read(self):
            raise socket.timeout("timed out")

    class Client:
        timeout = None

        def exec_command(self, cmd, timeout=None):
            Client.timeout = timeout
            return None, Out(), None

    host = {"alias": "w", "hostname": "w", "user": "u", "port": 22}
    with pytest.raises(srv.CommandTimeout) as e:
        srv.run_on_client(Client(), host)
    assert Client.timeout == srv.COMMAND_TIMEOUT < srv.SSH_TIMEOUT
    assert Out.channel.closed
    assert srv._error_text(e.value) == f"nvidia-smi did not answer in {srv.COMMAND_TIMEOUT}s"


def test_local_row_is_named_after_this_machine(monkeypatch):
    monkeypatch.setattr(srv.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ""})())
    import socket
    monkeypatch.setattr(socket, "gethostname", lambda: "omarchy.lan")
    assert srv.local_alias() == "omarchy"
    assert srv.query_local_gpu()["alias"] == "omarchy"
    monkeypatch.setattr(socket, "gethostname", lambda: "")
    assert srv.local_alias() == "localhost"


def test_cpu_percent_comes_from_two_consecutive_polls(fake_server):
    ticks = {"n": 0}

    def with_cpu(n):
        r = ok_result("alpha")
        r["sys"] = {"cpu_busy": 100 * n, "cpu_total": 400 * n}   # 25 % busy each interval
        return r
    fake_server["behaviour"]["alpha"] = with_cpu

    seen = []
    m = mon.Monitor(interval=lambda: 0.02, on_result=lambda r: seen.append(r))
    m.start()
    try:
        assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 4)
    finally:
        m.stop()
    alpha = [r["sys"] for r in seen if r["alias"] == "alpha" and r.get("sys")]
    assert "cpu_pct" not in alpha[0]                      # first poll: nothing to compare with
    assert all(abs(s["cpu_pct"] - 25) < 0.01 for s in alpha[1:])


def test_gpu_fault_is_logged_when_it_starts_and_when_it_clears(fake_server, caplog):
    def faulty_then_fine(n):
        r = ok_result("alpha")
        if 3 <= n <= 5:
            r["gpus"][0]["fault"] = "GPU requires reset"
        return r
    fake_server["behaviour"]["alpha"] = faulty_then_fine

    m = mon.Monitor(interval=lambda: 0.02)
    with caplog.at_level("INFO", logger="nvtop2i"):
        m.start()
        try:
            assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 9)
        finally:
            m.stop()

    text = caplog.text
    assert text.count("alpha: GPU 0 fault: GPU requires reset") == 1   # once, not per poll
    assert "alpha: GPU 0 recovered" in text
