"""GPU usage history — appends to a CSV file."""

import csv
import os
import threading
import time

_CSV_PATH = "/tmp/gnvitop_history.csv"
_HEADERS = [
    "timestamp", "host_alias", "hostname",
    "gpu_index", "gpu_name",
    "mem_total_mb", "mem_used_mb", "gpu_util_pct", "temp_c",
    "pid", "user", "command", "gpu_mem_mb",
]
_lock = threading.Lock()


def set_csv_path(path):
    global _CSV_PATH
    _CSV_PATH = path


def init_db():
    if not os.path.exists(_CSV_PATH):
        with open(_CSV_PATH, "w", newline="") as f:
            csv.writer(f).writerow(_HEADERS)
    print(f"  History: {_CSV_PATH}")


def record_snapshot(hosts_data):
    ts = int(time.time())
    rows = []
    for host in hosts_data:
        if host.get("status") != "ok":
            continue
        alias = host["alias"]
        hostname = host.get("hostname", "")
        for gpu in host.get("gpus", []):
            base = [
                ts, alias, hostname,
                gpu["index"], gpu["name"],
                gpu["memory_total_mb"], gpu["memory_used_mb"],
                gpu["gpu_utilization_pct"], gpu["temperature_c"],
            ]
            procs = gpu.get("processes", [])
            if procs:
                for proc in procs:
                    rows.append(base + [
                        proc["pid"], proc["user"],
                        proc.get("command", ""), proc["gpu_memory_mb"],
                    ])
            else:
                rows.append(base + ["", "", "", ""])

    if not rows:
        return
    with _lock:
        with open(_CSV_PATH, "a", newline="") as f:
            csv.writer(f).writerows(rows)


def start_sampler(interval_seconds, fetch_fn):
    def _loop():
        while True:
            try:
                record_snapshot(fetch_fn())
            except Exception:
                pass
            time.sleep(interval_seconds)

    threading.Thread(target=_loop, daemon=True).start()
