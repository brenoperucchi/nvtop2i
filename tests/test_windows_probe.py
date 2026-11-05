import subprocess
from types import SimpleNamespace

from nvtop2i import probe

GPU_LINE = ("0, NVIDIA GeForce RTX 5090, 32607, 1200, 31407, 7, 41, 210, 405, 0, "
            "30.5, 575.0, 5, 16")


def test_windows_local_probe_calls_nvidia_smi_without_a_shell(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(stdout=GPU_LINE + "\n")

    monkeypatch.setattr(probe.sys, "platform", "win32")
    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    result = probe.query_local_gpu()

    assert result["status"] == "ok"
    assert result["gpus"][0]["name"] == "NVIDIA GeForce RTX 5090"
    assert len(calls) == 1                                   # no pmon / dmon on WDDM
    cmd, kwargs = calls[0]
    assert isinstance(cmd, list) and cmd[0] == "nvidia-smi"  # a list: cmd.exe never sees it
    assert not kwargs.get("shell")
    assert kwargs["timeout"] == probe.COMMAND_TIMEOUT


def test_windows_local_probe_survives_a_hung_or_missing_nvidia_smi(monkeypatch):
    monkeypatch.setattr(probe.sys, "platform", "win32")
    for exc in (subprocess.TimeoutExpired("nvidia-smi", 15), FileNotFoundError()):
        def boom(cmd, **kwargs):
            raise exc
        monkeypatch.setattr(probe.subprocess, "run", boom)
        assert probe.query_local_gpu()["status"] != "ok"
