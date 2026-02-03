

# 🏠 HomeLab Checkup Tool

HomeLab Checkup Tool is a terminal-based Python application for monitoring the status of devices in your home lab network. It provides a simple, interactive menu interface to check which devices are online or offline using ICMP ping, making it easy to keep track of your network health.


## ✨ Features


- **🖧 Network Device Status Scanning**
   - 📡 Pings a customizable list of devices (IP addresses or hostnames) and displays their online/offline status in real time.
   - Uses color-coded output for quick recognition: green for online, red for offline.
   - Aligns device names, IPs, and status for clear readability.

- **🖥️ Interactive Terminal Menu**
   - Navigate options using the arrow keys and select with Enter.
   - Menu options include running a network checkup, viewing information about the tool, and exiting.

- **ℹ️ About Section**
   - Displays information about the tool and its intended use for home lab owners.


## ⚙️ How It Works

1. The tool presents a menu in your terminal window.
2. Selecting "Network Checkup Tool" will ping each device in the configured list and display their status.
3. The results are shown in a formatted table, with online/offline status clearly indicated.
4. You can return to the menu or exit at any time.


## 🛠️ Requirements

- Python 3.11.6 or newer
- 🐧 Linux, macOS, or Windows (tested on Linux)
- `ping` command available in your system's PATH


## 🚀 Installation

1. 📥 **Clone the repository:**
   ```bash
   git clone https://github.com/NejcZorko007/HomeLabCheckupTool.git
   cd HomeLabCheckupTool
   ```

2. 📦 **Install required Python packages:**
   - On Linux/macOS, the `curses` module is included with Python.
   - On Windows, install `windows-curses`:
     ```bash
     pip install windows-curses
     ```

3. 📝 **Configure your devices:**
   - Open `main.py` in a text editor.
   - Edit the `DEVICES` list at the top of the file to include the names and IP addresses of your home lab devices.

4. ▶️ **Run the tool:**
   ```bash
   python3 main.py
   ```


## 🧑‍💻 Usage

- ⬆️⬇️ Use the **arrow keys** to move between menu options.
- ⏎ Press **Enter** to select an option.
- When running the network checkup, the tool will display each device's status in real time.
- After the scan, press any key to return to the main menu.


## 🛠️ Customization

- **Add or Remove Devices:**
   - Edit the `DEVICES` list in `main.py` to match your network setup. Each entry is a tuple: (`Device Name`, `IP Address`).

- ⏱️ **Change Ping Behavior:**
   - The script uses a 1-second timeout for each ping. You can adjust this in the `ping_device` function if needed.

- 🧩 **Extend Functionality:**
   - The code is modular and can be extended to include additional network checks, logging, or notifications.
   - Contributions and feature requests are welcome via the [GitHub Issues page](https://github.com/NejcZorko007/HomeLabCheckupTool/issues).


## 🐞 Troubleshooting

- If you see errors related to `curses` on Windows, ensure you have installed `windows-curses`.
- Make sure the `ping` command is available in your system's PATH.
- Run the script in a terminal that supports ANSI colors for best results.


## 📄 License

Apache-2.0 Licence
