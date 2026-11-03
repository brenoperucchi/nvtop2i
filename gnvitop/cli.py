#!/usr/bin/env python3
"""CLI entry point for gnvitop."""

import argparse
import logging
import os
import signal
import socket
import webbrowser
import threading


def _kill_stale_gnvitop(port):
    """If the port is occupied by a previous gnvitop process, kill it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", port))
        sock.close()
        return  # Port is free
    except OSError:
        pass  # Port is in use

    # Find the PID holding the port (Linux only, via /proc)
    try:
        import subprocess
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "gnvitop" in line:
                # Extract pid from pid=XXXX
                for part in line.split(","):
                    if part.startswith("pid="):
                        pid = int(part.split("=")[1])
                        os.kill(pid, signal.SIGTERM)
                        print(f"Killed previous gnvitop (PID {pid}) on port {port}")
                        import time
                        time.sleep(0.5)
                        return
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        prog="gnvitop",
        description="Global nvitop: web-based GPU monitoring dashboard for remote servers via SSH.",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=5050,
        help="Port to run the server on (default: 5050)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open browser automatically",
    )
    parser.add_argument(
        "--ssh-config",
        default=None,
        help="Path to SSH config file (default: ~/.ssh/config)",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Enable GPU history recording to CSV",
    )
    parser.add_argument(
        "--csv",
        default=None,
        metavar="PATH",
        help="CSV file path for GPU history (default: /tmp/gnvitop_history.csv, requires --history)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=600,
        metavar="SECONDS",
        help="Sampling interval for history recording in seconds (default: 600, requires --history)",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch terminal UI (no browser, no web server)",
    )
    parser.add_argument(
        "--tui-refresh",
        type=int,
        default=30,
        metavar="SECONDS",
        help="TUI auto-refresh interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Output GPU availability as JSON for agent use, then exit",
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Show version and exit",
    )

    args = parser.parse_args()

    from . import __version__

    if args.version:
        print(f"gnvitop {__version__}")
        return

    # Agent mode — fetch once, print JSON, exit
    if args.agent:
        if args.ssh_config:
            from . import server
            server.SSH_CONFIG_PATH = args.ssh_config
        import json
        from .server import fetch_all_gpu_info
        results = fetch_all_gpu_info()
        output = []
        for host in results:
            if host["status"] != "ok":
                output.append({
                    "host": host["alias"],
                    "status": host["status"],
                    "error": host.get("error"),
                    "gpus": [],
                })
                continue
            gpus = []
            for gpu in host["gpus"]:
                gpus.append({
                    "index": gpu["index"],
                    "name": gpu["name"],
                    "memory_total_mb": gpu["memory_total_mb"],
                    "memory_used_mb": gpu["memory_used_mb"],
                    "memory_free_mb": gpu["memory_free_mb"],
                    "gpu_utilization_pct": gpu["gpu_utilization_pct"],
                    "available": (
                        len(gpu.get("processes", [])) == 0
                        if gpu["gpu_utilization_pct"] < 0
                        else gpu["gpu_utilization_pct"] < 10 and gpu["memory_used_mb"] < gpu["memory_total_mb"] * 0.1
                    ),
                })
            output.append({
                "host": host["alias"],
                "status": "ok",
                "gpus": gpus,
            })
        print(json.dumps(output, indent=2))
        return

    # TUI mode — skip Flask entirely
    if args.tui:
        if args.ssh_config:
            from . import server
            server.SSH_CONFIG_PATH = args.ssh_config
        from .tui import run_tui
        run_tui(ssh_config_path=args.ssh_config, refresh_interval=args.tui_refresh)
        return

    # Set custom SSH config path if provided
    if args.ssh_config:
        from . import server
        server.SSH_CONFIG_PATH = args.ssh_config

    # Kill stale gnvitop process if it's holding the port
    _kill_stale_gnvitop(args.port)

    from .server import app, _start_background_warmer
    _start_background_warmer()

    # Detect if running inside an SSH session
    is_ssh = bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"))

    # In SSH mode, auto-bind to 0.0.0.0 so the dashboard is network-accessible
    # (unless user explicitly set --host)
    host = args.host
    user_set_host = any(
        arg in ("--host",) for arg in os.sys.argv[1:]
    )
    if is_ssh and not user_set_host:
        host = "0.0.0.0"

    if is_ssh:
        # SSH_CONNECTION format: client_ip client_port server_ip server_port
        ssh_conn = os.environ.get("SSH_CONNECTION", "")
        parts = ssh_conn.split()
        server_ip = parts[2] if len(parts) >= 3 else "this_server_ip"
        display_url = f"http://{server_ip}:{args.port}"
    else:
        display_url = f"http://{host}:{args.port}"

    print(f"gnvitop v{__version__} — \033[1;36m{display_url}\033[0m")
    print("Press Ctrl+C to stop.\n")

    if not args.no_browser and not is_ssh:
        threading.Timer(1.0, lambda: webbrowser.open(display_url)).start()

    # Start history sampler (opt-in via --history)
    if args.history:
        from .db import init_db, set_csv_path, start_sampler
        from .server import fetch_all_gpu_info
        if args.csv:
            set_csv_path(args.csv)
        init_db()
        start_sampler(args.interval, fetch_all_gpu_info)

    # Suppress Flask/Werkzeug startup banner (we already printed our own)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    import click
    _original_echo = click.echo
    click.echo = lambda *a, **kw: None
    try:
        app.run(host=host, port=args.port, debug=False)
    finally:
        click.echo = _original_echo


if __name__ == "__main__":
    main()
