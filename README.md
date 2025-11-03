# SSM - Sour CLI Sys Monitor Version: Aphrodite

A beginner-friendly terminal-based system monitor for Ubuntu/Linux.

---

## Features

- CPU, memory, and disk usage with color-coded bars
- Network speed (auto-scaled in KB/MB/GB per second)
- Top 10 processes by CPU usage
- Hostname and system uptime display
- Refreshes every second
- Clean, beginner-friendly interface

---

## Installation

1. **Clone the repository:**
git clone https://github.com/<your-username>/SSM.git

2. **Install Python dependencies:**
pip install -r /SSM/requirements.txt

3. **Install SSM globally** (requires sudo):
bash /SSM/install.sh
This will copy the launcher to /usr/local/bin, so you can run `ssm` from anywhere.

---

## Usage

After installation, simply run:

ssm

Press Ctrl+C to exit.

---

## Development

- The main Python code is in ssm_pkg/main.py.
- The launcher script is ssm.
- Use install.sh to set up the launcher globally.

---

## Notes

- Requires Python 3 and the packages psutil and rich.
- Tested on Ubuntu/Linux environments.
- Works on systems without temperature sensors.

---
