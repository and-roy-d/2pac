# 2PAC ADR Control & Telemetry System

A modern, high-reliability Python / PyQt5 application for automated cryogenic procedures, real-time telemetry logging, and interactive monitoring of the **2PAC Two-Stage Adiabatic Demagnetization Refrigerator (ADR)**.

Built on **QCoDeS**, **PyQt5**, and **Matplotlib**, 2PAC provides automated hardware sequencing, dual-layer persistent data logging, an intuitive **Simple Mode** for day-to-day operations, and an **Expert Mode** for custom scripting and state machine inspection.

---

## Quick Start (daily use)

- **Launch:** click the *2pac gui* icon, or run `scripts/run_supervised.sh`. It also starts automatically at login.
  Only one GUI can run at a time; a second launch just tells you the first one is open.
- **Crashes:** the supervisor restarts the GUI after 10 s (normal window close = stop). After a restart a running
  regulation loop is re-adopted automatically; an interrupted cycle or ramp is **not** resumed (a banner says what
  was running). GUI output: `~/2pac_logs/gui_stdout/`.
- **Operating:** see [`docs/OPERATOR_RUNBOOK.md`](docs/OPERATOR_RUNBOOK.md) (banners, regulation, relay, restarts).
- **Before a magnet cycle:** Kepco ON with its current limit above 9.5 A, green He-3 valve closed.
- **Changing code:** run `scripts/install_git_hooks.sh` once; `git push` then runs `tests/test_state_machine.py`.
  Don't restart the GUI while a ramp is advancing.

---

## Table of Contents

1. [Key Features](#key-features)
2. [Hardware Architecture](#hardware-architecture)
3. [Installation & Setup](#installation--setup)
   - [System Prerequisites](#1-system-prerequisites)
   - [Hardware Permissions & udev Rules](#2-hardware-permissions--udev-rules)
   - [Software Installation](#3-software-installation)
   - [Desktop Launcher Setup](#4-desktop-launcher-setup)
4. [User Guide & Operations](#user-guide--operations)
   - [Simple Mode (Default)](#simple-mode-default)
   - [Standard Cryogenic Run Workflow](#standard-cryogenic-run-workflow)
   - [Expert Mode & Scripting](#expert-mode--scripting)
   - [Interactive Plot Controls](#interactive-plot-controls)
   - [Utils & Diagnostics Tab](#utils--diagnostics-tab)
5. [Data Logging & Storage](#data-logging--storage)
6. [Repository Structure](#repository-structure)
7. [Troubleshooting & FAQ](#troubleshooting--faq)

---

## Key Features

- **Dual-Mode Operation**:
  - **Simple Mode**: One-click selection of automated procedures with clean plain-text naming (`Idle`, `Ready for Cooldown`, `He-3 / ADR Cycle`, `Warm Up 300K`), high-visibility operator action banners, and automatic safe transition to `Idle` on sequence completion.
  - **Expert Mode**: Full state machine code inspection, live line execution highlighting, pseudocode compiler, and desktop custom script runner.
- **High-Performance Plotting**:
  - Sub-millisecond viewport slicing (`np.searchsorted`) eliminates render lag (< 35 ms) even with multi-million-point databases.
  - Adaptive tick locators (`SmartTimeLocator`) maintain 5–7 clean, readable time ticks at any zoom level ($0.05$ s up to 50 years) without crashes.
  - Interactive box zoom, mouse-wheel axis zoom, click-drag pan, and hover crosshair readouts across all subplots.
- **Dual Persistence Architecture**:
  - Structured **QCoDeS SQLite** database (`~/2pac_logs/YYYY-MM-DD/2pac.db`).
  - Human-readable daily flat log files (`~/2pac_logs/YYYY-MM-DD/<channel>.log`).
- **Robust Hardware Sequencing**:
  - Automated open-loop and closed-loop Lake Shore heater ramping, sorption pump temperature cycling, pneumatic heat switch actuations, and magnet relay transitions.
  - Automatic fallback to closed-loop temperature control upon demagnetization completion.

---

## Hardware Architecture

The 2PAC ADR is controlled through three primary instrument interfaces managed via `station_2pac.py`:

```
               +-------------------------------------------------+
               |              2PAC GUI (PyQt5 / QCoDeS)          |
               +-----------------------+-------------------------+
                                       |
        +------------------------------+-------------------------------+
        |                              |                               |
        v                              v                               v
+------------------+         +--------------------+         +--------------------+
|  LabJack U3-HV   |         |  Cryo-con Model 24C|         | Lake Shore Model370|
|      (USB)       |         | (/dev/ttyUSB0 Serial)|        |(/dev/ttyUSB1 Serial)|
+------------------+         +--------------------+         +--------------------+
  | AI0: Magnet V              | Ch A: 60K Flange             | Ch 1: FAA Thermometer
  | AI1: Magnet I              | Ch B: Charcoal Sorption      | Heater: Magnet Ramp
  | AI2: He3 Pressure          | Ch C: 4K Flange              |         Controller
  | FIO4: HS ADR               | Ch D: Pot                    |
  | FIO5: HS Charcoal          | Loop 1: Sorption Heater      |
  | FIO6: HS Pot               | Loop 2: Stage Heater         |
  | EIO0: Magnet Relay         +--------------------+         +--------------------+
+------------------+
```

---

## Installation & Setup

### 1. System Prerequisites

- **Operating System**: Linux (Ubuntu 20.04+, Debian 11+, Fedora 36+, or similar X11/Wayland desktop)
- **Python**: Version 3.10, 3.11, or 3.12
- **Hardware Ports**: 3 available USB ports (LabJack U3, Cryo-con serial adapter, Lake Shore serial adapter)

### 2. Hardware Permissions & udev Rules

#### A. Serial Port Access (`dialout` group)
Ensure your Linux user has permission to read and write to USB serial ports (`/dev/ttyUSB*`):
```bash
sudo usermod -a -G dialout $USER
```
*(Log out and log back in for group changes to take effect).*

#### B. LabJack U3 udev Rules
To allow non-root users to claim the LabJack USB interface, install the LabJack udev rule:
```bash
sudo tee /etc/udev/rules.d/10-labjack.rules << 'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="0cd5", MODE="0666", GROUP="dialout"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

---

### 3. Software Installation

Clone the repository to your preferred location:
```bash
git clone https://github.com/ggggggggg/2pac.git
cd 2pac
```

Choose **Option A** (recommended: ultrafast with `uv`) or **Option B** (standard `pip`):

#### Option A: Using `uv` (Recommended)
```bash
# If uv is not installed: curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv --python 3.10
uv pip install -r requirements.txt
```

#### Option B: Using standard Python `venv` & `pip`
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 4. Desktop Launcher Setup

```bash
scripts/install_desktop_icon.sh            # add --no-autostart to skip starting at login
```

Installs the menu entry (`~/.local/share/applications/2pac_gui.desktop`), a desktop shortcut and a login
autostart entry (`~/.config/autostart/2pac_gui.desktop`). All of them run `scripts/run_supervised.sh`, which
restarts the GUI after a crash or a telemetry-watchdog exit and stops on a normal close.

You can now launch the application by clicking the icon on your desktop or application dock.

---

## User Guide & Operations

### Simple Mode (Default)

When launched, the application opens in **Simple Mode**. This presents a streamlined, professional interface designed for routine cryogenic cooling cycles without exposing underlying code or script windows.

- **Procedure Selector**: Plain-text dropdown for high-level operations:
  - **Idle**: System is paused or holding steady; background telemetry continues logging.
  - **Ready for Cooldown**: Prepares all heat switches and temperature controllers for pre-cooling from room temperature.
  - **He-3 / ADR Cycle**: Fully automated condensation and demagnetization sequence.
  - **Warm Up 300K**: Safely closes heat switches and sets Cryo-con loops to 295 K for warming the cryostat back to room temperature.
- **Controls**:
  - **Start**: Initiates the selected procedure.
  - **Pause**: Halts state advancement while holding current hardware setpoints and logging telemetry.
  - **Stop**: Immediately aborts the active sequence and returns the system safely to **Idle**.
- **Action Banners**: If a procedure requires manual operator intervention (e.g., closing the He-3 green valve), a prominent yellow notification banner appears at the top of the window.

---

### Standard Cryogenic Run Workflow

```
       [Room Temp]
            │
            ▼
┌─────────────────────────┐
│   Ready for Cooldown    │  Closes Pot, ADR, and Charcoal heat switches.
└───────────┬─────────────┘  Action Banner: "OPEN THE GREEN HE3 VALVE"
            │ (Cooldown to 4K via liquid helium / pulse tube)
            ▼
┌─────────────────────────┐  Charcoal heats to 65 K / 55 K.
│    He-3 / ADR Cycle     │  ADR ramps up (0 -> 58.1% hout, 1800 s).
└───────────┬─────────────┘  Action Banner: "CLOSE THE GREEN HE3 VALVE"
            │                He-3 condenses (3.5 hour dwell).
            │                Charcoal cools to condense remaining gas.
            │                ADR ramps down (58.1% -> 0 hout, 1800 s).
            │                Relay switches to CONTROL; closed-loop PID engaged.
            ▼
┌─────────────────────────┐
│          Idle           │  Sub-Kelvin base temperature reached (< 100 mK).
└───────────┬─────────────┘  PID control holds FAA stage temperature.
            │ (Run physics experiment)
            ▼
┌─────────────────────────┐
│      Warm Up 300K       │  Closes heat switches; sets heaters to 295 K.
└─────────────────────────┘
```

---

### Expert Mode & Scripting

Toggle the **Mode** button to switch to **Expert Mode**. Expert mode reveals:
1. **Script Code Viewer**: Displays the active procedure source code with line-by-line yellow execution tracking.
2. **Custom Script Runner**: Automatically scans `~/Desktop/custom_scripts/` for custom `.txt` scripts and adds them to the procedure selector.

#### Writing Custom Scripts (Pseudocode or Python)
Create any `.txt` file in `~/Desktop/custom_scripts/` using simple pseudocode:

```text
# Example: Custom He-3 Quick Cycle
close heatswitch pot
close heatswitch adr
open heatswitch charcoal
wait 5 s

set relay RAMP
wait 10 s

print "Starting manual ramp"
set relay CONTROL
return wait_forever
```

Supported pseudocode commands:
- `open heatswitch <pot|adr|charcoal>` or `close heatswitch <pot|adr|charcoal>`
- `set relay <RAMP|CONTROL>`
- `wait <number> [s|min|hours]`
- `print "message"`
- `return <target_state>`
- Any standard Python expression (`world.station.cryocon...`, `for`, `while`, `if`).

---

### Interactive Plot Controls

- **Left-Click + Drag**: Box-zoom into any specific time or temperature window.
- **Mouse Scroll on Axis**:
  - Scroll over the **X-axis** to zoom in/out in time centered on the cursor.
  - Scroll over the **Y-axis** to zoom in/out in temperature or pressure.
- **Right-Click Drag**: Pan viewport across the timeline.
- **Reset Zoom**: Instantly restores the full view for the active time window.
- **Time Range Selector**: Quickly switch between `1 Hour`, `6 Hours`, `1 Day`, `1 Week`, or `1 Month`.
- **Theme Toggle**: Switch between clean **Light Mode** and high-contrast **Dark Mode**.

---

### Utils & Diagnostics Tab

Located in the top tab bar:
- **Telemetry Logging Interval**: Set telemetry polling rate (default: `1.0 s`).
- **Plot Refresh Cadence**: Adjust plot redraw frequency (default: `1.0 s`).
- **Hardware Diagnostics**: View live subplots for:
  - Kepco Magnet Voltage
  - Lake Shore 370 Heater Output
  - Heat Switch (`ADR`, `Charcoal`, `Pot`) and Relay (`RAMP` / `CONTROL`) discrete states.

---

## Data Logging & Storage

Telemetry is automatically saved every second to daily timestamped folders located at:
```
~/2pac_logs/YYYY-MM-DD/
```

### 1. SQLite Database (`2pac.db`)
Full QCoDeS dataset containing all synchronized channels with elapsed time setpoints:
- `cryocon_chA_temperature` (60K flange)
- `cryocon_chB_temperature` (Charcoal)
- `cryocon_chC_temperature` (4K flange)
- `cryocon_chD_temperature` (Pot)
- `faa_temperature` (Lake Shore FAA stage)
- `labjack_he3_pressure` (He-3 line bar)
- `labjack_kepco_current` / `labjack_kepco_voltage`
- `ls370_heater_out`
- `labjack_relay`, `labjack_heatswitch_*`
- `state` (active state machine procedure name)

### 2. Flat Log Files
Human-readable text logs appended in real time:
- `cryocon_chA_temperature.log`
- `faa_temperature.log`
- `labjack_he3_pressure.log`
- *(etc.)*

Each line contains: `<epoch_timestamp> <value>\n`.

---

## Repository Structure

```
2pac/
├── main.py                     # Entry point: single-instance lock, hardware init, window
├── gui.py                      # Main window (MyApp) and layout
├── gui_common.py               # Shared imports, constants, settings helpers
├── gui_status.py               # Banners, alerts, watchdog, status tiles, restart handling
├── gui_utils_tab.py            # Utils tab: LS370 PID/heater settings, wiring R
├── gui_hardware.py             # Heat switch and relay controls
├── gui_ipc.py                  # Private command channel (~/.2pac/ipc)
├── gui_plot_interaction.py     # Mouse zoom / pan / cursor
├── plot_utils.py               # Matplotlib plotting, locators, formatters
├── daily_logger.py             # SQLite daily telemetry logger, preloader, and cache
├── states.py                   # Procedures (state machine) and safety checks
├── alerts.py                   # Optional remote alerts (webhook / ntfy)
├── pid_autotuner.py            # PID trial runner (uses the command channel)
├── launch_gui.sh               # Runs main.py with the project venv
│
├── engine/                     # State machine engine
├── instruments/                # LS370, Cryo-con 24C, LabJack U3 drivers + station
├── custom_scripts/             # Plain-text procedure templates (magnet/relay scripts are refused)
├── assets/                     # Icon and .desktop entry
├── scripts/
│   ├── run_supervised.sh       # Restart-on-crash launcher (used by all launchers)
│   ├── install_desktop_icon.sh # Menu, desktop and login-autostart entries
│   └── install_git_hooks.sh    # pre-push hook running the tests
├── tests/test_state_machine.py # Fake-instrument tests of the procedures
└── docs/                       # Runbook, fix list, architecture, Kepco/PID notes, history
```

---

## Troubleshooting & FAQ

### 1. LabJack Permission Error (`Could not claim interface`)
**Symptom**: `LabJackPython.LabJackException: Could not claim interface on LabJack.`  
**Cause**: Missing udev rules or another running process holds the device.  
**Fix**:
1. Check if another instance of `main.py` is running: `pkill -f "python.*main.py"`.
2. Ensure udev rules are installed as described in [Hardware Permissions](#2-hardware-permissions--udev-rules).

### 2. Serial Port Error (`Permission denied: '/dev/ttyUSB0'`)
**Symptom**: `PermissionError: [Errno 13] Permission denied: '/dev/ttyUSB0'`.  
**Fix**: Add your user to the `dialout` group:
```bash
sudo usermod -a -G dialout $USER
```
Then log out and back in.

### 3. USB Serial Port Swap (`/dev/ttyUSB0` vs `/dev/ttyUSB1`)
**Symptom**: Cryo-con or Lake Shore fails to connect on startup.  
**Fix**: If USB cables were unplugged and reconnected in a different order, check port assignments:
```bash
ls -l /dev/ttyUSB*
```
Update port names in `station_2pac.py` if necessary:
- `LakeshoreModel370("ls370", "ASRL/dev/ttyUSB1::INSTR")`
- `Cryocon24C("cryocon", "ASRL/dev/ttyUSB0::INSTR")`

### 4. Window Launches Behind Other Applications
**Fix**: The application uses EWMH `_NET_ACTIVE_WINDOW` signaling and `StartupNotify=true` to ensure the window gains foreground focus immediately upon launch.

---

## License

Proprietary / Internal Research Laboratory Software — NIST / Quantum Sensors Project.
