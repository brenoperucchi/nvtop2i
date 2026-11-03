#!/usr/bin/env python3
"""Command line entry point for nvtop2i."""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="nvtop2i",
        description="nvtop-style GPU monitor for the local machine and several hosts over SSH.",
    )
    parser.add_argument(
        "--ssh-config",
        default=None,
        help="Read hosts from this SSH config file instead of the nvtop2i config",
    )
    parser.add_argument(
        "-r", "--refresh",
        type=lambda v: max(1, int(v)),
        default=None,
        metavar="SECONDS",
        help="Refresh interval in seconds, at least 1 (default: from the config, else 2)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Ask about your hosts and write the config file",
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Show version and exit",
    )
    args = parser.parse_args()

    from . import __version__

    if args.version:
        print(f"nvtop2i {__version__}")
        return

    from . import config
    path = config.config_path()

    if args.setup:
        from .setup import run_setup
        try:
            run_setup(path)
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled, nothing saved.")
        return

    refresh = args.refresh
    if not args.ssh_config:
        if not os.path.exists(path) and sys.stdin.isatty() and sys.stdout.isatty():
            from .setup import run_setup
            print(f"No config found at {path}.")
            answer = input("Run the setup now? [Y/n] ").strip().lower()
            if not answer or answer[0] == "y":
                try:
                    run_setup(path)
                except (KeyboardInterrupt, EOFError):
                    print("\nSetup cancelled, nothing saved.")
                    return
        if os.path.exists(path):
            from . import probe
            try:
                _, cfg_refresh = config.load(path)
            except (OSError, ValueError) as e:
                sys.exit(f"nvtop2i: cannot read {path}: {e}")
            probe.HOSTS_LOADER = lambda: config.load_hosts(path)
            refresh = refresh or cfg_refresh

    from .tui import run_tui
    run_tui(ssh_config_path=args.ssh_config, refresh_interval=refresh or 2)


if __name__ == "__main__":
    main()
