# 2PAC ADR System Architecture

## Overview
The **2PAC ADR** software is an automated control and telemetry logging system for an Adiabatic Demagnetization Refrigerator (ADR) cryostat. It coordinates sub-Kelvin thermal physics, multi-instrument serial/USB communication, live data visualization, and operator workflows.

```
                  ┌───────────────────────────────┐
                  │           PyQt5 GUI           │
                  │  (Simple & Expert Interface)  │
                  └───────────────┬───────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
  ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
  │  plot_utils   │       │ StationWorld  │       │ daily_logger  │
  │  (Matplotlib) │       │ (states/world)│       │ (SQLite & Mem)│
  └───────────────┘       └───────┬───────┘       └───────┬───────┘
                                  │                       │
                                  ▼                       │
                       ┌──────────────────────┐           │
                       │ QCoDeS Station       │           │
                       │ (instruments package)│           │
                       └──────────┬───────────┘           │
                                  │                       │
                 ┌────────────────┼────────────────┐      │
                 ▼                ▼                ▼      │
         ┌───────────────┐ ┌──────────────┐ ┌────────────┐│
         │ Cryo-con 24C  │ │ LakeShore 370│ │ LabJack U3 ││
         │  (VISA/RS232) │ │  (VISA/GPIB) │ │   (USB)    ││
         └───────────────┘ └──────────────┘ └────────────┘│
                 │                │                │      │
                 └────────────────┴────────────────┴──────┘
                                  │
                       Live Cryostat Hardware
```

---

## Directory Organization

```
2pac/
├── main.py                     # Application startup, splash screen, and initialization
├── gui.py                      # Modern PyQt5 graphical interface
├── plot_utils.py               # Matplotlib interactive plotting, locators, formatters
├── daily_logger.py             # SQLite daily telemetry logger, preloader, and cache
├── states.py                   # ADR state machine procedures and StationWorld safety
├── launch_gui.sh               # Root application launch script
│
├── engine/                     # State machine & procedure execution engine
│   ├── __init__.py             # Exports World, WaitUntil, state, State, loader functions
│   ├── world.py                # State machine execution engine & timing loop
│   ├── imperative_statemachine.py # Coroutine-based line-by-line state machine engine
│   └── custom_script_loader.py # Desktop pseudocode script compiler
│
├── instruments/                # Hardware instrument drivers and station setup
│   ├── __init__.py             # Exports get_station, LabjackU3, Cryocon24C, LakeshoreModel370
│   ├── station_2pac.py         # QCoDeS Station builder
│   ├── labjacku3.py            # LabJack U3 USB driver with thread-safe RLock
│   ├── cryocon24c.py           # Cryo-con 24C temperature controller VISA driver
│   ├── lakeshore370.py         # Lake Shore 370 AC resistance bridge driver
│   └── lakeshore370_base.py    # Lake Shore base instrument classes
│
├── custom_scripts/             # Plaintext procedure templates
│   ├── he3_adr_cycle.txt       # Full He-3 condensation + ADR demagnetization cycle
│   ├── he3_only_cycle.txt      # He-3 condensation cycle without magnet energization
│   ├── ready_for_cooldown.txt  # Pre-cooling configuration (all switches closed)
│   ├── warmup_300K.txt         # Controlled 300 K system warm-up procedure
│   └── ...                     # Utility switch & relay scripts
│
├── assets/                     # Graphical assets and desktop files
│   ├── adr_gui_icon.png        # Application desktop icon
│   └── 2pac_gui.desktop        # Linux XDG desktop entry
│
├── scripts/                    # Maintenance and installation scripts
│   ├── launch_gui.sh           # Shell launcher
│   └── install_desktop_icon.sh # Desktop shortcut installer
│
├── docs/                       # System documentation
│   ├── ARCHITECTURE.md         # Software architecture and subsystem breakdown
│   └── PROCEDURES.md           # Operational procedure guides and safety rules
│
```

---

## Subsystem Details

### 1. Telemetry & Database (`daily_logger.py`)
- **Storage**: Partitioned SQLite databases located at `~/2pac_logs/YYYY-MM-DD/2pac.db`.
- **Preloading**: Automatically preloads up to 8 days of history from previous SQLite databases at startup to enable seamless multi-day visualization without midnight discontinuities.
- **Thread Safety**: Uses internal threading locks and bulk-commits to SQLite every 2 seconds or 20 rows.
- **Schema Migration**: Automatically adds newly introduced columns (e.g., `vac_can_pressure_torr`) via `ALTER TABLE` to older daily database files without data loss.

### 2. State Machine & Safety (`states.py`, `world.py`, `imperative_statemachine.py`)
- **Imperative States**: Python generator functions where `yield` pauses execution until time elapsed or user confirmation.
- **Safety Interlocks**:
  - **He-3 Overpressure**: Shuts down Cryocon heaters immediately if $P_{He3} > 9.5\text{ bar}$.
  - **Magnet De-energize Guard**: Prevents starting cooldown or He-3 cycles if $|I_{magnet}| > 0.2\text{ A}$.
  - **Warmup Protection**: Prevents warming the cryostat while the superconducting magnet is energized.
  - **Pre-flight Valve Check**: Verifies green valve state before thermal cycles.

### 3. Hardware Drivers (`instruments/`)
- **LabJack U3**: Reads analog inputs (He-3 pressure transducer on AIN1, magnet current shunt on AIN0, magnet voltage on AIN2, Kurt Lesker vacuum can Pirani gauge on AIN3) and actuates solid-state relays for heat switches (Charcoal, Pot, ADR). Uses `threading.RLock()` to prevent USB collision between telemetry reads and relay toggles.
- **Cryo-con 24C**: Queries 4-channel cryogenic diode and platinum thermometers (60K flange, Charcoal, 4K flange, 1K pot) and controls dual-loop PID heaters.
- **Lake Shore 370**: Resistance bridge reading sub-Kelvin Germanium / Ruthenium oxide sensor on FAA stage and controlling magnet power supply setpoint.
