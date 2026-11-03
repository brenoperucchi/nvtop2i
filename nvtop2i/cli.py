#!/usr/bin/env python3
"""Command line entry point for nvtop2i."""

import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="nvtop2i",
        description="nvtop-style GPU monitor for the local machine and several hosts over SSH.",
    )
    parser.add_argument(
        "--ssh-config",
        default=None,
        help="Path to the SSH config file (default: ~/.ssh/config)",
    )
    parser.add_argument(
        "-r", "--refresh",
        type=lambda v: max(1, int(v)),
        default=2,
        metavar="SECONDS",
        help="Refresh interval in seconds, at least 1 (default: 2)",
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

    from .tui import run_tui
    run_tui(ssh_config_path=args.ssh_config, refresh_interval=args.refresh)


if __name__ == "__main__":
    main()
