"""File log for connection events. The TUI owns the terminal, so nothing goes to stderr.

Default: $XDG_STATE_HOME/nvtop2i/nvtop2i.log, or ~/.local/state/nvtop2i/nvtop2i.log.
NVTOP2I_LOG overrides the path.
"""

import logging
import logging.handlers
import os

LOGGER = "nvtop2i"


def log_path():
    env = os.environ.get("NVTOP2I_LOG")
    if env:
        return os.path.expanduser(env)
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "nvtop2i", "nvtop2i.log")


def setup_logging():
    """Attach a rotating file handler once; failures to open the file are ignored."""
    logger = logging.getLogger(LOGGER)
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers):
        return log_path()
    path = log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=512_000, backupCount=2)
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return path
