import os
import stat
import sys

from nvtop2i import cli, config, setup


def test_save_and_load_roundtrip_with_private_permissions(tmp_path):
    path = str(tmp_path / "sub" / "config.ini")
    hosts = [config.new_host("lab", "10.0.0.5", "me", 2222, "/k/id", "bastion"),
             config.new_host("plain")]
    config.save(hosts, 5, path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    got, refresh = config.load(path)
    assert refresh == 5
    assert got[0] == hosts[0]
    assert got[1]["alias"] == "plain" and got[1]["port"] == 22 and got[1]["hostname"] is None


def test_refresh_has_a_floor_and_missing_general_uses_the_default(tmp_path):
    path = tmp_path / "c.ini"
    path.write_text("[general]\nrefresh = 0\n[host a]\nhostname = h\n")
    assert config.load(str(path)) == ([config.new_host("a", "h")], 1)
    path.write_text("[host a]\nhostname = h\n")
    assert config.load(str(path))[1] == config.DEFAULT_REFRESH


def test_config_path_follows_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NVTOP2I_CONFIG", str(tmp_path / "x.ini"))
    assert config.config_path() == str(tmp_path / "x.ini")
    monkeypatch.delenv("NVTOP2I_CONFIG")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.config_path() == str(tmp_path / "nvtop2i" / "config.ini")


def scripted(answers):
    it = iter(answers)
    return lambda prompt="": next(it)


def test_wizard_writes_the_host_and_never_the_password(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))   # no real ~/.ssh/config or keys
    path = str(tmp_path / "config.ini")
    tries = []

    def check(host):
        tries.append(1)
        return (len(tries) > 1, "Authentication failed" if len(tries) == 1 else "connected, 1 GPU(s) found")

    installed = []
    ask = scripted([
        "lab", "10.0.0.5", "me", "", "/k/id", "",   # host details
        "y",                                         # install key with password
        "",                                          # next host: stop
        "3",                                         # refresh
    ])
    setup.run_setup(path, say=lambda *_: None, ask=ask, secret=lambda p: "s3cret",
                    check=check, install=lambda h, k, pw: installed.append(pw) or True,
                    key_for=lambda *_: "ssh-ed25519 AAAA test")
    assert installed == ["s3cret"]
    text = open(path).read()
    assert "s3cret" not in text
    hosts, refresh = config.load(path)
    assert refresh == 3 and hosts[0]["alias"] == "lab" and hosts[0]["identity_file"] == "/k/id"


def test_wizard_can_drop_a_failing_host(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = str(tmp_path / "config.ini")
    ask = scripted(["bad", "", "", "", "", "",   # details, key blank
                    "n",                          # keep anyway? no
                    "n",                          # try again? no
                    "",                           # stop
                    ""])                          # refresh default
    setup.run_setup(path, say=lambda *_: None, ask=ask, secret=lambda p: "",
                    check=lambda h: (False, "Connection timed out"))
    assert config.load(path)[0] == []


def test_cli_uses_the_config_hosts_and_refresh(monkeypatch, tmp_path):
    from nvtop2i import probe
    path = tmp_path / "c.ini"
    config.save([config.new_host("lab", "h")], 4, str(path))
    monkeypatch.setenv("NVTOP2I_CONFIG", str(path))
    seen = {}
    monkeypatch.setattr(sys, "argv", ["nvtop2i"])
    monkeypatch.setattr("nvtop2i.tui.run_tui",
                        lambda ssh_config_path=None, refresh_interval=2: seen.update(r=refresh_interval))
    monkeypatch.setattr(probe, "HOSTS_LOADER", None)
    cli.main()
    assert seen["r"] == 4
    assert probe.HOSTS_LOADER()[0]["alias"] == "lab"
    monkeypatch.setattr(sys, "argv", ["nvtop2i", "-r", "9"])
    cli.main()
    assert seen["r"] == 9
    monkeypatch.setattr(probe, "HOSTS_LOADER", None)
