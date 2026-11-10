import base64
import subprocess

from nvtop2i import probe

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
    gpus = probe._build_gpus(GPU_OUT)
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
    g = probe._build_gpus(GPU_OUT_WSL)[0]
    assert g["fan_pct"] is None and g["power_w"] is None
    assert g["power_limit_w"] is None and g["pcie_gen"] is None
    assert g["clock_gr_mhz"] == 2400


def test_build_gpus_old_seven_columns():
    g = probe._build_gpus(GPU_OUT_OLD)[0]
    assert g["name"] == "Tesla T4" and g["fan_pct"] is None


def test_attach_processes_by_header_and_skips_system_users():
    gpus = probe._build_gpus(GPU_OUT)
    probe._attach_processes(gpus, PROC_OUT)
    procs = gpus[0]["processes"]
    assert [p["pid"] for p in procs] == [3093, 8064, 9000]
    assert procs[1]["type"] == "C+G" and procs[1]["gpu_memory_mb"] == 714
    assert procs[2]["command"] == "python train.py" and procs[2]["sm_pct"] == 69
    assert procs[0]["user"] == "brenoperucchi"
    assert gpus[1]["processes"] == []  # root is a system user


def test_attach_dmon():
    gpus = probe._build_gpus(GPU_OUT)
    probe._attach_dmon(gpus, DMON)
    assert gpus[0]["pcie_rx_mbs"] == 3 and gpus[0]["pcie_tx_mbs"] == 15


def test_build_nvidia_full_output():
    out = "NVIDIA\n" + GPU_OUT + "---SEP---\n" + PROC_OUT + "---DMON---\n" + DMON
    gpu_part, proc_part, vendor = probe._parse_combined_output(out)
    assert vendor == "nvidia"
    gpus = probe._build_nvidia(gpu_part, proc_part)
    assert gpus[0]["pcie_tx_mbs"] == 15
    assert len(gpus[0]["processes"]) == 3


def test_remote_command_has_no_single_quotes_and_roundtrips():
    cmd = probe._remote_command()
    assert "'" not in cmd
    assert cmd.startswith('bash -c "echo ') and cmd.endswith(' | base64 -d | bash"')
    encoded = cmd[len('bash -c "echo '):-len(' | base64 -d | bash"')]
    assert base64.b64decode(encoded).decode() == probe.COMBINED_CMD
    assert len(cmd) < 8000  # cmd.exe command line limit


def test_remote_command_runs_through_a_shell():
    # sshd hands the string to the user's shell; emulate that with sh -c
    out = subprocess.run(probe._remote_command(), shell=True,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    gpu_part, _, vendor = probe._parse_combined_output(out.stdout.strip())
    assert vendor in ("nvidia", "mx", "tpu")


def test_na_in_core_fields_does_not_drop_the_gpu():
    line = "0, NVIDIA GeForce RTX 5090, 32607, [N/A], [N/A], [N/A], [N/A], 2400, 14000, [N/A], [N/A], [N/A], [N/A], [N/A]"
    g = probe._build_gpus(line)[0]
    assert g["memory_used_mb"] == 0 and g["gpu_utilization_pct"] == 0
    assert g["temperature_c"] == 0 and g["memory_usage_pct"] == 0
    assert g["memory_total_mb"] == 32607


def test_script_keeps_commands_off_stdin():
    # bash reads the script from stdin on remote hosts, so a command that read
    # stdin would swallow the rest of it
    assert probe.COMBINED_CMD.rstrip().endswith("fi </dev/null")
    script = "if true; then cat; echo after-cat; fi </dev/null"
    out = subprocess.run(["bash"], input=script, capture_output=True, text=True, timeout=10)
    assert "after-cat" in out.stdout


SYS_BLOCK = """---SYS---
cpu  1000 0 500 8000 500 0 0 0 0 0
MemTotal:       65536000 kB
MemAvailable:   32768000 kB
0.80 0.60 0.50 1/1234 5678
16
TEMP 48500
---ENDSYS---
"""


def test_sys_block_gives_cpu_counters_memory_load_and_temperature():
    s = probe._parse_sys(SYS_BLOCK.split("---SYS---")[1].split("---ENDSYS---")[0])
    assert s["cpu_total"] == 10000 and s["cpu_busy"] == 1500   # idle and iowait are not busy
    assert s["mem_total_mb"] == 64000 and s["mem_used_mb"] == 32000 and s["mem_pct"] == 50
    assert s["load1"] == 0.8 and s["cores"] == 16 and s["cpu_temp_c"] == 48.5


def test_sys_block_without_proc_is_none_and_does_not_hide_the_gpus():
    assert probe._parse_sys("") is None
    gpu = "NVIDIA\n0, NVIDIA GeForce RTX 5090, 32607, 1200, 31407, 7, 41, 210, 405, 0, 30.5, 575.0, 5, 16"
    for out in (SYS_BLOCK + gpu, gpu):
        res = probe._fill_result({"alias": "a", "gpus": []}, out)
        assert res["status"] == "ok" and res["gpus"][0]["name"] == "NVIDIA GeForce RTX 5090"
    assert probe._fill_result({"alias": "a", "gpus": []}, SYS_BLOCK + gpu)["sys"]["cores"] == 16
    assert probe._fill_result({"alias": "a", "gpus": []}, gpu)["sys"] is None


AMD_BLOCK = ("---AMD---\n0000:04:00.0|Ellesmere [Radeon RX 470/480/570/570X/580/580X/590]|49|"
             "2744631296|8589934592|59000|784|3700|83|255||145000000|1294600000|1300|2000|"
             "8.0 GT/s PCIe|4\n---ENDAMD---\n")
NVIDIA_OUT = ("NVIDIA\n0, NVIDIA GeForce RTX 3080 Ti, 12288, 569, 11719, 7, 32, 210, 405, 0, "
              "10.5, 370.0, 1, 16")


def test_amd_card_is_read_from_the_sysfs_block():
    g = probe._build_amd_gpus(AMD_BLOCK.split("---AMD---")[1].split("---ENDAMD---")[0], 3)[0]
    assert g["index"] == 3 and g["name"] == "AMD Radeon RX 470/480/570/570X/580/580X/590"
    assert g["gpu_utilization_pct"] == 49 and g["memory_total_mb"] == 8192
    assert round(g["memory_used_mb"]) == 2617 and g["memory_usage_pct"] == 32.0
    assert g["temperature_c"] == 59 and round(g["fan_pct"]) == 33      # pwm 83/255
    assert g["power_w"] is None and g["power_limit_w"] == 145          # no power reading
    assert round(g["clock_gr_mhz"]) == 1295 and g["clock_mem_mhz"] == 2000
    assert g["pcie_gen"] == 3 and g["pcie_width"] == 4 and g["processes"] == []


def test_amd_card_sits_next_to_the_nvidia_cards_with_the_next_index():
    res = probe._fill_result({"alias": "a", "gpus": []}, AMD_BLOCK + NVIDIA_OUT)
    assert res["status"] == "ok"
    assert [(g["index"], g["name"][:6]) for g in res["gpus"]] == [(0, "NVIDIA"), (1, "AMD Ra")]


def test_amd_only_host_is_ok_and_empty_amd_block_changes_nothing():
    res = probe._fill_result({"alias": "a", "gpus": []}, AMD_BLOCK)
    assert res["status"] == "ok" and res["gpus"][0]["index"] == 0
    res = probe._fill_result({"alias": "a", "gpus": []}, "---AMD---\n---ENDAMD---\n" + NVIDIA_OUT)
    assert [g["index"] for g in res["gpus"]] == [0]
    res = probe._fill_result({"alias": "a", "gpus": []}, "---AMD---\n---ENDAMD---\n")
    assert res["status"] == "no_gpu"


def test_amd_snippet_runs_in_a_shell_and_finds_this_machines_cards():
    out = subprocess.run(["bash", "-c", probe._AMD_QUERY], capture_output=True,
                         text=True, timeout=30).stdout
    assert out.startswith("---AMD---") and out.rstrip().endswith("---ENDAMD---")
    for line in out.split("\n")[1:-2]:
        assert len(line.split("|")) >= 17


# The RTX 5090 of 2026-11-10: the driver lost the card and answers with text
# instead of numbers (seen on the real host)
GPU_OUT_NEEDS_RESET = """\
0, NVIDIA GeForce RTX 5090, 32607, 30264, 2343, [N/A], 47, [N/A], [N/A], [GPU requires reset], [N/A], [N/A], [N/A], [N/A]
"""


def test_gpu_that_requires_a_reset_is_flagged_as_a_fault():
    (gpu,) = probe._build_gpus(GPU_OUT_NEEDS_RESET)
    assert gpu["fault"] == "GPU requires reset"
    assert gpu["fan_pct"] is None            # still parsed, just empty


def test_plain_na_values_are_not_a_fault():
    (gpu,) = probe._build_gpus(GPU_OUT_WSL)
    assert gpu.get("fault") is None
