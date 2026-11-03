import sys

import pytest

from gnvitop import cli


@pytest.mark.parametrize("given,expected", [(["--tui-refresh", "0"], 1),
                                            (["--tui-refresh", "-5"], 1),
                                            (["--tui-refresh", "7"], 7),
                                            ([], 2)])
def test_tui_refresh_has_a_floor_of_one_second(monkeypatch, given, expected):
    seen = {}
    monkeypatch.setattr(sys, "argv", ["gnvitop", "--tui"] + given)
    monkeypatch.setattr("gnvitop.tui.run_tui",
                        lambda ssh_config_path=None, refresh_interval=2: seen.update(r=refresh_interval))
    cli.main()
    assert seen["r"] == expected
