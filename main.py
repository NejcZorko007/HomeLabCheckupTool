import curses
import subprocess
import platform
import time

# --- Configuration: Add your home lab IPs here ---
DEVICES = [
    ("OpenWebRX HOST", "192.168.1.95"),
    ("Laptop Node", "192.168.1.63"),
    ("NAS Storage", "192.168.1.76"),
    ("External Gateway", "8.8.8.8")
]

def ping_device(ip):
    """Pings a device and returns True if online, False otherwise."""
    # -c 1 (1 packet), -W 1 (1 second timeout)
    # Use -n 1 for Windows, -c 1 for Linux/Mac
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
    
    command = ['ping', param, '1', timeout_param, '1', ip]
    return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def run_network_checkup(stdscr):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    
    stdscr.addstr(2, 5, "--- HomeLab Network Mapping ---", curses.A_BOLD)
    stdscr.addstr(3, 5, "Initializing Ping Function...", curses.A_DIM)
    stdscr.refresh()
    time.sleep(3)

    for idx, (name, ip) in enumerate(DEVICES):
        y = 5 + idx
        stdscr.addstr(y, 5, f"{name} ({ip})")
        
        # Calculate dots for alignment
        # We want the [Status] to be at column 40
        current_len = len(name) + len(ip) + 8
        dots = "." * (40 - current_len)
        stdscr.addstr(y, 5 + current_len, dots)
        
        stdscr.refresh()
        
        # Perform Ping
        is_online = ping_device(ip)
        
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
    
    menu = ["Network Checkup Tool", "About", "Exit"]
    selected_row = 0

    while True:
        stdscr.clear()
        stdscr.addstr(1, 70, "HomeLab Checkup Tool")
        stdscr.addstr(9, 53, "https://www.github.com/NejcZorko007/HomeLabCheckupTool")
        
        
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
                about(stdscr)
            else:
                break

if __name__ == "__main__":
    curses.wrapper(main)
