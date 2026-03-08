#Copyright 2026 Zorko Industries ©

#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.

import curses
import subprocess
import platform
import time
import socket
import datetime

# --- Configuration: Add your home lab IPs here ---
DEVICES = [
    ("host 1", "192.168.1.95"),
    ("host 2", "192.168.1.63"),
    ("host 3", "192.168.1.76"),
    ("External Gateway", "8.8.8.8")
]

# Stores the latest network scan results for report export.
LAST_SCAN_RESULTS = []


def prompt_input(stdscr, prompt_text):
    """Prompt for single-line input in curses and return stripped text."""
    stdscr.clear()
    curses.echo()
    curses.curs_set(1)
    stdscr.addstr(2, 5, prompt_text, curses.A_BOLD)
    stdscr.addstr(4, 5, "> ")
    stdscr.refresh()
    value = stdscr.getstr(4, 7, 120).decode("utf-8", errors="ignore").strip()
    curses.noecho()
    curses.curs_set(0)
    return value


def show_result(stdscr, title, lines):
    """Render a simple result screen and wait for a key press."""
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    max_text_width = max(10, w - 8)
    stdscr.addstr(2, 5, title[:max_text_width], curses.A_BOLD)

    max_lines = max(1, h - 8)
    for idx, line in enumerate(lines[:max_lines]):
        stdscr.addstr(4 + idx, 5, str(line)[:max_text_width])

    if len(lines) > max_lines:
        stdscr.addstr(4 + max_lines, 5, "... output truncated ..."[:max_text_width], curses.A_DIM)

    stdscr.addstr(h - 3, 5, "PRESS ANY KEY TO RETURN."[:max_text_width])
    stdscr.refresh()
    stdscr.getch()


def run_device_scan():
    """Return scan results as a list of dicts for UI and report export."""
    results = []
    for name, ip in DEVICES:
        is_online = ping_device(ip)
        results.append(
            {
                "name": name,
                "ip": ip,
                "online": is_online,
                "status": "ONLINE" if is_online else "OFFLINE",
            }
        )
    return results

def ping_device(ip):
    """Pings a device and returns True if online, False otherwise."""
    # -c 1 (1 packet), -W 1 (1 second timeout)
    # Use -n 1 for Windows, -c 1 for Linux/Mac
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
    
    command = ['ping', param, '1', timeout_param, '1', ip]
    return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def quick_ping_tool(stdscr):
    target = prompt_input(stdscr, "Quick Ping: Enter hostname or IP")
    if not target:
        show_result(stdscr, "Quick Ping", ["No target entered."])
        return

    is_online = ping_device(target)
    status = "ONLINE" if is_online else "OFFLINE"
    show_result(stdscr, "Quick Ping Result", [f"Target: {target}", f"Status: {status}"])


def port_check_tool(stdscr):
    host = prompt_input(stdscr, "Port Check: Enter hostname or IP")
    if not host:
        show_result(stdscr, "Port Check", ["No host entered."])
        return

    port_text = prompt_input(stdscr, "Port Check: Enter TCP port (1-65535)")
    try:
        port = int(port_text)
        if port < 1 or port > 65535:
            raise ValueError
    except ValueError:
        show_result(stdscr, "Port Check", [f"Invalid port: {port_text or '(empty)'}"])
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.5)
    try:
        result = sock.connect_ex((host, port))
        is_open = result == 0
    except socket.gaierror:
        show_result(stdscr, "Port Check Result", [f"Host: {host}", "Could not resolve host name."])
        return
    except OSError as exc:
        show_result(stdscr, "Port Check Result", [f"Host: {host}", f"Socket error: {exc}"])
        return
    finally:
        sock.close()

    state = "OPEN" if is_open else "CLOSED/FILTERED"
    show_result(stdscr, "Port Check Result", [f"Host: {host}", f"Port: {port}", f"State: {state}"])


def dns_lookup_tool(stdscr):
    hostname = prompt_input(stdscr, "DNS Lookup: Enter hostname")
    if not hostname:
        show_result(stdscr, "DNS Lookup", ["No hostname entered."])
        return

    try:
        _, _, ip_list = socket.gethostbyname_ex(hostname)
    except socket.gaierror:
        show_result(stdscr, "DNS Lookup Result", [f"Hostname: {hostname}", "Lookup failed."])
        return

    lines = [f"Hostname: {hostname}"]
    if ip_list:
        lines.append("Resolved IPs:")
        lines.extend([f"- {ip}" for ip in ip_list])
    else:
        lines.append("No IP addresses returned.")
    show_result(stdscr, "DNS Lookup Result", lines)


def traceroute_tool(stdscr):
    target = prompt_input(stdscr, "Traceroute: Enter hostname or IP")
    if not target:
        show_result(stdscr, "Traceroute", ["No target entered."])
        return

    is_windows = platform.system().lower() == "windows"
    command = ["tracert", "-d", target] if is_windows else ["traceroute", "-n", target]

    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        missing = "tracert" if is_windows else "traceroute"
        show_result(stdscr, "Traceroute Result", [f"Missing command: {missing}"])
        return
    except subprocess.TimeoutExpired:
        show_result(stdscr, "Traceroute Result", [f"Target: {target}", "Traceroute timed out."])
        return

    output = proc.stdout.strip() or proc.stderr.strip()
    lines = [f"Target: {target}", "First hops:"]
    if output:
        output_lines = output.splitlines()
        lines.extend(output_lines[:10])
        if len(output_lines) > 10:
            lines.append("... output truncated ...")
    else:
        lines.append("No output returned.")

    show_result(stdscr, "Traceroute Result", lines)


def local_network_info_tool(stdscr):
    hostname = socket.gethostname()
    fqdn = socket.getfqdn()
    os_name = platform.system()
    os_version = platform.release()

    try:
        local_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        local_ip = "Unavailable"

    lines = [
        f"Hostname: {hostname}",
        f"FQDN: {fqdn}",
        f"Local IP: {local_ip}",
        f"OS: {os_name} {os_version}",
        f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    show_result(stdscr, "Local Network Info", lines)


def save_scan_report_tool(stdscr):
    if not LAST_SCAN_RESULTS:
        show_result(
            stdscr,
            "Save Scan Report",
            ["No scan data found.", "Run 'Network Checkup Tool' first."],
        )
        return

    file_name = prompt_input(stdscr, "Save Report: Enter file name (default: scan_report.txt)")
    if not file_name:
        file_name = "scan_report.txt"

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "HomeLab Checkup Scan Report",
        f"Generated: {timestamp}",
        "",
    ]

    online_count = sum(1 for item in LAST_SCAN_RESULTS if item["online"])
    lines.append(f"Summary: {online_count}/{len(LAST_SCAN_RESULTS)} devices online")
    lines.append("")

    for item in LAST_SCAN_RESULTS:
        lines.append(f"{item['name']} ({item['ip']}): {item['status']}")

    try:
        with open(file_name, "w", encoding="utf-8") as report_file:
            report_file.write("\n".join(lines) + "\n")
    except OSError as exc:
        show_result(stdscr, "Save Scan Report", [f"Failed to save report: {exc}"])
        return

    show_result(stdscr, "Save Scan Report", [f"Report saved to: {file_name}"])

def run_network_checkup(stdscr):
    global LAST_SCAN_RESULTS

    stdscr.clear()
    h, w = stdscr.getmaxyx()
    
    stdscr.addstr(2, 5, "--- HomeLab Network Mapping ---", curses.A_BOLD)
    stdscr.addstr(3, 5, "Initializing Ping Function...", curses.A_DIM)
    stdscr.refresh()
    time.sleep(3)

    LAST_SCAN_RESULTS = run_device_scan()

    for idx, result in enumerate(LAST_SCAN_RESULTS):
        name = result["name"]
        ip = result["ip"]
        y = 5 + idx
        stdscr.addstr(y, 5, f"{name} ({ip})")
        
        # Calculate dots for alignment
        # We want the [Status] to be at column 40
        current_len = len(name) + len(ip) + 8
        dots = "." * max(1, (40 - current_len))
        stdscr.addstr(y, 5 + current_len, dots)
        
        stdscr.refresh()
        is_online = result["online"]
        
        if is_online:
            stdscr.attron(curses.A_BOLD)
            stdscr.addstr("[ONLINE]", curses.color_pair(1)) # Green
            stdscr.attroff(curses.A_BOLD)
        else:
            stdscr.addstr("[OFFLINE]")

    stdscr.addstr(h - 3, 5, "SCAN COMPLETE. PRESS ANY KEY TO RETURN.")
    stdscr.refresh()
    stdscr.getch()

def about(stdscr):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    stdscr.addstr(2, 5, "---- HomeLab Network ----", curses.A_BOLD)
    stdscr.addstr(3, 5, "About tool", curses.A_DIM)
    stdscr.addstr(5, 5, "HomeLab Checkup Tool created by NejcZorko007 is a tool designed for big or small HomeLab owners.", curses.A_BOLD)
    stdscr.addstr(6, 5, "For functions you would like to add, please create a ticket on our github page.", curses.A_BOLD)
    stdscr.addstr(7, 5, "Thanks for supporting the Project.", curses.A_BOLD)

    stdscr.addstr(h - 3, 5, " PRESS ANY KEY TO RETURN.")
    stdscr.refresh()
    stdscr.getch()


# --- Main Terminal Logic (Simplified for integration) ---
def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    stdscr.attron(curses.color_pair(1))
    
    menu = [
        "Network Checkup Tool",
        "Quick Ping",
        "Port Check",
        "DNS Lookup",
        "Traceroute",
        "Local Network Info",
        "Save Last Scan Report",
        "About",
        "Exit",
    ]
    selected_row = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        title = "HomeLab Checkup Tool"
        link = "https://www.github.com/NejcZorko007/HomeLabCheckupTool"
        stdscr.addstr(1, max(1, w - len(title) - 2), title)
        stdscr.addstr(min(h - 2, 14), max(1, w - len(link) - 2), link)
        
        
        for idx, item in enumerate(menu):
            if idx == selected_row:
                stdscr.addstr(4 + idx, 5, f"> {item}", curses.A_REVERSE)
            else:
                stdscr.addstr(4 + idx, 5, f"  {item}")
        
        key = stdscr.getch()
        if key == curses.KEY_UP and selected_row > 0:
            selected_row -= 1
        elif key == curses.KEY_DOWN and selected_row < len(menu) - 1:
            selected_row += 1
        elif key in [10, 13]:
            if selected_row == 0:
                run_network_checkup(stdscr)
            elif selected_row == 1:
                quick_ping_tool(stdscr)
            elif selected_row == 2:
                port_check_tool(stdscr)
            elif selected_row == 3:
                dns_lookup_tool(stdscr)
            elif selected_row == 4:
                traceroute_tool(stdscr)
            elif selected_row == 5:
                local_network_info_tool(stdscr)
            elif selected_row == 6:
                save_scan_report_tool(stdscr)
            elif selected_row == 7:
                about(stdscr)
            else:
                break

if __name__ == "__main__":
    curses.wrapper(main)
