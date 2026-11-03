import base64
import subprocess

from gnvitop import server

GPU_OUT = """\
0, NVIDIA GeForce RTX 3080 Ti, 12288, 3340, 8608, 20, 43, 300, 405, 45, 36.83, 300.00, 1, 8
1, NVIDIA GeForce RTX 4090, 24564, 2, 24162, 0, 32, 210, 405, 30, 19.06, 500.00, 4, 8
"""

# Windows host through WSL: fan, power and PCIe come back as [N/A]
GPU_OUT_WSL = """\
0, NVIDIA GeForce RTX 5090, 32607, 31900, 500, 69, 45, 2400, 14000, [N/A], [N/A], [N/A], [N/A], [N/A]
"""

# Old query format: only the first 7 columns
GPU_OUT_OLD = "0, Tesla T4, 15360, 100, 15260, 5, 40\n"

PMON = """\
# gpu         pid   type     sm    mem    enc    dec    jpg    ofa     fb   ccpm    command
# Idx           #    C/G      %      %      %      %      %      %     MB     MB    name
    0       3093     G     19     26      -      -      -      -    529      0    Hyprland
    0       8064   C+G      -      -      -      -      -      -    714      0    voxtype
    0       9000     C     69     12      -      -      -      -  31000      0    python train.py
    1       1111     G      -      -      -      -      -      -      4      0    Xwayland
    1          -     -      -      -      -      -      -      -      -      -    -
"""
PS = """\
 3093 brenoperucchi
 8064 brenoperucchi
 9000 wsl
 1111 root
"""
PROC_OUT = PMON + "---PS---\n" + PS
DMON = """\
# gpu  rxpci  txpci
# Idx   MB/s   MB/s
    0      3     15
    1      0      0
"""


def test_build_gpus_extended_columns():
    gpus = server._build_gpus(GPU_OUT)
    assert len(gpus) == 2
    g = gpus[0]
    assert g["name"] == "NVIDIA GeForce RTX 3080 Ti"
    assert g["clock_gr_mhz"] == 300 and g["clock_mem_mhz"] == 405
    assert g["fan_pct"] == 45
    assert g["power_w"] == 36.83 and g["power_limit_w"] == 300
    assert (g["pcie_gen"], g["pcie_width"]) == (1, 8)
    assert gpus[1]["pcie_gen"] == 4
    # keys the web dashboard relies on are untouched
    assert g["memory_used_mb"] == 3340 and g["gpu_utilization_pct"] == 20
    assert g["temperature_c"] == 43 and g["processes"] == []


def test_build_gpus_na_values_become_none():
    g = server._build_gpus(GPU_OUT_WSL)[0]
    assert g["fan_pct"] is None and g["power_w"] is None
    assert g["power_limit_w"] is None and g["pcie_gen"] is None
    assert g["clock_gr_mhz"] == 2400


def test_build_gpus_old_seven_columns():
    g = server._build_gpus(GPU_OUT_OLD)[0]
    assert g["name"] == "Tesla T4" and g["fan_pct"] is None


def test_attach_processes_by_header_and_skips_system_users():
    gpus = server._build_gpus(GPU_OUT)
    server._attach_processes(gpus, PROC_OUT)
    procs = gpus[0]["processes"]
    assert [p["pid"] for p in procs] == [3093, 8064, 9000]
    assert procs[1]["type"] == "C+G" and procs[1]["gpu_memory_mb"] == 714
    assert procs[2]["command"] == "python train.py" and procs[2]["sm_pct"] == 69
    assert procs[0]["user"] == "brenoperucchi"
    assert gpus[1]["processes"] == []  # root is a system user


def test_attach_dmon():
    gpus = server._build_gpus(GPU_OUT)
    server._attach_dmon(gpus, DMON)
    assert gpus[0]["pcie_rx_mbs"] == 3 and gpus[0]["pcie_tx_mbs"] == 15


def test_build_nvidia_full_output():
    out = "NVIDIA\n" + GPU_OUT + "---SEP---\n" + PROC_OUT + "---DMON---\n" + DMON
    gpu_part, proc_part, vendor = server._parse_combined_output(out)
    assert vendor == "nvidia"
    gpus = server._build_nvidia(gpu_part, proc_part)
    assert gpus[0]["pcie_tx_mbs"] == 15
    assert len(gpus[0]["processes"]) == 3


def test_remote_command_has_no_single_quotes_and_roundtrips():
    cmd = server._remote_command()
    assert "'" not in cmd
    assert cmd.startswith('bash -c "echo ') and cmd.endswith(' | base64 -d | bash"')
    encoded = cmd[len('bash -c "echo '):-len(' | base64 -d | bash"')]
    assert base64.b64decode(encoded).decode() == server.COMBINED_CMD
    assert len(cmd) < 8000  # cmd.exe command line limit


def test_remote_command_runs_through_a_shell():
    # sshd hands the string to the user's shell; emulate that with sh -c
    out = subprocess.run(server._remote_command(), shell=True,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    gpu_part, _, vendor = server._parse_combined_output(out.stdout.strip())
    assert vendor in ("nvidia", "mx", "tpu")


def test_na_in_core_fields_does_not_drop_the_gpu():
    line = "0, NVIDIA GeForce RTX 5090, 32607, [N/A], [N/A], [N/A], [N/A], 2400, 14000, [N/A], [N/A], [N/A], [N/A], [N/A]"
    g = server._build_gpus(line)[0]
    assert g["memory_used_mb"] == 0 and g["gpu_utilization_pct"] == 0
    assert g["temperature_c"] == 0 and g["memory_usage_pct"] == 0
    assert g["memory_total_mb"] == 32607


def test_script_keeps_commands_off_stdin():
    # bash reads the script from stdin on remote hosts, so a command that read
    # stdin would swallow the rest of it
    assert server.COMBINED_CMD.rstrip().endswith("fi </dev/null")
    script = "if true; then cat; echo after-cat; fi </dev/null"
    out = subprocess.run(["bash"], input=script, capture_output=True, text=True, timeout=10)
    assert "after-cat" in out.stdout
