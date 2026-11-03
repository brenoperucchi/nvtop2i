"""Background polling for the TUI: one thread per host, one SSH connection each.

A slow or dead host only delays its own row. The connection is opened once and
reused for every poll (each poll is a new channel); after a failure the worker
reconnects with a growing delay.
"""

import threading
import time

from . import probe as srv

MAX_BACKOFF = 30
NO_GPU_DELAY = 30          # hosts without a GPU rarely change; poll them slowly
DISCOVERY_EVERY = 60       # seconds between Gadi compute node discoveries


def poll_delay(interval, fails):
    """Seconds between polls: the interval, longer after repeated failures."""
    if not fails:
        return interval
    return max(interval, min(MAX_BACKOFF, 2 ** min(fails, 5)))


class _HostWorker(threading.Thread):
    def __init__(self, monitor, host_info, hosts_by_alias):
        super().__init__(daemon=True, name=f"nvtop2i-{host_info['alias']}")
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

    def _error_result(self, exc):
        result = srv._new_result(self.host_info)
        result["error"] = srv._error_text(exc)
        return result

    def _query(self):
        """Poll over the open connection, connecting first when needed."""
        if self.client is None:
            self.client, self.jump_client = srv.open_connection(
                self.host_info, self.hosts_by_alias)
            transport = self.client.get_transport()
            if transport:
                transport.set_keepalive(15)
        return srv.run_on_client(self.client, self.host_info)

    def poll(self):
        """One poll. A dropped connection gets one immediate retry on a new one."""
        if self.host_info.get("is_local"):
            return srv.query_local_gpu()
        reused = self.client is not None
        try:
            return self._query()
        except (ValueError, KeyError, IndexError) as e:
            # the host answered with something we cannot parse: the
            # connection is fine, keep it
            return self._error_result(e)
        except Exception as e:
            self._close()
            if not reused:
                return self._error_result(e)
        try:
            return self._query()
        except Exception as e:
            self._close()
            return self._error_result(e)

    def run(self):
        mon = self.monitor
        while not mon.stopped.is_set():
            started = time.time()
            result = self.poll()
            if mon.stopped.is_set():
                break
            mon.publish(self.host_info["alias"], result)
            self.fails = 0 if result["status"] != "error" else self.fails + 1
            wait = poll_delay(mon.interval(), self.fails)
            if result["status"] == "no_gpu":
                wait = max(wait, NO_GPU_DELAY)
            wait = max(0.0, wait - (time.time() - started))
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
        threading.Thread(target=self._setup, daemon=True, name="nvtop2i-setup").start()

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
        """Start one worker per host of the SSH config, then keep looking for
        dynamically allocated nodes (Gadi) in the background."""
        try:
            hosts = (srv.HOSTS_LOADER() if srv.HOSTS_LOADER
                     else srv.parse_ssh_config(srv.SSH_CONFIG_PATH))
        except Exception as e:
            self._publish_problem("(ssh config)", f"Cannot read {srv.SSH_CONFIG_PATH}: {e}")
            return
        by_alias = {h["alias"]: h for h in hosts}
        for host_info in hosts:
            if self.stopped.is_set():
                return
            self._spawn(host_info, by_alias)
        while not self.stopped.is_set():
            try:
                for h in srv.discover_gadi_nodes(by_alias):
                    if h["alias"] not in by_alias and not self.stopped.is_set():
                        by_alias[h["alias"]] = h
                        self._spawn(h, by_alias)
            except Exception:
                pass   # discovery is best effort; configured hosts keep working
            self.stopped.wait(DISCOVERY_EVERY)

    def _publish_problem(self, alias, message):
        self.publish(alias, {"alias": alias, "hostname": alias, "user": "", "port": 0,
                             "status": "error", "error": message, "gpus": []})

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
