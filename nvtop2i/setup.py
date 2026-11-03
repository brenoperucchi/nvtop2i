"""`nvtop2i --setup`: asks about each host and writes the config file.

Passwords are only used once, to put your public key on the host; they are never
stored. Input and output go through arguments so the flow can be tested.
"""

import getpass
import os
import shlex
import subprocess

from . import config, probe

KEY_NAMES = ("id_ed25519", "id_ecdsa", "id_rsa")


def default_key():
    for name in KEY_NAMES:
        path = os.path.expanduser(f"~/.ssh/{name}")
        if os.path.exists(path):
            return path
    return None


def _yes(answer, default):
    answer = answer.strip().lower()
    return default if not answer else answer[0] == "y"


def check_host(host):
    """Try the host and return (ok, message). Never raises."""
    client = jump = None
    try:
        client, jump = probe.open_connection(host)
        res = probe.run_on_client(client, host)
        if res["status"] == "ok":
            return True, f"connected, {len(res['gpus'])} GPU(s) found"
        if res["status"] == "no_gpu":
            return True, "connected, but nvidia-smi found no GPU"
        return False, res.get("error") or "no answer"
    except Exception as e:   # reported to the user, never fatal
        return False, probe._error_text(e)
    finally:
        for c in (client, jump):
            if c:
                try:
                    c.close()
                except Exception:
                    pass


def ensure_public_key(key_path, say, ask):
    """Return the public key text for key_path, offering to create the key pair."""
    pub = key_path + ".pub"
    if not os.path.exists(key_path):
        if not _yes(ask(f"  {key_path} does not exist. Create it now? [Y/n] "), True):
            return None
        os.makedirs(os.path.dirname(key_path), mode=0o700, exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key_path],
                       check=True)
        say(f"  Created {key_path}")
    with open(pub, "r", encoding="utf-8") as f:
        return f.read().strip()


def install_key(host, pubkey, password):
    """Append pubkey to the host's authorized_keys, logging in with a password once."""
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host["hostname"] or host["alias"], port=host["port"], username=host["user"],
                   password=password, allow_agent=False, look_for_keys=False,
                   timeout=probe.SSH_TIMEOUT)
    try:
        line = shlex.quote(pubkey)
        cmd = ("umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
               f"grep -qxF {line} ~/.ssh/authorized_keys || echo {line} >> ~/.ssh/authorized_keys")
        _, out, _ = client.exec_command(cmd, timeout=probe.SSH_TIMEOUT)
        return out.channel.recv_exit_status() == 0
    finally:
        client.close()


def ask_host(say, ask, secret, check=check_host, install=install_key, key_for=ensure_public_key):
    """Ask for one host and test it. Returns the host dict or None when skipped."""
    alias = ask("Name for this host (blank to stop): ").strip()
    if not alias:
        return None
    hostname = ask(f"  Address or hostname [{alias}]: ").strip() or alias
    user = ask(f"  User [{getpass.getuser()}]: ").strip() or getpass.getuser()
    port = ask("  SSH port [22]: ").strip() or "22"
    key = default_key()
    shown = key or "none"
    key = ask(f"  Private key file [{shown}]: ").strip() or key
    jump = ask("  Jump host (blank for none): ").strip()
    host = config.new_host(alias, hostname, user, int(port), key, jump)

    ok, msg = check(host)
    say(f"  {'OK' if ok else 'Failed'}: {msg}")
    if not ok and "Authentication" in msg and key:
        if _yes(ask("  Install your public key using the password now? "
                    "(the password is not saved) [Y/n] "), True):
            pubkey = key_for(key, say, ask)
            if pubkey:
                try:
                    done = install(host, pubkey, secret(f"  Password for {user}@{hostname}: "))
                except Exception as e:   # wrong password, host without sh, ...
                    done = False
                    say(f"  Could not install the key: {probe._error_text(e)}")
                if done:
                    ok, msg = check(host)
                    say(f"  {'OK' if ok else 'Failed'}: {msg}")
    if not ok and not _yes(ask("  Keep this host anyway? [y/N] "), False):
        return ask_host(say, ask, secret, check, install, key_for) if _yes(
            ask("  Try again with other details? [Y/n] "), True) else None
    return host


def run_setup(path=None, say=print, ask=input, secret=getpass.getpass, **hooks):
    """The wizard. Returns the path written, or None when nothing was saved."""
    path = path or config.config_path()
    hosts, refresh = [], config.DEFAULT_REFRESH
    if os.path.exists(path):
        try:
            hosts, refresh = config.load(path)
        except (OSError, ValueError) as e:
            say(f"Could not read {path}: {e}")
    say(f"nvtop2i setup. The local GPUs are always shown; hosts go in {path}.")
    if hosts:
        say("Hosts already configured: " + ", ".join(h["alias"] for h in hosts))

    ssh_cfg = probe.parse_ssh_config(os.path.expanduser("~/.ssh/config"))
    ssh_cfg = [h for h in ssh_cfg if h["alias"] not in {x["alias"] for x in hosts}]
    if ssh_cfg and _yes(ask(f"Import hosts from ~/.ssh/config ({len(ssh_cfg)} found)? [y/N] "), False):
        for i, h in enumerate(ssh_cfg, 1):
            say(f"  {i}. {h['alias']}  {h['hostname'] or ''}")
        for tok in ask("  Numbers to import, comma separated (blank for none): ").replace(" ", "").split(","):
            if tok.isdigit() and 1 <= int(tok) <= len(ssh_cfg):
                hosts.append(ssh_cfg[int(tok) - 1])

    while True:
        host = ask_host(say, ask, secret, **hooks)
        if host is None:
            break
        hosts = [h for h in hosts if h["alias"] != host["alias"]] + [host]

    raw = ask(f"Refresh interval in seconds [{refresh}]: ").strip()
    if raw.isdigit() and int(raw) >= 1:
        refresh = int(raw)
    written = config.save(hosts, refresh, path)
    say(f"Saved {len(hosts)} host(s) to {written}. Run: nvtop2i")
    return written
