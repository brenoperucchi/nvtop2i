import sys

import pytest


@pytest.fixture(autouse=True)
def _no_real_config(tmp_path, monkeypatch):
    monkeypatch.setenv("NVTOP2I_CONFIG", str(tmp_path / "none.ini"))

from nvtop2i import cli


@pytest.mark.parametrize("given,expected", [(["--refresh", "0"], 1),
                                            (["-r", "-5"], 1),
                                            (["--refresh", "7"], 7),
                                            ([], 2)])
def test_refresh_has_a_floor_of_one_second(monkeypatch, given, expected):
    seen = {}
    monkeypatch.setattr(sys, "argv", ["nvtop2i"] + given)
    monkeypatch.setattr("nvtop2i.tui.run_tui",
                        lambda ssh_config_path=None, refresh_interval=2: seen.update(r=refresh_interval))
    cli.main()
    assert seen["r"] == expected


def test_ssh_config_is_passed_to_the_tui(monkeypatch):
    seen = {}
    monkeypatch.setattr(sys, "argv", ["nvtop2i", "--ssh-config", "/tmp/cfg"])
    monkeypatch.setattr("nvtop2i.tui.run_tui",
                        lambda ssh_config_path=None, refresh_interval=2: seen.update(p=ssh_config_path))
    cli.main()
    assert seen["p"] == "/tmp/cfg"


def test_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["nvtop2i", "--version"])
    cli.main()
    assert capsys.readouterr().out.startswith("nvtop2i 0.")
