"""Background polling for the TUI: one thread per host, one SSH connection each.

A slow or dead host only delays its own row. The connection is opened once and
reused for every poll (each poll is a new channel); after a failure the worker
reconnects with a growing delay.
"""

import threading
import time

from . import server as srv

MAX_BACKOFF = 30


def poll_delay(interval, fails):
    """Seconds between polls: the interval, longer after repeated failures."""
    if not fails:
        return interval
    return max(interval, min(MAX_BACKOFF, 2 ** min(fails, 5)))


class _HostWorker(threading.Thread):
    def __init__(self, monitor, host_info, hosts_by_alias):
        super().__init__(daemon=True, name=f"gnvitop-{host_info['alias']}")
        self.monitor = monitor
        self.host_info = host_info
        self.hosts_by_alias = hosts_by_alias
        self.wake = threading.Event()
        self.fails = 0
        self.client = None
        self.jump_client = None

    def _close(self):
        for c in (self.client, self.jump_client):
            if c:
                try:
                    c.close()
                except Exception:
                    pass
        self.client = self.jump_client = None

    def poll(self):
        """One poll: reuse the connection, open it when missing."""
        if self.host_info.get("is_local"):
            return srv.query_local_gpu()
        try:
            if self.client is None:
                self.client, self.jump_client = srv.open_connection(
                    self.host_info, self.hosts_by_alias)
                transport = self.client.get_transport()
                if transport:
                    transport.set_keepalive(15)
            return srv.run_on_client(self.client, self.host_info)
        except Exception as e:
            self._close()
            result = srv._new_result(self.host_info)
            result["error"] = srv._error_text(e)
            return result

    def run(self):
        mon = self.monitor
        while not mon.stopped.is_set():
            started = time.time()
            result = self.poll()
            if mon.stopped.is_set():
                break
            mon.publish(self.host_info["alias"], result)
            self.fails = 0 if result["status"] != "error" else self.fails + 1
            wait = max(0.0, poll_delay(mon.interval(), self.fails) - (time.time() - started))
            self.wake.wait(wait)
            self.wake.clear()
        self._close()


class Monitor:
    """Latest result per host, refreshed in the background."""

    def __init__(self, interval=lambda: 2, on_result=None):
        self.interval = interval
        self.on_result = on_result
        self.stopped = threading.Event()
        self._results = {}
        self._lock = threading.Lock()
        self._workers = []

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        self._spawn({"alias": "localhost", "is_local": True}, {})
        threading.Thread(target=self._setup, daemon=True, name="gnvitop-setup").start()

    def _spawn(self, host_info, hosts_by_alias):
        # Show the host right away; a slow connection can take a long time.
        placeholder = srv._new_result(dict(host_info, hostname=host_info.get("hostname"),
                                           user=host_info.get("user"),
                                           port=host_info.get("port", 22)))
        placeholder["status"] = "connecting"
        placeholder["is_local"] = bool(host_info.get("is_local"))
        self.publish(host_info["alias"], placeholder)
        worker = _HostWorker(self, host_info, hosts_by_alias)
        self._workers.append(worker)
        worker.start()

    def _setup(self):
        """Read the SSH config and start one worker per host."""
        try:
            hosts = srv.parse_ssh_config(srv.SSH_CONFIG_PATH)
            by_alias = {h["alias"]: h for h in hosts}
            for h in srv.discover_gadi_nodes(by_alias):
                if h["alias"] not in by_alias:
                    hosts.append(h)
                    by_alias[h["alias"]] = h
        except Exception:
            return
        for host_info in hosts:
            if self.stopped.is_set():
                return
            self._spawn(host_info, by_alias)

    def stop(self):
        self.stopped.set()
        for w in self._workers:
            w.wake.set()

    def refresh(self):
        """Poll every host now instead of waiting for the interval."""
        for w in self._workers:
            w.wake.set()

    # -- results ------------------------------------------------------------
    def publish(self, alias, result):
        result["fetched_at"] = time.time()
        with self._lock:
            self._results[alias] = result
        if self.on_result:
            self.on_result(result)

    def snapshot(self):
        """Sorted results; each host gets `age_s`, seconds since its last poll."""
        now = time.time()
        with self._lock:
            items = [dict(r) for r in self._results.values()]
        for r in items:
            r["age_s"] = now - r["fetched_at"]
        return srv._sort_results(items)

    def last_update(self):
        with self._lock:
            return max([r["fetched_at"] for r in self._results.values()] or [0.0])
