# 🏠 HomeLab Checkup Tool

A small terminal tool that shows which devices and services in your home lab are up. Checks run in parallel, so even a big list finishes in about a second. You get a simple arrow-key menu, or you can run it with no menu from cron and scripts.

<!-- TODO: add a screenshot or GIF of a scan here, e.g. docs/screenshot.png -->

## ✨ Features

- **🖧 Network Checkup:** pings every device in your list in parallel and shows each result as it arrives, with latency.
  - 🟢 `ONLINE` / 🔴 `OFFLINE`
  - 🟡 `SERVICE DOWN`: the device answers ping, but the service port you set (for example Proxmox on 8006) doesn't.
- **🧰 Quick tools:** Quick Ping, Port Check (IPv4 and IPv6), DNS Lookup, Traceroute, Local Network Info.
- **📝 Reports:** save the last scan to a text file.
- **🤖 Script mode:** `--once` prints the results and exits with code `1` if anything is down. Add `--json` for machine-readable output (cron, n8n, Home Assistant, shell scripts).
- **🖥️ Cross-platform:** Linux, macOS and Windows. Handles each OS's `ping` differences.

## 🛠️ Requirements

- Python 3.8 or newer
- The `ping` command (preinstalled on almost every system)
- `traceroute` (Linux/macOS) for the Traceroute tool. Optional.

## 🚀 Installation

```bash
git clone https://github.com/NejcZorko007/HomeLabCheckupTool.git
cd HomeLabCheckupTool
pip install -r requirements.txt   # only installs windows-curses on Windows
cp devices.example.json devices.json
```

On Windows use `copy` instead of `cp`.

## 📝 Configure your devices

Edit `devices.json`:

```json
{
  "devices": [
    { "name": "Router", "host": "192.168.1.1" },
    { "name": "Proxmox host", "host": "192.168.1.10", "port": 8006 },
    { "name": "Pi-hole", "host": "pihole.lan", "port": 80 }
  ]
}
```

| Field  | Required | Meaning |
|--------|----------|---------|
| `name` | yes | Label shown in the results |
| `host` | yes | IP address (IPv4/IPv6) or hostname |
| `port` | no  | TCP port of a service on that device. If set, the device only counts as up when this port answers. |

`devices.json` is in `.gitignore`, so `git pull` never overwrites your list.

## ▶️ Usage

Interactive menu:

```bash
python3 main.py
```

- ⬆️⬇️ arrow keys or number keys `1`–`9` to choose, **Enter** to select
- `q` or `Esc` to quit

Script mode:

```bash
python3 main.py --once                     # plain text report
python3 main.py --once --json              # JSON output
python3 main.py --config /path/to/lab.json # use a different device list
```

Exit codes: `0` everything up, `1` something down, `2` config error.

Example cron job that logs whenever something is down:

```cron
*/5 * * * * cd /opt/HomeLabCheckupTool && python3 main.py --once || python3 main.py --once >> down.log
```

## 🐞 Troubleshooting

- **Windows: `curses` error** → run `pip install -r requirements.txt`.
- **Everything shows OFFLINE** → check that `ping` works in your terminal. Some devices and firewalls block ping. For those, add a `port` so the service is checked instead.
- **Colors look wrong** → use a terminal with color support (Windows Terminal, any modern Linux/macOS terminal).

## 🤝 Contributing

Ideas and bug reports are welcome on the [Issues page](https://github.com/NejcZorko007/HomeLabCheckupTool/issues).

## 📄 License

Apache License 2.0. See [LICENSE](LICENSE).
