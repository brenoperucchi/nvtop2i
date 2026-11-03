# nvtop2i

A terminal GPU monitor in the style of [nvtop](https://github.com/Syllo/nvtop) that shows your own machine and any number of hosts reachable over SSH on one screen.

Each GPU gets the familiar nvtop header (clocks, temperature, fan, power, PCIe link and throughput, utilization and memory bars) plus a short history graph. Below each GPU is a chart of its utilization and memory over the last minute or so. `F9` swaps the charts for a process table covering all hosts.

```
 nvtop2i  3 GPUs on 2 hosts                                    refresh 2s   updated 12:02:24
 ────────────────────────────────────────────────────────────────────────────────────────────

 ▾ localhost [Local]
 Device 0 [NVIDIA GeForce RTX 3080 Ti]                  PCIe GEN 4@ 8x  RX: 5.4 MB/s  TX: 2.0 MB/s
 GPU 1230MHz  MEM 810MHz   TEMP 45°C  FAN 45%  POW 47 / 300 W
 GPU[|||||||||||||                             37%]  MEM[|||||||||            3.526Gi/12.000Gi]
 hist GPU ▁▂▃▅▇▆▅▃▂▁▂▃▅▆▇▅▃▂▁▂▃▅▇  MEM ▃▃▃▃▃▃▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄  TEMP ▃▃▃▃▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄

 ▾ lab-server [Online]
 Device 0 [NVIDIA GeForce RTX 5090]                     PCIe GEN 4@16x  RX: 18.0 MB/s  TX: 19.0 MB/s
 ...

 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │ HOST       GPU PID     USER          TYPE GPU MEM GPU% COMMAND                           │
 │ lab-server 0   41200   wsl           C    31.0GiB  69% ollama                            │
 │ localhost  0   3093    me            G     515MiB  35% Hyprland                          │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
 h Hosts  s Sort:mem  f Filter  F5 Kill  i Interval:2s  c Compact  v View:procs  q Quit
```

## Install

```
uv tool install git+https://github.com/brenoperucchi/nvtop2i
```

or with pip:

```
pip install git+https://github.com/brenoperucchi/nvtop2i
```

It is written in Python 3 (developed on 3.13) and depends on `paramiko`. Each monitored host needs `nvidia-smi` in the `PATH` of a non-interactive `bash`. SSH access has to work without a password prompt (keys or an agent).

## Usage

```
nvtop2i --setup                  # answer a few questions; hosts are saved for next time
nvtop2i                          # local GPUs plus the hosts from the config
nvtop2i -r 5                     # refresh every 5 seconds (default 2, minimum 1)
nvtop2i --ssh-config ./gpu_hosts # use an SSH config file instead of the nvtop2i config
```

The first run without a config offers to start the setup. It asks for each host's name, address, user, port, private key and optional jump host, then tests the connection. If the key is rejected it can install your public key using the password once; the password is not saved. The result goes to `~/.config/nvtop2i/config.ini` (or `$XDG_CONFIG_HOME/nvtop2i/config.ini`, or the path in `NVTOP2I_CONFIG`) with owner-only permissions:

```ini
[general]
refresh = 2

[host lab]
hostname = 10.0.0.5
user = me
port = 22
identity_file = ~/.ssh/id_ed25519
proxy_jump = bastion
```

You can edit the file by hand. The local machine is always included. With `--ssh-config`, every `Host` entry of that file is polled instead, so a file that lists only the machines with GPUs works best. `ProxyJump` and `ProxyCommand` are supported there.

Each host has its own thread and keeps one SSH connection open, so a slow or dead host only affects its own row. After a failure the connection is retried with a growing delay. A host that has not answered for three refresh intervals (at least 10 seconds) is marked with the time since its last update.

## Keys

| Key | Action |
|---|---|
| `←` `→` | select a host |
| `↑` `↓` | select a process |
| `h` / `F2` | fold or unfold the selected host |
| `s` / `F3` | cycle the process sort (process table only): memory, GPU %, PID, user, host |
| `f` or `/` / `F4` | filter processes (process table only) by host, user or command (Enter applies, Esc clears) |
| `i` / `F6` | next refresh interval: 1, 2, 5, 10 or 30 seconds |
| `c` / `F8` | compact view, one line per GPU |
| `v` or `Tab` / `F9` | switch between the GPU charts (default) and the process table |
| `r` | refresh now |
| `F10`, `q` | quit |

The view switches to compact on its own when the terminal is narrower than 100 columns or too short for the full layout. `F5 Kill` is shown greyed out; killing processes is not implemented.

Bars are green below 50 %, yellow up to 80 % and red above. Temperature is green below 60 °C, yellow up to 80 °C and red above.

## Notes

- PCIe throughput comes from `nvidia-smi dmon` and is reported in MB/s.
- On Windows hosts that run `nvidia-smi` inside WSL, the process list is usually empty and fan, power or PCIe values may show as `--`.
- Windows hosts whose OpenSSH default shell is `cmd.exe` work because the probe script is sent base64-encoded instead of single-quoted.
- MetaX (`mx-smi`) and Google Cloud TPU hosts are detected and shown with the one-line layout, without clocks, fan or PCIe fields.
- Hosts under `*.nci.org.au` are treated as Gadi login nodes, and the GPU compute nodes allocated to your jobs are discovered every minute.

## Development

```
uv run python -m pytest
```

The layout code builds plain lines of text, so most of the interface is tested without a terminal.

## Credits and license

nvtop2i started from [gnvitop](https://github.com/Linwei94/gnvitop) by Linwei94 (MIT). The SSH config parsing, the MetaX and TPU probes and the Gadi node discovery still come from that code. The terminal interface, the monitor and the tests are new. The first commit imports gnvitop 0.5.0 as it was; its earlier history is in that repository.

The layout follows nvtop's look. No code was taken from nvtop, which is GPL-3.0.

MIT, see [LICENSE](LICENSE).
