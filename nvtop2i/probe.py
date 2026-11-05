#!/usr/bin/env python3
"""Probe hosts over SSH, and the local machine, for GPU data."""

import base64
import getpass
import os
import re
import subprocess
import sys

import paramiko

SSH_CONFIG_PATH = os.path.expanduser("~/.ssh/config")
HOSTS_LOADER = None   # when set, called instead of reading SSH_CONFIG_PATH
SSH_TIMEOUT = 45
COMMAND_TIMEOUT = 15   # one GPU query takes well under a second; a hung one is cut here


class CommandTimeout(Exception):
    """The host is reachable but the GPU query did not answer in time."""

# ── nvidia-smi queries ────────────────────────────────────────────────────────
_GPU_QUERY = (
    "nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,"
    "utilization.gpu,temperature.gpu,clocks.gr,clocks.mem,fan.speed,"
    "power.draw,power.limit,pcie.link.gen.current,pcie.link.width.current"
    " --format=csv,noheader,nounits 2>/dev/null"
)
# Raw pmon output (columns are located by header, they differ between drivers),
# followed by a pid -> user table. The user column is widened so ps does not
# cut long names to "name+".
_PROC_QUERY = (
    "nvidia-smi pmon -c 1 -s um 2>/dev/null; echo '---PS---'; "
    "ps -eo pid=,user:32= 2>/dev/null"
)
# PCIe throughput per GPU in MB/s (rx, tx)
_DMON_QUERY = "nvidia-smi dmon -c 1 -s t 2>/dev/null"

# ── TPU queries (Google Cloud TPU) ───────────────────────────────────────────
_TPU_CHIP_QUERY = "ls /dev/accel* 2>/dev/null | wc -l"
_TPU_PROC_QUERY = (
    "ps -eo pid,user,comm 2>/dev/null"
    " | awk 'NR>1 && /python/ && !/awk/ {print $1\",0,0,\"$2\",\"$3}'"
    " | head -10"
)

# ── mx-smi queries (沐曦 MetaX GPUs) ─────────────────────────────────────────
_MX_PROC_QUERY = (
    r"mx-smi --show-all-process 2>/dev/null"
    r" | grep -E '^\|[[:space:]]+[0-9]'"
    r" | sed 's/|//g'"
    r" | awk '{print $1, $2, $NF}'"
    r" | while read gpu_idx pid mem; do"
    r' if [ -n "$pid" ]; then'
    r" user=$(ps -o user= -p $pid 2>/dev/null | tr -d ' ');"
    r' printf "%s,%s,%s,%s\n" "$gpu_idx" "$pid" "$mem" "$user";'
    r" fi; done"
)

# ── Auto-detect: try nvidia-smi first, fall back to mx-smi ───────────────────
# Output begins with "NVIDIA\n" or "MX\n" so the parser knows which format follows
COMBINED_CMD = (
    "if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then "
    "echo NVIDIA; " + _GPU_QUERY + "; echo '---SEP---'; " + _PROC_QUERY + "; "
    "echo '---DMON---'; " + _DMON_QUERY + "; "
    "elif command -v mx-smi >/dev/null 2>&1; then "
    "echo MX; mx-smi 2>/dev/null; echo '---SEP---'; " + _MX_PROC_QUERY + "; "
    "elif ls /dev/accel0 >/dev/null 2>&1; then "
    "echo TPU; " + _TPU_CHIP_QUERY + "; echo '---SEP---'; " + _TPU_PROC_QUERY + "; "
    # bash reads this script from stdin on remote hosts; keep commands off it
    "fi </dev/null"
)

CURRENT_USER = getpass.getuser()

# System users to filter out from GPU process list
SYSTEM_USERS = frozenset({
    "root", "gdm", "lightdm", "sddm", "nvidia-persistenced",
    "Xorg", "gnome-shell",
})

def parse_ssh_config(path):
    """Parse ~/.ssh/config and return a list of hosts."""
    hosts = []
    current = None

    if not os.path.exists(path):
        return hosts

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            key_match = re.match(r"^(\w+)\s+(.+)$", line)
            if not key_match:
                continue

            key, value = key_match.group(1), key_match.group(2)

            if key.lower() == "host":
                if "*" in value or "?" in value:
                    current = None
                    continue
                current = {
                    "alias": value,
                    "hostname": None,
                    "user": None,
                    "port": 22,
                    "identity_file": None,
                    "proxy_jump": None,
                    "proxy_command": None,
                }
                hosts.append(current)
            elif current is not None:
                if key.lower() == "hostname":
                    current["hostname"] = value
                elif key.lower() == "user":
                    current["user"] = value
                elif key.lower() == "port":
                    current["port"] = int(value)
                elif key.lower() == "identityfile":
                    current["identity_file"] = os.path.expanduser(value)
                elif key.lower() == "proxyjump":
                    # Take only the first jump host (chained jumps not supported)
                    current["proxy_jump"] = value.split(",")[0].strip()
                elif key.lower() == "proxycommand":
                    current["proxy_command"] = value

    return hosts


def _parse_combined_output(output):
    """Split combined command output into (gpu_part, proc_part, vendor).

    Output may begin with 'NVIDIA', 'MX', or 'TPU' to indicate accelerator vendor.
    Returns vendor as one of: 'nvidia', 'mx', 'tpu'.
    """
    vendor = "nvidia"
    lines = output.split("\n")
    if lines and lines[0].strip() == "MX":
        vendor = "mx"
        output = "\n".join(lines[1:])
    elif lines and lines[0].strip() == "NVIDIA":
        output = "\n".join(lines[1:])
    elif lines and lines[0].strip() == "TPU":
        vendor = "tpu"
        output = "\n".join(lines[1:])

    if "---SEP---" in output:
        gpu_part, proc_part = output.split("---SEP---", 1)
    else:
        gpu_part, proc_part = output, ""
    return gpu_part.strip(), proc_part.strip(), vendor


def _num(text):
    """Parse a nvidia-smi number; '[N/A]', '[Not Supported]' and '' become None."""
    text = (text or "").strip()
    if not text or text.startswith("["):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _build_gpus(gpu_part):
    """Parse GPU stats section into a list of GPU dicts."""
    gpus = []
    for line in gpu_part.split("\n"):
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 7:
            # nvidia-smi prints [N/A] for values a driver cannot report (seen on
            # WSL); a missing number must not drop the whole host
            mem_total = _num(parts[2]) or 0.0
            mem_used = _num(parts[3]) or 0.0
            mem_free = _num(parts[4]) or 0.0
            utilization = _num(parts[5]) or 0.0
            extra = parts[7:] + [""] * (7 - len(parts[7:]))
            pcie_gen = _num(extra[5])
            pcie_width = _num(extra[6])
            gpus.append({
                "index": int(parts[0]),
                "name": parts[1],
                "memory_total_mb": mem_total,
                "memory_used_mb": mem_used,
                "memory_free_mb": mem_free,
                "memory_usage_pct": round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0,
                "gpu_utilization_pct": utilization,
                "temperature_c": _num(parts[6]) or 0.0,
                "clock_gr_mhz": _num(extra[0]),
                "clock_mem_mhz": _num(extra[1]),
                "fan_pct": _num(extra[2]),
                "power_w": _num(extra[3]),
                "power_limit_w": _num(extra[4]),
                "pcie_gen": int(pcie_gen) if pcie_gen is not None else None,
                "pcie_width": int(pcie_width) if pcie_width is not None else None,
                "pcie_rx_mbs": None,
                "pcie_tx_mbs": None,
                "processes": [],
            })
    return gpus


def _build_mx_gpus(output):
    """Parse default mx-smi table output into GPU dicts.

    Each GPU occupies two adjacent table rows, e.g.:
      | 0       MetaX C500  Off | 0000:0e:00.0 | 0%  Native |
      | 36C  56W / 350W  P0     | 858/65536 MiB | Available  |
    """
    import re
    gpus = []
    lines = output.split("\n")
    # Row 1: index, name, utilisation
    row1_re = re.compile(
        r"\|\s*(\d+)\s+([\w ]+?)\s+(?:Off|On)\s*\|[^|]+\|\s*(\d+)%"
    )
    # Row 2: temperature, mem_used / mem_total MiB
    row2_re = re.compile(
        r"\|\s*(\d+(?:\.\d+)?)C\s+[^|]+\|\s*(\d+)/(\d+)\s+MiB"
    )
    i = 0
    while i < len(lines):
        m1 = row1_re.search(lines[i])
        if m1 and i + 1 < len(lines):
            m2 = row2_re.search(lines[i + 1])
            if m2:
                mem_used = float(m2.group(2))
                mem_total = float(m2.group(3))
                gpus.append({
                    "index": int(m1.group(1)),
                    "name": m1.group(2).strip(),
                    "memory_total_mb": mem_total,
                    "memory_used_mb": mem_used,
                    "memory_free_mb": mem_total - mem_used,
                    "memory_usage_pct": round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0,
                    "gpu_utilization_pct": float(m1.group(3)),
                    "temperature_c": float(m2.group(1)),
                    "processes": [],
                })
                i += 2
                continue
        i += 1
    return gpus


def _attach_mx_processes(gpus, proc_output):
    """Parse mx-smi process output (gpu_idx,pid,mem,user,exp) and attach to GPUs."""
    gpu_by_index = {g["index"]: g for g in gpus}
    for line in proc_output.split("\n"):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4 and parts[0].isdigit():
            user = parts[3] if parts[3] else "unknown"
            if user in SYSTEM_USERS:
                continue
            gpu_idx = int(parts[0])
            proc = {
                "pid": int(parts[1]),
                "gpu_memory_mb": float(parts[2]) if parts[2] else 0,
                "user": user,
                "command": "",
            }
            if gpu_idx in gpu_by_index:
                gpu_by_index[gpu_idx]["processes"].append(proc)


# ── TPU helpers ───────────────────────────────────────────────────────────────
_TPU_HBM_MB_PER_CHIP = {
    "v4": 32 * 1024,   # 32 GB HBM
    "v5e": 16 * 1024,  # 16 GB HBM
    "v6e": 32 * 1024,  # 32 GB HBM
}
_TPU_DEFAULT_HBM_MB = 32 * 1024


def _build_tpu_gpus(chip_count_output):
    """Build GPU-like dicts for each TPU chip.
    Memory is known spec; utilization is unknown until torch_xla is installed.
    Uses -1 as sentinel for 'unknown' in numeric fields.
    """
    try:
        num_chips = int(chip_count_output.strip().split()[0])
    except (ValueError, IndexError):
        num_chips = 4  # default for *-8 node
    hbm_mb = _TPU_DEFAULT_HBM_MB
    return [
        {
            "index": i,
            "name": "Google TPU v4",
            "memory_total_mb": hbm_mb,
            "memory_used_mb": -1,   # unknown without torch_xla
            "memory_free_mb": -1,
            "memory_usage_pct": -1,
            "gpu_utilization_pct": -1,
            "temperature_c": -1,
            "processes": [],
        }
        for i in range(num_chips)
    ]


def _attach_tpu_processes(gpus, proc_output):
    """Attach running Python processes to chip 0 (can't determine per-chip assignment)."""
    if not gpus or not proc_output.strip():
        return
    for line in proc_output.strip().split("\n"):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        user = parts[3] if len(parts) > 3 else "unknown"
        if user in SYSTEM_USERS:
            continue
        proc = {
            "pid": pid,
            "gpu_memory_mb": 0,
            "user": user,
            "command": parts[4] if len(parts) > 4 else "",
        }
        gpus[0]["processes"].append(proc)


def _make_ssh_client(hostname, port, user, identity_file, sock=None):
    """Create and connect a paramiko SSHClient."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {
        "hostname": hostname,
        "port": port,
        "username": user,
        "timeout": SSH_TIMEOUT,
        "banner_timeout": SSH_TIMEOUT,
        "auth_timeout": SSH_TIMEOUT,
        "allow_agent": True,
        "look_for_keys": True,
    }
    if identity_file:
        kwargs["key_filename"] = identity_file
    if sock is not None:
        kwargs["sock"] = sock
    client.connect(**kwargs)
    return client


def _new_result(host_info):
    alias = host_info["alias"]
    return {
        "alias": alias,
        "hostname": host_info["hostname"] or alias,
        "user": host_info["user"] or "unknown",
        "port": host_info["port"],
        "status": "error",
        "error": None,
        "gpus": [],
    }


def _fill_result(result, output):
    """Parse the combined command output into `result` (status, gpus, error)."""
    gpu_part, proc_part, vendor = _parse_combined_output(output)

    if not gpu_part:
        result["status"] = "no_gpu"
        result["error"] = "No supported GPU found (tried nvidia-smi, mx-smi, and TPU)"
        return result
    if vendor == "mx":
        gpus = _build_mx_gpus(gpu_part)
        if proc_part:
            _attach_mx_processes(gpus, proc_part)
    elif vendor == "tpu":
        gpus = _build_tpu_gpus(gpu_part)
        if proc_part:
            _attach_tpu_processes(gpus, proc_part)
        result["is_tpu"] = True
    else:
        gpus = _build_nvidia(gpu_part, proc_part)
    result["gpus"] = gpus
    if gpus:
        result["status"] = "ok"
    else:
        result["status"] = "no_gpu"
        result["error"] = "No valid accelerator data returned"
    return result


def _error_text(exc):
    """Short message for a failed connection or command."""
    if isinstance(exc, paramiko.AuthenticationException):
        return "Authentication failed"
    if isinstance(exc, paramiko.SSHException):
        return f"SSH error: {exc}"
    if isinstance(exc, CommandTimeout):
        return str(exc)
    if isinstance(exc, TimeoutError):
        return "Connection timed out"
    if isinstance(exc, OSError):
        return f"Connection failed: {exc}"
    return f"{type(exc).__name__}: {exc}"


def open_connection(host_info, hosts_by_alias=None):
    """Connect to a host, going through ProxyJump or ProxyCommand when set.

    Returns (client, jump_client); jump_client is None without a jump host.
    The caller closes both.
    """
    alias = host_info["alias"]
    hostname = host_info["hostname"] or alias
    user = host_info["user"]
    port = host_info["port"]

    jump_client = None
    try:
        sock = None
        proxy_alias = host_info.get("proxy_jump")
        proxy_cmd = host_info.get("proxy_command")
        if proxy_alias:
            # Resolve jump host info
            jump_info = (hosts_by_alias or {}).get(proxy_alias) or {
                "alias": proxy_alias,
                "hostname": proxy_alias,
                "user": None,
                "port": 22,
                "identity_file": None,
            }
            jump_host = jump_info.get("hostname") or proxy_alias
            jump_port = jump_info.get("port", 22)
            jump_user = jump_info.get("user")
            jump_key = jump_info.get("identity_file")
            jump_client = _make_ssh_client(jump_host, jump_port, jump_user, jump_key)
            sock = jump_client.get_transport().open_channel(
                "direct-tcpip", (hostname, port), ("", 0)
            )
        elif proxy_cmd:
            # ProxyCommand: execute the command and use its stdio as socket
            cmd = proxy_cmd.replace("%h", hostname).replace("%p", str(port))
            sock = paramiko.ProxyCommand(cmd)

        client = _make_ssh_client(hostname, port, user, host_info.get("identity_file"), sock=sock)
        return client, jump_client
    except Exception:
        if jump_client:
            try:
                jump_client.close()
            except Exception:
                pass
        raise


def run_on_client(client, host_info):
    """Run the GPU query on an open connection and return the host result.

    Each call opens a new channel, so one connection serves many polls.
    Connection problems propagate; the caller decides whether to reconnect.
    """
    result = _new_result(host_info)
    _, stdout, _ = client.exec_command(_remote_command(), timeout=COMMAND_TIMEOUT)
    try:
        output = stdout.read().decode("utf-8").strip()
    except TimeoutError:   # socket.timeout is an alias of it
        # drop the channel so the stuck command does not pile up on the host
        stdout.channel.close()
        raise CommandTimeout(f"nvidia-smi did not answer in {COMMAND_TIMEOUT}s") from None
    return _fill_result(result, output)


def _attach_processes(gpus, proc_output):
    """Parse `pmon` + `ps` output and attach processes to GPUs (skip system users).

    proc_output is the raw `nvidia-smi pmon -c 1 -s um` text, then a
    '---PS---' line, then `ps -eo pid=,user:32=` lines. pmon columns are
    located through its header because they differ between driver versions.
    """
    pmon_text, _, ps_text = proc_output.partition("---PS---")
    users = {}
    for line in ps_text.split("\n"):
        bits = line.split()
        if len(bits) >= 2 and bits[0].isdigit():
            users[int(bits[0])] = bits[1]

    gpu_by_index = {g["index"]: g for g in gpus}
    names = None
    for line in pmon_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            fields = line.lstrip("#").split()
            if names is None and "pid" in fields:
                names = fields
            continue
        if names is None:
            continue
        cols = line.split(None, len(names) - 1)
        row = dict(zip(names, cols))
        pid = row.get("pid", "-")
        if not pid.isdigit() or not row.get("gpu", "").isdigit():
            continue
        user = users.get(int(pid), "unknown")
        if user in SYSTEM_USERS:
            continue
        gpu_idx = int(row["gpu"])
        proc = {
            "pid": int(pid),
            "gpu_memory_mb": _num(row.get("fb")) or 0,
            "user": user,
            "command": row.get("command", "").strip(),
            "type": row.get("type", ""),
            "sm_pct": _num(row.get("sm")),
        }
        if gpu_idx in gpu_by_index:
            gpu_by_index[gpu_idx]["processes"].append(proc)


def _attach_dmon(gpus, dmon_output):
    """Attach PCIe RX/TX throughput (MB/s) from `nvidia-smi dmon -s t` output."""
    gpu_by_index = {g["index"]: g for g in gpus}
    for line in dmon_output.split("\n"):
        bits = line.split()
        if len(bits) >= 3 and bits[0].isdigit() and int(bits[0]) in gpu_by_index:
            gpu = gpu_by_index[int(bits[0])]
            gpu["pcie_rx_mbs"] = _num(bits[1])
            gpu["pcie_tx_mbs"] = _num(bits[2])


def _build_nvidia(gpu_part, proc_part):
    """Build GPU dicts from the NVIDIA sections of the combined output."""
    gpus = _build_gpus(gpu_part)
    proc_part, _, dmon_part = proc_part.partition("---DMON---")
    if proc_part.strip():
        _attach_processes(gpus, proc_part)
    if dmon_part.strip():
        _attach_dmon(gpus, dmon_part)
    return gpus


def _remote_command():
    """Command line that runs COMBINED_CMD on a remote host.

    The script travels base64-encoded so it contains no quotes: single quotes
    break on Windows OpenSSH servers whose default shell is cmd.exe. The script
    is read from stdin by bash, so nothing inside it may read stdin.
    """
    encoded = base64.b64encode(COMBINED_CMD.encode("utf-8")).decode("ascii")
    return 'bash -c "echo ' + encoded + ' | base64 -d | bash"'


def _local_windows_output():
    """Same text COMBINED_CMD prints, built without a POSIX shell.

    cmd.exe cannot run the sh script (command -v, ps, 2>/dev/null), so on
    Windows nvidia-smi is called directly. pmon and dmon are not supported by
    the WDDM driver and usually print nothing, so those sections stay empty.
    """
    def smi(args):
        try:
            return subprocess.run(
                ["nvidia-smi"] + args, capture_output=True, text=True, timeout=30
            ).stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    query = _GPU_QUERY.replace(" 2>/dev/null", "")
    fields = query.split("--query-gpu=")[1].split(" --format")[0]
    gpus = smi(["--query-gpu=" + fields, "--format=csv,noheader,nounits"])
    if not gpus:
        return ""
    pmon = smi(["pmon", "-c", "1", "-s", "um"])
    dmon = smi(["dmon", "-c", "1", "-s", "t"])
    return ("NVIDIA\n" + gpus + "\n---SEP---\n" + pmon + "\n---PS---\n"
            "\n---DMON---\n" + dmon)


def query_local_gpu():
    """Query the local machine for GPU information (single subprocess call)."""
    import socket

    hostname = socket.gethostname()
    result = {
        "alias": "localhost",
        "hostname": hostname,
        "user": CURRENT_USER,
        "port": 0,
        "status": "error",
        "error": None,
        "gpus": [],
        "is_local": True,
    }

    try:
        if sys.platform == "win32":
            output = _local_windows_output()
        else:
            output = subprocess.run(
                COMBINED_CMD, shell=True, capture_output=True, text=True, timeout=30
            ).stdout.strip()
        _fill_result(result, output)

    except FileNotFoundError:
        result["status"] = "no_gpu"
        result["error"] = "nvidia-smi not found"
    except subprocess.TimeoutExpired:
        result["error"] = "nvidia-smi timed out"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def _sort_results(results):
    order = {"ok": 0, "connecting": 1, "no_gpu": 2, "error": 3}
    results.sort(key=lambda x: (
        0 if x.get("is_local") else 1,
        order.get(x["status"], 3),
        -len(x.get("gpus", [])),
        x["alias"],
    ))
    return results


def discover_gadi_nodes(hosts_by_alias):
    """SSH to each gadi-like login node and discover allocated GPU compute nodes via qstat.

    Returns a list of host_info dicts for any active job nodes found.
    A host is treated as a Gadi login node if its HostName ends with '.nci.org.au'
    and it has no ProxyJump (i.e. it is itself the jump host).
    """
    discovered = []
    for alias, info in hosts_by_alias.items():
        hostname = info.get("hostname") or alias
        if not hostname.endswith(".nci.org.au"):
            continue
        if info.get("proxy_jump"):
            continue  # skip compute nodes, only query login nodes
        # SSH to login node and run qstat to find allocated nodes
        try:
            client = _make_ssh_client(
                hostname, info.get("port", 22),
                info.get("user"), info.get("identity_file"),
            )
            _, stdout, _ = client.exec_command(
                "qstat -u $(whoami) -n 2>/dev/null | grep -oE 'gadi-gpu-[a-z0-9-]+' | sort -u",
                timeout=SSH_TIMEOUT,
            )
            node_names = [n.strip() for n in stdout.read().decode().splitlines() if n.strip()]
            client.close()
        except Exception:
            continue

        for node in node_names:
            node_hostname = f"{node}.gadi.nci.org.au"
            discovered.append({
                "alias": node,
                "hostname": node_hostname,
                "user": info.get("user"),
                "port": 22,
                "identity_file": info.get("identity_file"),
                "proxy_jump": alias,
            })

    return discovered
