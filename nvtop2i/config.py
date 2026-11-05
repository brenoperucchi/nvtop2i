"""The nvtop2i config file (INI): hosts to monitor and the refresh interval.

Default location: $XDG_CONFIG_HOME/nvtop2i/config.ini, or ~/.config/nvtop2i/config.ini.
NVTOP2I_CONFIG overrides it. The file never holds passwords, only key paths.

    [general]
    refresh = 2

    [host lab]
    hostname = 10.0.0.5
    user = me
    port = 22
    identity_file = ~/.ssh/id_ed25519
    proxy_jump = bastion
"""

import configparser
import os

HOST_PREFIX = "host "
DEFAULT_REFRESH = 2


def config_path():
    env = os.environ.get("NVTOP2I_CONFIG")
    if env:
        return os.path.expanduser(env)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "nvtop2i", "config.ini")


def _parser():
    return configparser.ConfigParser(delimiters=("=",), interpolation=None)


def new_host(alias, hostname=None, user=None, port=22, identity_file=None, proxy_jump=None):
    return {"alias": alias, "hostname": hostname or None, "user": user or None,
            "port": int(port), "identity_file": identity_file or None,
            "proxy_jump": proxy_jump or None, "proxy_command": None}


def load(path=None):
    """Return (hosts, refresh). Raises OSError or ValueError on an unreadable file."""
    path = path or config_path()
    cp = _parser()
    with open(path, "r", encoding="utf-8") as f:
        cp.read_file(f)
    refresh = cp.getint("general", "refresh", fallback=DEFAULT_REFRESH)
    hosts = []
    for name in cp.sections():
        if not name.lower().startswith(HOST_PREFIX):
            continue
        sec = cp[name]
        ident = sec.get("identity_file")
        hosts.append(new_host(
            name[len(HOST_PREFIX):].strip(), sec.get("hostname"), sec.get("user"),
            sec.getint("port", 22), os.path.expanduser(ident) if ident else None,
            sec.get("proxy_jump")))
    return hosts, max(1, refresh)


def load_options(path=None):
    """UI switches from [general]; both default to on, and a missing or bad file is fine."""
    opts = {"show_cpu": True, "chart_temp": True}
    cp = _parser()
    try:
        with open(path or config_path(), "r", encoding="utf-8") as f:
            cp.read_file(f)
    except (OSError, configparser.Error):
        return opts
    for key in opts:
        try:
            opts[key] = cp.getboolean("general", key, fallback=True)
        except ValueError:
            pass
    return opts


def load_hosts(path=None):
    return load(path)[0]


def save(hosts, refresh=DEFAULT_REFRESH, path=None):
    """Write the config with owner-only permissions. Returns the path.

    The UI switches (show_cpu, chart_temp) already in the file are kept.
    """
    path = path or config_path()
    opts = load_options(path) if os.path.exists(path) else {}
    cp = _parser()
    cp["general"] = {"refresh": str(max(1, int(refresh)))}
    if os.path.exists(path):
        cp["general"].update({k: "yes" if v else "no" for k, v in opts.items()})
    for h in hosts:
        sec = {"port": str(h.get("port") or 22)}
        for key in ("hostname", "user", "identity_file", "proxy_jump"):
            if h.get(key):
                sec[key] = str(h[key])
        cp[HOST_PREFIX + h["alias"]] = sec
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        cp.write(f)
    os.chmod(path, 0o600)
    return path
