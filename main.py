# Copyright 2026 Zorko Enterprise Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""HomeLab Checkup Tool - check which home lab devices and services are up."""

import argparse
import curses
import datetime
import ipaddress
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

__version__ = "2.0.0"

REPO_URL = "https://github.com/NejcZorko007/HomeLabCheckupTool"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "devices.json")
EXAMPLE_CONFIG = os.path.join(SCRIPT_DIR, "devices.example.json")

PING_TIMEOUT_S = 1
PORT_TIMEOUT_S = 1.5
MAX_WORKERS = 32

OS_NAME = platform.system().lower()
IS_WINDOWS = OS_NAME == "windows"
IS_MAC = OS_NAME == "darwin"

# Hostname: labels of letters, digits and hyphens, not starting or ending with a hyphen.
_HOST_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
# Matches "time=12.3 ms", "time<1ms", and localized forms like "cas=12ms".
_LATENCY_RE = re.compile(r"[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)

# Stores the latest network scan results for report export.
LAST_SCAN_RESULTS = []


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    pass


def is_valid_target(value):
    """True if value is an IP address or a valid hostname (never an option like '-f')."""
    if not value or len(value) > 253 or value.startswith("-"):
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    labels = value.rstrip(".").split(".")
    return all(_HOST_LABEL.match(label) for label in labels)


def load_devices(path):
    """Load and validate the device list from a JSON config file."""
    if not os.path.exists(path):
        raise ConfigError(
            f"Config file not found: {path}\n"
            f"Copy devices.example.json to devices.json and add your devices."
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}")

    entries = data.get("devices") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f'{path} must contain a non-empty "devices" list.')

    devices = []
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"Device #{i} must be an object.")
        name = str(entry.get("name", "")).strip()
        host = str(entry.get("host", "")).strip()
        port = entry.get("port")
        if not name:
            raise ConfigError(f'Device #{i} is missing "name".')
        if not is_valid_target(host):
            raise ConfigError(f'Device "{name}" has an invalid "host": {host!r}')
        if port is not None:
            if not isinstance(port, int) or not 1 <= port <= 65535:
                raise ConfigError(f'Device "{name}" has an invalid "port": {port!r}')
        devices.append({"name": name, "host": host, "port": port})
    return devices


# ---------------------------------------------------------------------------
# Network checks (no curses here, so they also work in --once mode)
# ---------------------------------------------------------------------------

def ping_device(host):
    """Ping a host once. Returns (online, latency_ms or None)."""
    if not is_valid_target(host):
        return False, None

    if IS_WINDOWS:
        # Windows: -n count, -w timeout in MILLISECONDS
        command = ["ping", "-n", "1", "-w", str(PING_TIMEOUT_S * 1000), host]
    elif IS_MAC:
        # macOS: -W timeout in MILLISECONDS
        command = ["ping", "-c", "1", "-W", str(PING_TIMEOUT_S * 1000), host]
    else:
        # Linux: -W timeout in SECONDS
        command = ["ping", "-c", "1", "-W", str(PING_TIMEOUT_S), host]

    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=PING_TIMEOUT_S + 3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, None
    elapsed_ms = (time.perf_counter() - started) * 1000

    online = proc.returncode == 0
    if IS_WINDOWS:
        # Windows ping returns 0 even for "Destination host unreachable" replies
        # sent by the router, so require a real echo reply (it contains TTL=).
        online = online and "ttl=" in proc.stdout.lower()
    if not online:
        return False, None

    match = _LATENCY_RE.search(proc.stdout)
    if match:
        return True, float(match.group(1).replace(",", "."))
    return True, round(elapsed_ms, 1)


def check_port(host, port, timeout=PORT_TIMEOUT_S):
    """Return (state, detail). state is 'open', 'closed' or 'error'. Works with IPv4 and IPv6."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "open", None
    except socket.gaierror:
        return "error", "Could not resolve host name."
    except (socket.timeout, ConnectionRefusedError):
        return "closed", None
    except OSError as exc:
        return "closed", str(exc)


def check_device(device):
    """Ping a device and, if it has a port, check that service too."""
    online, latency = ping_device(device["host"])
    port_state = None
    if device["port"]:
        port_state, _ = check_port(device["host"], device["port"])

    if device["port"]:
        # A device with a service port counts as up only if the service answers.
        up = port_state == "open"
    else:
        up = online

    if up:
        status = "ONLINE"
    elif online and port_state != "open":
        status = "SERVICE DOWN"
    else:
        status = "OFFLINE"

    return {
        "name": device["name"],
        "host": device["host"],
        "port": device["port"],
        "ping": online,
        "latency_ms": latency,
        "port_state": port_state,
        "online": up,
        "status": status,
    }


def scan_devices(devices, on_result=None):
    """Check all devices in parallel. Calls on_result(index, result) as each finishes."""
    results = [None] * len(devices)
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(devices))) as pool:
        futures = {pool.submit(check_device, d): i for i, d in enumerate(devices)}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            if on_result:
                on_result(i, results[i])
    return results


def get_local_ip():
    """Find the LAN IP used for outgoing traffic (no packets are actually sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "Unavailable"
    finally:
        sock.close()


def format_result_line(r):
    target = f"{r['host']}:{r['port']}" if r["port"] else r["host"]
    latency = f" {r['latency_ms']:.1f} ms" if r["latency_ms"] is not None else ""
    return f"{r['name']} ({target}): {r['status']}{latency}"


# ---------------------------------------------------------------------------
# Curses helpers
# ---------------------------------------------------------------------------

COLOR_GREEN = 1
COLOR_RED = 2
COLOR_YELLOW = 3


def safe_addstr(win, y, x, text, attr=0):
    """addstr that clips to the window instead of crashing on small terminals."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w - 1:
        return
    text = str(text)[: max(0, w - x - 1)]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def wait_for_key(stdscr, message="PRESS ANY KEY TO RETURN."):
    h, _ = stdscr.getmaxyx()
    safe_addstr(stdscr, h - 2, 5, message, curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def prompt_input(stdscr, prompt_text):
    """Prompt for single-line input in curses and return stripped text."""
    stdscr.clear()
    curses.echo()
    curses.curs_set(1)
    safe_addstr(stdscr, 2, 5, prompt_text, curses.A_BOLD)
    safe_addstr(stdscr, 4, 5, "> ")
    stdscr.refresh()
    try:
        value = stdscr.getstr(4, 7, 120).decode("utf-8", errors="ignore").strip()
    except curses.error:
        value = ""
    curses.noecho()
    curses.curs_set(0)
    return value


def prompt_target(stdscr, title, prompt_text):
    """Ask for a hostname/IP and validate it. Returns None if empty or invalid."""
    target = prompt_input(stdscr, prompt_text)
    if not target:
        show_result(stdscr, title, ["No target entered."])
        return None
    if not is_valid_target(target):
        show_result(stdscr, title, [f"Invalid hostname or IP: {target}"])
        return None
    return target


def show_result(stdscr, title, lines):
    """Render a simple result screen and wait for a key press."""
    stdscr.clear()
    h, _ = stdscr.getmaxyx()
    safe_addstr(stdscr, 2, 5, title, curses.A_BOLD)

    max_lines = max(1, h - 8)
    for idx, line in enumerate(lines[:max_lines]):
        safe_addstr(stdscr, 4 + idx, 5, line)
    if len(lines) > max_lines:
        safe_addstr(stdscr, 4 + max_lines, 5, "... output truncated ...", curses.A_DIM)

    wait_for_key(stdscr)


# ---------------------------------------------------------------------------
# Menu tools
# ---------------------------------------------------------------------------

def run_network_checkup(stdscr, devices):
    global LAST_SCAN_RESULTS

    stdscr.clear()
    h, w = stdscr.getmaxyx()
    safe_addstr(stdscr, 2, 5, "--- HomeLab Network Checkup ---", curses.A_BOLD)
    safe_addstr(stdscr, 3, 5, f"Checking {len(devices)} device(s)...", curses.A_DIM)

    first_row = 5
    visible = max(1, h - first_row - 4)
    labels = []
    for d in devices:
        target = f"{d['host']}:{d['port']}" if d["port"] else d["host"]
        labels.append(f"{d['name']} ({target})")
    status_col = 5 + min(max(len(l) for l in labels) + 3, max(10, w - 30))

    for idx, label in enumerate(labels[:visible]):
        safe_addstr(stdscr, first_row + idx, 5, label)
        safe_addstr(stdscr, first_row + idx, status_col, "[ ...... ]", curses.A_DIM)
    if len(devices) > visible:
        safe_addstr(stdscr, first_row + visible, 5,
                    f"... {len(devices) - visible} more not shown (enlarge the window or save a report)",
                    curses.A_DIM)
    stdscr.refresh()

    def draw(i, r):
        if i >= visible:
            return
        y = first_row + i
        safe_addstr(stdscr, y, status_col, " " * 30)
        if r["status"] == "ONLINE":
            attr = curses.color_pair(COLOR_GREEN) | curses.A_BOLD
        elif r["status"] == "SERVICE DOWN":
            attr = curses.color_pair(COLOR_YELLOW) | curses.A_BOLD
        else:
            attr = curses.color_pair(COLOR_RED) | curses.A_BOLD
        safe_addstr(stdscr, y, status_col, f"[{r['status']}]", attr)
        if r["latency_ms"] is not None:
            safe_addstr(stdscr, y, status_col + len(r["status"]) + 3,
                        f"{r['latency_ms']:.1f} ms", curses.A_DIM)
        stdscr.refresh()

    LAST_SCAN_RESULTS = scan_devices(devices, on_result=draw)

    online = sum(1 for r in LAST_SCAN_RESULTS if r["online"])
    safe_addstr(stdscr, h - 3, 5, f"SCAN COMPLETE: {online}/{len(LAST_SCAN_RESULTS)} up.", curses.A_BOLD)
    wait_for_key(stdscr)


def quick_ping_tool(stdscr):
    target = prompt_target(stdscr, "Quick Ping", "Quick Ping: Enter hostname or IP")
    if not target:
        return
    online, latency = ping_device(target)
    lines = [f"Target: {target}", f"Status: {'ONLINE' if online else 'OFFLINE'}"]
    if latency is not None:
        lines.append(f"Latency: {latency:.1f} ms")
    show_result(stdscr, "Quick Ping Result", lines)


def port_check_tool(stdscr):
    host = prompt_target(stdscr, "Port Check", "Port Check: Enter hostname or IP")
    if not host:
        return

    port_text = prompt_input(stdscr, "Port Check: Enter TCP port (1-65535)")
    try:
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        show_result(stdscr, "Port Check", [f"Invalid port: {port_text or '(empty)'}"])
        return

    state, detail = check_port(host, port)
    lines = [f"Host: {host}", f"Port: {port}"]
    if state == "error":
        lines.append(detail)
    else:
        lines.append(f"State: {'OPEN' if state == 'open' else 'CLOSED/FILTERED'}")
    show_result(stdscr, "Port Check Result", lines)


def dns_lookup_tool(stdscr):
    hostname = prompt_target(stdscr, "DNS Lookup", "DNS Lookup: Enter hostname")
    if not hostname:
        return
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        show_result(stdscr, "DNS Lookup Result", [f"Hostname: {hostname}", "Lookup failed."])
        return

    addresses = []
    for family, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        label = "IPv6" if family == socket.AF_INET6 else "IPv4"
        if (label, ip) not in addresses:
            addresses.append((label, ip))

    lines = [f"Hostname: {hostname}", "Resolved addresses:"]
    lines.extend(f"- [{label}] {ip}" for label, ip in addresses)
    show_result(stdscr, "DNS Lookup Result", lines)


def traceroute_tool(stdscr):
    target = prompt_target(stdscr, "Traceroute", "Traceroute: Enter hostname or IP")
    if not target:
        return

    command = ["tracert", "-d", target] if IS_WINDOWS else ["traceroute", "-n", target]
    stdscr.clear()
    safe_addstr(stdscr, 2, 5, f"Tracing route to {target} (up to 30 s)...", curses.A_DIM)
    stdscr.refresh()

    try:
        proc = subprocess.run(command, capture_output=True, text=True, errors="ignore", timeout=30)
    except FileNotFoundError:
        missing = "tracert" if IS_WINDOWS else "traceroute"
        show_result(stdscr, "Traceroute Result", [f"Missing command: {missing}"])
        return
    except subprocess.TimeoutExpired:
        show_result(stdscr, "Traceroute Result", [f"Target: {target}", "Traceroute timed out."])
        return

    output = proc.stdout.strip() or proc.stderr.strip()
    lines = [f"Target: {target}", ""]
    lines.extend(output.splitlines() if output else ["No output returned."])
    show_result(stdscr, "Traceroute Result", lines)


def local_network_info_tool(stdscr):
    lines = [
        f"Hostname: {socket.gethostname()}",
        f"FQDN: {socket.getfqdn()}",
        f"Local IP: {get_local_ip()}",
        f"OS: {platform.system()} {platform.release()}",
        f"Python: {platform.python_version()}",
        f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    show_result(stdscr, "Local Network Info", lines)


def build_report_lines(results):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    online = sum(1 for r in results if r["online"])
    lines = [
        "HomeLab Checkup Scan Report",
        f"Generated: {timestamp}",
        "",
        f"Summary: {online}/{len(results)} devices up",
        "",
    ]
    lines.extend(format_result_line(r) for r in results)
    return lines


def save_scan_report_tool(stdscr):
    if not LAST_SCAN_RESULTS:
        show_result(stdscr, "Save Scan Report",
                    ["No scan data found.", "Run 'Network Checkup' first."])
        return

    default_name = datetime.datetime.now().strftime("scan_report_%Y%m%d_%H%M%S.txt")
    file_name = prompt_input(stdscr, f"Save Report: Enter file name (default: {default_name})")
    file_name = file_name or default_name

    try:
        with open(file_name, "w", encoding="utf-8") as report_file:
            report_file.write("\n".join(build_report_lines(LAST_SCAN_RESULTS)) + "\n")
    except OSError as exc:
        show_result(stdscr, "Save Scan Report", [f"Failed to save report: {exc}"])
        return

    show_result(stdscr, "Save Scan Report", [f"Report saved to: {os.path.abspath(file_name)}"])


def about(stdscr, config_path):
    show_result(stdscr, f"HomeLab Checkup Tool v{__version__}", [
        "A small terminal tool for big or small HomeLab owners.",
        "",
        f"Config file: {config_path}",
        "",
        "Ideas or bugs? Open an issue on GitHub:",
        REPO_URL + "/issues",
    ])


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def tui_main(stdscr, devices, config_path):
    curses.curs_set(0)
    curses.start_color()
    try:
        curses.use_default_colors()
        background = -1
    except curses.error:
        background = curses.COLOR_BLACK
    curses.init_pair(COLOR_GREEN, curses.COLOR_GREEN, background)
    curses.init_pair(COLOR_RED, curses.COLOR_RED, background)
    curses.init_pair(COLOR_YELLOW, curses.COLOR_YELLOW, background)

    menu = [
        ("Network Checkup", lambda: run_network_checkup(stdscr, devices)),
        ("Quick Ping", lambda: quick_ping_tool(stdscr)),
        ("Port Check", lambda: port_check_tool(stdscr)),
        ("DNS Lookup", lambda: dns_lookup_tool(stdscr)),
        ("Traceroute", lambda: traceroute_tool(stdscr)),
        ("Local Network Info", lambda: local_network_info_tool(stdscr)),
        ("Save Last Scan Report", lambda: save_scan_report_tool(stdscr)),
        ("About", lambda: about(stdscr, config_path)),
        ("Exit", None),
    ]
    selected = 0

    while True:
        stdscr.clear()
        safe_addstr(stdscr, 1, 5, f"HomeLab Checkup Tool v{__version__}",
                    curses.color_pair(COLOR_GREEN) | curses.A_BOLD)
        safe_addstr(stdscr, 2, 5, f"{len(devices)} device(s) loaded", curses.A_DIM)

        for idx, (label, _) in enumerate(menu):
            text = f"{idx + 1}. {label}"
            if idx == selected:
                safe_addstr(stdscr, 4 + idx, 5, f"> {text}", curses.A_REVERSE)
            else:
                safe_addstr(stdscr, 4 + idx, 5, f"  {text}")

        safe_addstr(stdscr, 5 + len(menu), 5,
                    "Arrows/1-9 to choose, Enter to select, q to quit", curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):  # q or Esc
            break
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(menu)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(menu)
        elif ord("1") <= key <= ord(str(min(9, len(menu)))):
            selected = key - ord("1")
            key = 10  # select right away
        if key in (10, 13, curses.KEY_ENTER):
            action = menu[selected][1]
            if action is None:
                break
            action()


def run_once(devices, as_json):
    """Non-interactive scan for cron, scripts or n8n. Exit code 1 if anything is down."""
    results = scan_devices(devices)
    if as_json:
        print(json.dumps({
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "up": sum(1 for r in results if r["online"]),
            "total": len(results),
            "devices": results,
        }, indent=2))
    else:
        print("\n".join(build_report_lines(results)))
    return 0 if all(r["online"] for r in results) else 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Check which home lab devices and services are up.")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG,
                        help="path to devices JSON file (default: devices.json next to main.py)")
    parser.add_argument("--once", action="store_true",
                        help="scan once, print the results and exit (no menu)")
    parser.add_argument("--json", action="store_true",
                        help="with --once: print results as JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        devices = load_devices(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if args.once or args.json:
        return run_once(devices, args.json)

    try:
        curses.wrapper(tui_main, devices, os.path.abspath(args.config))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
