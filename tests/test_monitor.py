import threading
import time

import pytest

from gnvitop import monitor as mon
from gnvitop import server as srv
from gnvitop.tui_state import History


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


def test_failure_closes_connection_and_reconnects(fake_server):
    def flaky(n):
        if n == 2:
            raise OSError("connection reset")
        return ok_result("alpha")
    fake_server["behaviour"]["alpha"] = flaky

    seen = []
    m = mon.Monitor(interval=lambda: 0.02, on_result=lambda r: seen.append(
        (r["alias"], r["status"], r["error"])))
    m.start()
    try:
        assert wait_for(lambda: fake_server["opens"].get("alpha", 0) >= 2)
        assert wait_for(lambda: fake_server["polls"].get("alpha", 0) >= 4)
    finally:
        m.stop()
    alpha = [s for s in seen if s[0] == "alpha"]
    assert ("alpha", "error", "Connection failed: connection reset") in alpha
    assert alpha[-1][1] == "ok"                       # recovered
    assert fake_server["clients"][0].closed           # dead connection was closed


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
        aliases = {r["alias"] for r in m.snapshot()}
        assert "beta" in aliases and "localhost" in aliases and "alpha" not in aliases
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


def test_query_gpu_still_returns_error_text(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("slow")
    monkeypatch.setattr(srv, "open_connection", boom)
    r = srv.query_gpu({"alias": "x", "hostname": "x", "user": None, "port": 22})
    assert r["status"] == "error" and r["error"] == "Connection timed out"
