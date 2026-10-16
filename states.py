import time
import numpy as np
import qcodes
import typing
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from engine import state, World

# Initialize globals to be populated by main.py
st = None
elapsed_time = None
datasaver_global = None
log_dir = None  # Set by main.py
ENABLE_TEXT_LOGGING = True

def _get_log_dir():
    """Get or create today's log directory."""
    global log_dir
    today = datetime.now().strftime("%Y-%m-%d")
    d = Path.home() / "2pac_logs" / today
    d.mkdir(parents=True, exist_ok=True)
    log_dir = d
    return d

_open_log_handles = {}
_current_log_day = None

def _log_to_file(results_list):
    """Append each channel value to its own .log file with persistent line-buffered file handles."""
    global _open_log_handles, _current_log_day
    d = _get_log_dir()
    today = d.name
    if today != _current_log_day:
        for h in _open_log_handles.values():
            try:
                h.close()
            except Exception:
                pass
        _open_log_handles.clear()
        _current_log_day = today

    now = time.time()
    local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in results_list:
        if isinstance(item, tuple) and len(item) == 2:
            param, value = item
            if isinstance(param, str):
                name = param
            else:
                name = getattr(param, 'name', str(param))
            
            handle = _open_log_handles.get(name)
            if handle is None or handle.closed:
                log_file = d / f"{name}.log"
                handle = open(log_file, "a", buffering=1, encoding="utf-8")
                _open_log_handles[name] = handle
            try:
                handle.write(f"{now},{local_time},{value}\n")
            except Exception:
                try:
                    log_file = d / f"{name}.log"
                    handle = open(log_file, "a", buffering=1, encoding="utf-8")
                    _open_log_handles[name] = handle
                    handle.write(f"{now},{local_time},{value}\n")
                except Exception:
                    pass

def retry(f, n=3):
    # try cryocon is being unreliable on returning temp, so try a few times then return nan
    for i in range(n):
        try:
            return f()
        except: 
            pass
    return np.nan

def update(datasaver, state):
    global st
    if st is None and hasattr(datasaver, "station") and datasaver.station is not None:
        st = datasaver.station
    if st is None:
        return
    ls370_out = retry(st.ls370.heater.out, n=1) if hasattr(st, "ls370") and st.ls370 is not None else np.nan
    faa_val = retry(st.ls370.ch04.temperature, n=2) if hasattr(st, "ls370") and st.ls370 is not None else np.nan

    # Auto-resync guard: detect if LS370 heater output (%) and FAA temperature (K) were swapped by serial FIFO collision
    if np.isfinite(faa_val) and np.isfinite(ls370_out):
        if faa_val > 20.0 and ls370_out < 2.0:
            faa_val, ls370_out = ls370_out, faa_val
            try:
                if hasattr(st, "ls370") and hasattr(st.ls370, "visa_handle"):
                    vh = st.ls370.visa_handle
                    if hasattr(vh, "flush"):
                        import pyvisa.constants as pv_const
                        vh.flush(pv_const.VI_READ_BUF_DISCARD)
                    elif hasattr(vh, "read_raw"):
                        vh.read_raw()
                    elif hasattr(vh, "read"):
                        vh.read()
            except Exception:
                pass

    cryo_params = [elapsed_time, st.cryocon.chA_temperature, st.cryocon.chB_temperature,
                   st.cryocon.chC_temperature, st.cryocon.chD_temperature,
                   st.labjack.kepco_current, st.labjack.kepco_voltage]
    lj_params = [st.labjack.relay, st.labjack.heatswitch_adr, st.labjack.heatswitch_charcoal,
                 st.labjack.heatswitch_pot, st.labjack.he3_pressure, st.labjack.vac_can_pressure_torr]

    l = [(param, retry(param, n=1)) for param in cryo_params] + [
        (st.ls370.heater.out, ls370_out),
    ] + [(param, retry(param, n=1)) for param in lj_params] + [
        ("state", state.name()),
        ("faa_temperature", faa_val),
        ("time", time.time())
    ]
    try:
        datasaver.add_result(*l)
    except Exception as e:
        print(f"Warning: datasaver.add_result error: {e}")
    if ENABLE_TEXT_LOGGING:
        try:
            _log_to_file(l)
        except Exception as e:
            print(f"Warning: _log_to_file error: {e}")

def most_recent_measurements():
    if datasaver_global is None:
        return {}
    try:
        data = datasaver_global.dataset.cache.data()
        ret = {}
        for key in data.keys():
            if key in data and key in data[key] and len(data[key][key]) > 0:
                v = data[key][key][-1]
                ret[key] = v
        return ret
    except Exception as e:
        print(f"Error reading recent measurements: {e}")
        return {}

def pretty_str_dict(d: dict):
    s = ""
    for key, value in d.items():
        s+= f"{key} {value}\n"
    return s

# Default ADR cycle and regulation configuration parameters
DEFAULT_ADR_CONFIG = {
    "charcoal_heat_sp": 55.0,        # Charcoal heater setpoint (K)
    "flange_60k_heat_sp": 65.0,      # 60K flange heater setpoint (K)
    "starting_temp_3k": 3.2,         # 3K stage starting temperature threshold (Channel C) before cycle starts (K)
    "pot_precool_limit_k": 3.2,      # Alias for starting_temp_3k
    "he3_condense_dwell_h": 3.5,     # Condensation dwell duration (hours)
    "launch_temp_k": 1.0,            # Launch temperature: FAA temp threshold before opening ADR heat switch and ramping down magnet (K)
    "launch_dwell_min": 10.0,        # Post-ADR-switch-open dwell / friction dissipation wait (minutes) before ramping down magnet
    "magnet_max_hout": 58.1,         # Magnet max heat output (%)
    "magnet_ramp_up_min": 45.0,      # Magnet ramp up duration (minutes)
    "magnet_ramp_down_min": 60.0,    # Magnet ramp down duration (minutes) - slower ramp avoids inductive lag and eddy heating
    "demag_settle_min": 20.0,        # Post-demag current settle wait (minutes) before zero-current interlock check
    "regulate_temp_mk": 50.0,        # Closed-loop PID regulation setpoint (mK)
    "regulate_temp_k": 0.050,        # Closed-loop PID regulation setpoint (K)
}

def get_adr_config(world=None):
    """Retrieve active ADR configuration dict from world or defaults."""
    cfg = dict(DEFAULT_ADR_CONFIG)
    if world is not None and hasattr(world, "adr_config") and isinstance(world.adr_config, dict):
        cfg.update(world.adr_config)
    return cfg

def get_adr_regulation_setpoint(world=None):
    """
    Retrieve regulation setpoint in (Kelvin, mK) safely handling mK vs K formats.
    Guarantees target_k is strictly in Kelvin (e.g. 0.050) and target_mk is in mK (e.g. 50.0).
    """
    cfg = get_adr_config(world)
    if "regulate_temp_mk" in cfg:
        target_mk = float(cfg["regulate_temp_mk"])
        target_k = target_mk / 1000.0 if target_mk >= 1.0 else target_mk
        if target_mk < 1.0:
            target_mk = target_k * 1000.0
    elif "regulate_temp_k" in cfg:
        val = float(cfg["regulate_temp_k"])
        if val >= 1.0:  # Value was saved in mK (e.g. 50.0)
            target_mk = val
            target_k = val / 1000.0
        else:  # Value was saved in K (e.g. 0.050)
            target_k = val
            target_mk = val * 1000.0
    else:
        target_k = 0.050
        target_mk = 50.0
    return target_k, target_mk

# Legacy constants maintained for compatibility
MAGNET_MAX_HOUT = 58.1           # LS370 open-loop output (%) at full field (~9.5 A)
MAGNET_RAMP_TIME_S = 30*60       # full-scale ramp duration
MAGNET_START_LIMIT_A = 0.2       # refuse to start a cycle above this magnet current

def check_magnet_deenergized(world):
    """Raise if the magnet is (or may be) energized. NaN / read failure counts as unsafe."""
    try:
        cur_relay = world.station.labjack.relay.cache.get()
    except Exception:
        cur_relay = None
    if cur_relay == "CONTROL":
        return 0.0

    try:
        mag_I = float(world.station.labjack.kepco_current())
    except Exception as e:
        raise RuntimeError(f"Refusing to start: cannot read magnet current ({e}).")

    try:
        mag_V = float(world.station.labjack.kepco_voltage())
    except Exception:
        mag_V = 0.0

    effective_limit = 0.6 if abs(mag_V) < 0.15 else MAGNET_START_LIMIT_A

    if not np.isfinite(mag_I) or abs(mag_I) > effective_limit:
        raise RuntimeError(
            f"Refusing to start: magnet current is {mag_I:.3f} A (limit {effective_limit:.1f} A). "
            "Run 'Ramp Down Magnet' first.")
    return mag_I

MAX_HE3_PRESSURE_BAR = 9.5

@dataclass
class StationWorld(World):
    station: qcodes.station.Station = None
    datasaver: typing.Any = None
    adr_config: dict = None

    def __post_init__(self):
        if self.adr_config is None:
            self.adr_config = dict(DEFAULT_ADR_CONFIG)

    def update(self, state):
        update(self.datasaver, state)
        # Continuous hardware safety interlock: if He-3 pressure exceeds limit,
        # immediately cut Cryocon heaters and abort the procedure safely.
        if self.station and hasattr(self.station, "labjack"):
            try:
                p_param = getattr(self.station.labjack, "he3_pressure", None)
                if p_param:
                    p = p_param.cache.get()
                    if p is None:
                        p = float(p_param())
                    if p > MAX_HE3_PRESSURE_BAR:
                        if hasattr(self.station, "cryocon"):
                            try:
                                self.station.cryocon.control_enabled(False)
                            except Exception:
                                pass
                        raise RuntimeError(
                            f"CRITICAL SAFETY INTERLOCK: He-3 pressure reached {p:.2f} bar (exceeds {MAX_HE3_PRESSURE_BAR} bar limit)! "
                            "Cryocon heaters shut off immediately."
                        )
            except RuntimeError:
                raise
            except Exception:
                pass

def safe_set_heatswitch(world, hs_name: str, target_state: str):
    """Set heatswitch only if its cached state is not already target_state, avoiding redundant relay pulses."""
    try:
        if world and hasattr(world, "station") and hasattr(world.station, "labjack"):
            param = getattr(world.station.labjack, f"heatswitch_{hs_name}", None)
            if param is not None:
                cur = param.cache.get()
                if cur != target_state:
                    param(target_state)
    except Exception as e:
        print(f"Warning: safe_set_heatswitch({hs_name}, {target_state}) error: {e}")

@state 
def he3_adr_cycle(world: StationWorld):
    testmode = False
    cfg = get_adr_config(world)

    charcoal_sp = float(cfg.get("charcoal_heat_sp", 55.0))
    flange_sp = float(cfg.get("flange_60k_heat_sp", 65.0))
    limit_3k = float(cfg.get("starting_temp_3k", cfg.get("pot_precool_limit_k", 3.2)))

    condense_dwell_s = float(cfg.get("he3_condense_dwell_h", 3.5)) * 3600.0
    launch_temp_k = float(cfg.get("launch_temp_k", 1.0))
    launch_dwell_s = float(cfg.get("launch_dwell_min", 10.0)) * 60.0

    target_hout = float(cfg.get("magnet_max_hout", MAGNET_MAX_HOUT))
    ramp_up_s = float(cfg.get("magnet_ramp_up_min", 45.0)) * 60.0
    ramp_down_s = float(cfg.get("magnet_ramp_down_min", 60.0)) * 60.0
    demag_settle_s = float(cfg.get("demag_settle_min", 20.0)) * 60.0
    if "regulate_temp_mk" in cfg:
        target_mk = float(cfg["regulate_temp_mk"])
        reg_temp_k = target_mk / 1000.0
    else:
        reg_temp_k = float(cfg.get("regulate_temp_k", 0.050))
        target_mk = reg_temp_k * 1000.0

    # 0. safety: never start (and ramp from 0) while the magnet is energized
    check_magnet_deenergized(world)
    # Operator must close the green He-3 valve BEFORE step 1 (also confirmed in GUI)
    print("CLOSE THE GREEN HE3 VALVE")

    # 1. Close all heat switches in the beginning and wait 30 seconds before switching relay to RAMP
    world.set_phase(f"Pre-cooling: Closing All Heat Switches (30s settle)", 1, 6)
    safe_set_heatswitch(world, "pot", "CLOSED")
    world.wait(1)
    safe_set_heatswitch(world, "adr", "CLOSED")
    world.wait(1)
    safe_set_heatswitch(world, "charcoal", "CLOSED")
    world.wait(30)

    # Pre-cooling temperature check (ensure 3K stage is cold enough)
    world.set_phase(f"Pre-cooling Check (3K < {limit_3k:.1f}K)", 1, 6)
    while True:
        mr = most_recent_measurements()
        c_temp = mr.get("cryocon_chC_temperature")
        if c_temp is not None and np.isfinite(c_temp) and float(c_temp) < limit_3k:
            break
        world.wait(1)

    # 2. Switch relay to RAMP and ensure current starts from zero
    world.station.labjack.relay("RAMP")
    world.wait(1)
    ramp_controller = world.station.ls370.heater
    ramp_controller.mode('open_loop')
    world.wait(1)
    ramp_controller.out(0.0)
    world.wait(1)
    ramp_controller.range("10mA")
    world.wait(1)

    # 3. Open charcoal heatswitch and start heating sorption charcoal
    world.set_phase(f"Heating Sorption Charcoal ({charcoal_sp:.0f}K)", 2, 6)
    safe_set_heatswitch(world, "charcoal", "OPEN")
    world.wait(1)
    world.station.cryocon.loop1_source("A")
    world.wait(1)
    world.station.cryocon.loop1_setpoint(flange_sp)
    world.wait(1)
    world.station.cryocon.loop2_source("B")
    world.wait(1)
    world.station.cryocon.loop2_range("HI")
    world.wait(1)
    world.station.cryocon.loop2_setpoint(charcoal_sp)
    world.wait(1)
    world.station.cryocon.control_enabled(True) # heat charcoal
    world.wait(1)

    # 4. Ramp up ADR magnet current starting smoothly from zero
    world.set_phase("Ramping ADR Magnet Up (0% -> max)", 3, 6)

    if testmode:
        t_hout = 1.0 # small max current
        t_time_s = 30.0
    else:
        t_hout = target_hout
        t_time_s = ramp_up_s

    t_start_ramp = time.time()
    while True:
        elapsed = time.time() - t_start_ramp
        fraction = min(1.0, elapsed / max(1.0, t_time_s))
        hout = fraction * t_hout
        ramp_controller.out(float(hout))
        if fraction >= 1.0:
            break
        world.wait(1)

    # 4. wait for he3 to condense
    world.set_phase("He-3 Condensation Dwell", 4, 6)
    if testmode:
        world.wait(10)
    else:
        world.wait(condense_dwell_s)

    # 5. cool charcoal and wait for FAA to reach launch temperature
    disp_launch = f"{launch_temp_k * 1000.0:.0f}mK" if launch_temp_k < 1.0 else f"{launch_temp_k:.2f}K"
    world.set_phase(f"Cooling to Launch Temp (FAA < {disp_launch})", 5, 6)
    safe_set_heatswitch(world, "pot", "OPEN")
    world.wait(1)
    world.station.cryocon.control_enabled(False) # turn off heaters
    if testmode:
        world.wait(1)
    else: 
        world.wait(120) # a bit of cooling before closing charcoal heatswitch
    safe_set_heatswitch(world, "charcoal", "CLOSED")  
    world.wait(1)
    
    if testmode:
        world.wait(5)
    else:
        while True:
            mr = most_recent_measurements()
            faa_t = mr.get("faa_temperature")
            if faa_t is not None and np.isfinite(faa_t) and float(faa_t) < launch_temp_k:
                break
            world.wait(1)

    # 6. ramp down adr
    safe_set_heatswitch(world, "adr", "OPEN")
    world.wait(1)

    if launch_dwell_s > 0:
        world.set_phase(f"Launch Settle (Waiting {launch_dwell_s/60.0:.0f}m)", 6, 6)
        if testmode:
            world.wait(5)
        else:
            world.wait(launch_dwell_s)

    target_k, target_mk = get_adr_regulation_setpoint(world)
    reg_disp = f"{target_mk:.0f}mK" if target_mk < 1000.0 else f"{target_k:.3f}K"
    world.set_phase(f"Demag Ramp Down & Regulate @ {reg_disp}", 6, 6)

    if testmode:
        t_down_time_s = 30.0
    else:
        t_down_time_s = ramp_down_s

    t_start_down = time.time()
    while True:
        elapsed = time.time() - t_start_down
        fraction = min(1.0, elapsed / max(1.0, t_down_time_s))
        hout = (1.0 - fraction) * t_hout
        ramp_controller.out(float(hout))
        if fraction >= 1.0:
            break
        world.wait(1)

    # 7. Settle and verify magnet current has genuinely reached near-zero (< 0.05 A) before switching relay
    world.set_phase("Demag Settle (Waiting for I < 0.05A)", 6, 6)
    if testmode:
        world.wait(5)
    else:
        t_settle_start = time.time()
        while True:
            elapsed_settle = time.time() - t_settle_start
            mr = most_recent_measurements()
            cur_i = mr.get("labjack_kepco_current")
            # Must wait at least demag_settle_s AND actual current must be < 0.05 A
            if elapsed_settle >= demag_settle_s:
                if cur_i is not None and np.isfinite(cur_i) and abs(float(cur_i)) < 0.05:
                    break
                # Fallback timeout if sensor is offline or has tiny DC offset
                if elapsed_settle >= (demag_settle_s + 900.0) and (cur_i is None or abs(float(cur_i)) < 0.10):
                    break
            world.wait(1)

    # 8. Demag complete: transition directly to closed-loop temperature regulation holding state
    return regulate_temperature

@state
def ramp_down_magnet(world: StationWorld):
    # Safely ramps the LS370 open-loop output (magnet current) from its present
    # value to 0 at the configured magnet ramp-down rate, then holds idle.
    # Heat switches, relay and Cryo-con are left untouched.
    world.set_phase("Safe Ramp Down: reading magnet drive", 1, 1)
    rc = world.station.ls370.heater
    mode_now = rc.mode()
    start_hout = float(rc.out())
    if mode_now != "open_loop":
        print(f"ramp_down_magnet: LS370 heater in '{mode_now}' mode; safely resetting to open_loop 0.0% and disabling heater range.")
        rc.mode("open_loop")
        world.wait(1)
        rc.out(0.0)
        world.wait(1)
        rc.range("off")
        world.wait(1)
        world.station.labjack.relay("RAMP")
        world.set_phase("Idle — Magnet De-energized & Heater Off", 1, 1)
        return wait_forever
    if not np.isfinite(start_hout) or start_hout <= 0:
        rc.out(0.0)
        rc.range("off")
        world.station.labjack.relay("RAMP")
        world.set_phase("Idle — Holding Steady (0A)", 1, 1)
        return wait_forever
    cfg = get_adr_config(world)
    max_hout = float(cfg.get("magnet_max_hout", MAGNET_MAX_HOUT))
    ramp_time_s = float(cfg.get("magnet_ramp_down_min", 45.0)) * 60.0
    actual_ramp_time_s = max(1.0, (start_hout / max(0.01, max_hout)) * ramp_time_s)
    world.set_phase(f"Safe Ramp Down: {start_hout:.1f}% -> 0%", 1, 1)
    t_start_safe = time.time()
    while True:
        elapsed = time.time() - t_start_safe
        fraction = min(1.0, elapsed / actual_ramp_time_s)
        hout = (1.0 - fraction) * start_hout
        rc.out(float(hout))
        if fraction >= 1.0:
            break
        world.wait(1)
    rc.out(0.0)
    world.wait(1)
    rc.range("off")
    world.wait(1)
    world.station.labjack.relay("RAMP")
    world.set_phase("Idle — Holding Steady (magnet ramped down)", 1, 1)
    return wait_forever

@state
def wait_forever(world: StationWorld):
    world.set_phase("Idle — Holding Steady", 1, 1)
    while True:
        world.wait(1)

@state
def wait_forever2(world: StationWorld):
    world.wait(1e18)

@state
def switch_to_wait_forever_test(world: StationWorld):
    return wait_forever

@state
def ready_for_cooldown(world:StationWorld):
    # Doesn't really do anything except close HS 
    world.set_phase("Pre-cooling: Heat switches closed", 1, 1)
    world.station.labjack.heatswitch_pot("CLOSED")
    world.station.labjack.heatswitch_adr("CLOSED")
    world.station.labjack.heatswitch_charcoal("CLOSED")
    world.wait(3)

    # Set He3 setpoints but do nothing
    world.station.cryocon.loop1_source("A")
    world.station.cryocon.loop1_setpoint(45) # Upper stage setpoint = 45 K
    world.station.cryocon.loop2_source("B")
    world.station.cryocon.loop2_setpoint(55) # Charcoal setpoint = 55 K
    world.station.cryocon.control_enabled(False) 
    print("OPEN THE GREEN HE3 VALVE")
    world.wait(1e6)

@state
def open_charcoal_heatswitch(world: StationWorld):
    world.station.labjack.heatswitch_charcoal("OPEN")
    return wait_forever

@state
def open_pot_heatswitch(world: StationWorld):
    world.station.labjack.heatswitch_pot("OPEN")
    return wait_forever

@state
def open_adr_heatswitch(world: StationWorld):
    world.station.labjack.heatswitch_adr("OPEN")
    return wait_forever

@state
def set_relay_to_ramp(world: StationWorld):
    world.station.labjack.relay("RAMP")
    return wait_forever

@state
def he3_only_cycle(world: StationWorld):
    """
    Helium-3 Sorption Refrigerator Cycle (No Magnet / No ADR).
    Cycles the sorption pump to condense He-3 and achieve ~300 mK base temperature
    at the 1K pot without touching or energizing the superconducting magnet.
    """
    testmode = False
    cfg = get_adr_config(world)

    charcoal_sp = float(cfg.get("charcoal_heat_sp", 55.0))
    flange_sp = float(cfg.get("flange_60k_heat_sp", 65.0))
    limit_3k = float(cfg.get("starting_temp_3k", cfg.get("pot_precool_limit_k", 3.2)))

    condense_dwell_s = float(cfg.get("he3_condense_dwell_h", 3.5)) * 3600.0
    launch_temp_k = float(cfg.get("launch_temp_k", 1.0))

    # 0. safety: check magnet is de-energized and ensure relay is set to CONTROL (magnet isolated)
    check_magnet_deenergized(world)
    if hasattr(world, "station") and hasattr(world.station, "labjack") and hasattr(world.station.labjack, "relay"):
        try:
            cur_rel = world.station.labjack.relay.cache.get()
            if cur_rel != "CONTROL":
                world.station.labjack.relay("CONTROL")
                world.wait(1)
        except Exception as e:
            print(f"Warning setting relay to CONTROL: {e}")

    # Operator must close the green He-3 valve BEFORE step 1
    print("CLOSE THE GREEN HE3 VALVE")

    # 1. set heat switches and check that we're cold enough to start
    # Pot and ADR heat switches are CLOSED so the FAA stage is connected to the He-3 pot
    world.set_phase(f"Pre-cooling Check (3K < {limit_3k:.1f}K)", 1, 4)
    safe_set_heatswitch(world, "pot", "CLOSED")
    world.wait(1)
    safe_set_heatswitch(world, "adr", "CLOSED")
    world.wait(1)
    safe_set_heatswitch(world, "charcoal", "OPEN")
    world.wait(1)
    while True:
        mr = most_recent_measurements()
        c_temp = mr.get("cryocon_chC_temperature")
        if c_temp is not None and np.isfinite(c_temp) and float(c_temp) < limit_3k:
            break
        world.wait(1)

    # 2. start heating charcoal
    world.set_phase(f"Heating Sorption Charcoal ({charcoal_sp:.0f}K)", 2, 4)
    world.station.cryocon.loop1_source("A")
    world.wait(1)
    world.station.cryocon.loop1_setpoint(flange_sp)
    world.wait(1)
    world.station.cryocon.loop2_source("B")
    world.wait(1)
    world.station.cryocon.loop2_range("HI")
    world.wait(1)
    world.station.cryocon.loop2_setpoint(charcoal_sp) # Charcoal setpoint = 55 K
    world.wait(1)
    world.station.cryocon.control_enabled(True) # heat charcoal
    world.wait(1)

    # 3. wait for he3 to condense
    world.set_phase("He-3 Condensation Dwell", 3, 4)
    if testmode:
        world.wait(10)
    else:
        world.wait(condense_dwell_s) # takes about 3.5 hours to condense He-3

    # 4. cool charcoal and wait for launch/base temperature
    # Open pot heat switch to isolate 1K pot from 4K, but keep ADR switch CLOSED so FAA cools with pot
    disp_launch = f"{launch_temp_k * 1000.0:.0f}mK" if launch_temp_k < 1.0 else f"{launch_temp_k:.2f}K"
    world.set_phase(f"Cooling to Base Temp (FAA / Pot < {disp_launch})", 4, 4)
    safe_set_heatswitch(world, "pot", "OPEN") # thermally isolate 1K pot from 4K bath
    world.wait(1)
    safe_set_heatswitch(world, "adr", "CLOSED") # keep ADR heat switch connected to the pot
    world.wait(1)
    world.station.cryocon.control_enabled(False) # turn off heaters
    if testmode:
        world.wait(1)
    else: 
        world.wait(120) # a bit of cooling before closing charcoal heatswitch
    safe_set_heatswitch(world, "charcoal", "CLOSED")  
    world.wait(1)
    safe_set_heatswitch(world, "adr", "CLOSED") # keep ADR heat switch connected to the pot
    world.wait(1)
    
    if testmode:
        world.wait(5)
    else:
        while True:
            mr = most_recent_measurements()
            faa_t = mr.get("faa_temperature")
            pot_t = mr.get("cryocon_chD_temperature")
            if (faa_t is not None and np.isfinite(faa_t) and float(faa_t) < launch_temp_k) or (pot_t is not None and np.isfinite(pot_t) and float(pot_t) < launch_temp_k):
                break
            world.wait(1)

    # Done — holding steady at base temperature with ADR heat switch connected to the pot
    safe_set_heatswitch(world, "adr", "CLOSED")
    world.set_phase("Idle — Holding Steady (He-3 Base Temp, ADR Switch Connected)", 1, 1)
    return wait_forever

@state
def regulate_temperature(world: StationWorld):
    """
    Engage closed-loop PID temperature regulation on the Lake Shore 370 in CONTROL mode.
    Regulates stage temperature via physical stage heater resistor (relay switches to CONTROL).
    Applies tuning with 100 Ohm Kepco shunt: P=0.05, I=12, D=0, R=100 Ohm, 10mA range.
    Holds indefinitely in this state and continuously checks for setpoint updates.
    """
    check_magnet_deenergized(world)

    target_k, target_mk = get_adr_regulation_setpoint(world)
    disp_target = f"{target_mk:.1f} mK" if target_mk < 1000.0 else f"{target_k:.3f} K"
    world.set_phase(f"Regulating @ {disp_target}", 1, 1)

    ls = getattr(world.station, "ls370", None)
    rc = ls.heater if ls else None

    try:
        cur_relay = world.station.labjack.relay.cache.get()
    except Exception:
        cur_relay = None
    if cur_relay != "CONTROL":
        world.set_phase("Switching Relay to CONTROL (5s settle)", 1, 1)
        if rc:
            rc.mode('open_loop')
            rc.out(0.0)
            rc.range('off')
        if ls:
            try:
                ls.write("RAMP 0, 0")
            except Exception:
                pass
        world.station.labjack.relay("CONTROL")
        world.wait(5)

    # Load user-configured PID, R value, and ramp speed settings from gui_settings.json
    pid_cfg = {}
    try:
        from pathlib import Path
        import json
        cfg_p = Path.home() / "2pac_logs" / "gui_settings.json"
        if cfg_p.exists():
            with open(cfg_p) as f:
                pid_cfg = json.load(f).get("pid_config", {})
    except Exception:
        pid_cfg = {}

    p_val = float(pid_cfg.get("p", 0.05))
    i_val = float(pid_cfg.get("i", 12.0))
    d_val = float(pid_cfg.get("d", 0.0))
    r_val = float(pid_cfg.get("heater_resistance", 100.0))
    ch_val = int(pid_cfg.get("channel", 4))
    limit_val = int(pid_cfg.get("heater_limit", 6))
    htr_range = str(pid_cfg.get("heater_range", "10mA"))
    ramp_en = 1 if pid_cfg.get("ramp_enable", False) else 0
    ramp_k = float(pid_cfg.get("ramp_rate_mk_min", 10.0)) / 1000.0

    # 1. Configure Lake Shore 370 control loop parameters (CSET)
    if ls:
        try:
            ls.write(f"CSET {ch_val}, 1, 1, 1, 1, {limit_val}, {r_val:.1f}")
        except Exception as e:
            print(f"Warning: could not set CSET on LS370: {e}")
        world.wait(1)

        # 2. Configure PID gains
        try:
            ls.write(f"PID {p_val:.4f}, {i_val:.1f}, {d_val:.1f}")
        except Exception as e:
            print(f"Warning: could not set PID on LS370: {e}")
        world.wait(1)

        # 3. Configure Setpoint Ramping
        try:
            ls.write(f"RAMP {ramp_en}, {ramp_k:.4f}")
        except Exception as e:
            print(f"Warning: could not set RAMP on LS370: {e}")
        world.wait(1)

        # 4. Lock scan to Control Channel so scanner does not hop during regulation
        try:
            ls.write(f"SCAN {ch_val}, 0")
        except Exception as e:
            print(f"Warning: could not set SCAN on LS370: {e}")
        world.wait(1)

    # 5. Enable closed loop PID mode
    if rc:
        try:
            cur_mode = rc.mode.cache.get()
        except Exception:
            cur_mode = None
        if cur_mode != "closed":
            rc.mode('closed')
            world.wait(1)

        # 6. Set setpoint in Kelvin (AFTER entering closed loop so LS370 does not overwrite it with current temp)
        rc.setpoint(target_k)
        if ls:
            try:
                ls.write(f"SETP {target_k:.4f}")
            except Exception:
                pass
        world.wait(1)

        # 7. Enable heater excitation range
        try:
            rc.range(htr_range)
        except Exception:
            rc.range("10mA")

    last_applied_sp = target_k
    world.set_phase(f"Regulating @ {disp_target}", 1, 1)

    while True:
        cur_k, cur_mk = get_adr_regulation_setpoint(world)
        if abs(cur_k - last_applied_sp) > 1e-6:
            if ls:
                try:
                    ls.write(f"SETP {cur_k:.4f}")
                except Exception:
                    pass
            if rc:
                try:
                    rc.setpoint(cur_k)
                except Exception:
                    pass
            last_applied_sp = cur_k
            cur_disp = f"{cur_mk:.1f} mK" if cur_mk < 1000.0 else f"{cur_k:.3f} K"
            world.set_phase(f"Regulating @ {cur_disp}", 1, 1)
        world.wait(1)

@state
def warmup_300K(world: StationWorld):
    # Safety: ensure magnet is de-energized before warming up
    check_magnet_deenergized(world)
    print("OPEN THE GREEN HE3 VALVE")

    world.set_phase("Warming cryostat to 295 K", 1, 1)
    world.station.labjack.heatswitch_pot("CLOSED")
    world.station.labjack.heatswitch_adr("CLOSED")
    world.station.labjack.heatswitch_charcoal("CLOSED")
    world.wait(3)
    world.station.cryocon.loop1_source("A")
    world.station.cryocon.loop1_setpoint(295) # Upper stage setpoint = 295 K
    world.station.cryocon.loop2_source("B")
    world.station.cryocon.loop2_range("HI")
    world.station.cryocon.loop2_setpoint(295) # Charcoal setpoint = 295 K
    world.station.cryocon.control_enabled(True) # heat charcoal
    world.wait(1e15)

def find_full_field_start_time(target_hout):
    """Find timestamp when magnet first reached full field today without yielding across log lines."""
    try:
        today_log = Path.home() / "2pac_logs" / datetime.now().strftime("%Y-%m-%d") / "out.log"
        if today_log.exists():
            with open(today_log, "r") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 3:
                        try:
                            if float(parts[2]) >= (target_hout - 1.0):
                                return float(parts[0])
                        except ValueError:
                            continue
    except Exception as e:
        print(f"Notice: Could not parse full field start time: {e}")
    return None

@state
def resume_he3_adr_cycle(world: StationWorld):
    """
    Resume an in-progress He-3 + ADR cycle from Condensation Dwell (Step 4/6) or Cooling (Step 5/6).
    Leaves the magnet energized at full field, verifies all heat switches and
    Cryo-con loops, completes the remaining condensation dwell time, then
    cools charcoal (Step 5) and ramps down the magnet (Step 6) to regulate at base.
    """
    testmode = False
    cfg = get_adr_config(world)
    charcoal_sp = float(cfg.get("charcoal_heat_sp", 55.0))
    flange_sp = float(cfg.get("flange_60k_heat_sp", 65.0))
    condense_dwell_s = float(cfg.get("he3_condense_dwell_h", 3.5)) * 3600.0
    launch_temp_k = float(cfg.get("launch_temp_k", 1.0))
    launch_dwell_s = float(cfg.get("launch_dwell_min", 10.0)) * 60.0

    target_hout = float(cfg.get("magnet_max_hout", MAGNET_MAX_HOUT))
    ramp_down_s = float(cfg.get("magnet_ramp_down_min", 60.0)) * 60.0
    demag_settle_s = float(cfg.get("demag_settle_min", 20.0)) * 60.0
    if "regulate_temp_mk" in cfg:
        target_mk = float(cfg["regulate_temp_mk"])
        reg_temp_k = target_mk / 1000.0
    else:
        reg_temp_k = float(cfg.get("regulate_temp_k", 0.050))
        target_mk = reg_temp_k * 1000.0

    t_full_field = find_full_field_start_time(target_hout)
    now = time.time()
    condensation_complete = (t_full_field is not None and (now - t_full_field) >= condense_dwell_s)

    # Check if charcoal is already cold (< 15 K)
    mr_init = most_recent_measurements()
    ch_b = mr_init.get("cryocon_chB_temperature")
    charcoal_already_cold = (ch_b is not None and np.isfinite(ch_b) and float(ch_b) < 15.0)

    if condensation_complete or charcoal_already_cold:
        # Step 4 condensation dwell is already finished and charcoal is cold
        # Maintain existing switch positions without pulsing: Pot OPEN, Charcoal CLOSED, ADR CLOSED
        safe_set_heatswitch(world, "pot", "OPEN")
        world.wait(1)
        safe_set_heatswitch(world, "charcoal", "CLOSED")
        world.wait(1)
        safe_set_heatswitch(world, "adr", "CLOSED")
        world.wait(1)
        if hasattr(world.station, "cryocon"):
            try:
                world.station.cryocon.control_enabled(False)
            except Exception:
                pass
    else:
        # Step 4: Condensation Dwell
        safe_set_heatswitch(world, "pot", "CLOSED")
        world.wait(1)
        safe_set_heatswitch(world, "adr", "CLOSED")
        world.wait(1)
        safe_set_heatswitch(world, "charcoal", "OPEN")
        world.wait(1)

        world.station.cryocon.loop1_source("A")
        world.wait(1)
        world.station.cryocon.loop1_setpoint(flange_sp)
        world.wait(1)
        world.station.cryocon.loop2_source("B")
        world.wait(1)
        world.station.cryocon.loop2_range("HI")
        world.wait(1)
        world.station.cryocon.loop2_setpoint(charcoal_sp)
        world.wait(1)
        world.station.cryocon.control_enabled(True)
        world.wait(1)

        remaining_s = max(10.0, condense_dwell_s - (now - t_full_field)) if t_full_field is not None else condense_dwell_s
        world.set_phase("He-3 Condensation Dwell", 4, 6)
        if testmode:
            world.wait(10)
        else:
            world.wait(remaining_s)

        # 5. cool charcoal and wait for FAA to reach launch temperature
        safe_set_heatswitch(world, "pot", "OPEN")
        world.wait(1)
        world.station.cryocon.control_enabled(False)
        if not testmode:
            world.wait(120)
        safe_set_heatswitch(world, "charcoal", "CLOSED")
        world.wait(1)

    # 5. Cooling to launch temp phase
    disp_launch = f"{launch_temp_k * 1000.0:.0f}mK" if launch_temp_k < 1.0 else f"{launch_temp_k:.2f}K"
    world.set_phase(f"Cooling to Launch Temp (FAA < {disp_launch})", 5, 6)
    if testmode:
        world.wait(5)
    else:
        while True:
            mr = most_recent_measurements()
            faa_t = mr.get("faa_temperature")
            if faa_t is not None and np.isfinite(faa_t) and float(faa_t) < launch_temp_k:
                break
            world.wait(1)

    # 6. ramp down adr
    safe_set_heatswitch(world, "adr", "OPEN")
    world.wait(1)

    if launch_dwell_s > 0:
        world.set_phase(f"Launch Settle (Waiting {launch_dwell_s/60.0:.0f}m)", 6, 6)
        if testmode:
            world.wait(5)
        else:
            world.wait(launch_dwell_s)

    target_k, target_mk = get_adr_regulation_setpoint(world)
    reg_disp = f"{target_mk:.0f}mK" if target_mk < 1000.0 else f"{target_k:.3f}K"
    world.set_phase(f"Demag Ramp Down & Regulate @ {reg_disp}", 6, 6)

    t_start_down = time.time()
    t_down_time_s = 30.0 if testmode else ramp_down_s
    ramp_controller = world.station.ls370.heater
    while True:
        elapsed = time.time() - t_start_down
        fraction = min(1.0, elapsed / max(1.0, t_down_time_s))
        hout = (1.0 - fraction) * target_hout
        ramp_controller.out(float(hout))
        if fraction >= 1.0:
            break
        world.wait(1)

    # Settle and verify magnet current has genuinely reached near-zero (< 0.05 A) before switching relay
    world.set_phase("Demag Settle (Waiting for I < 0.05A)", 6, 6)
    if testmode:
        world.wait(5)
    else:
        t_settle_start = time.time()
        while True:
            elapsed_settle = time.time() - t_settle_start
            mr = most_recent_measurements()
            cur_i = mr.get("labjack_kepco_current")
            # Must wait at least demag_settle_s AND actual current must be < 0.05 A
            if elapsed_settle >= demag_settle_s:
                if cur_i is not None and np.isfinite(cur_i) and abs(float(cur_i)) < 0.05:
                    break
                # Fallback timeout if sensor is offline or has tiny DC offset
                if elapsed_settle >= (demag_settle_s + 900.0) and (cur_i is None or abs(float(cur_i)) < 0.10):
                    break
            world.wait(1)

    # Demag complete: transition directly to closed-loop temperature regulation holding state
    return regulate_temperature

STATES_LIST = [
    wait_forever,
    ready_for_cooldown,
    he3_only_cycle,
    he3_adr_cycle,
    resume_he3_adr_cycle,
    regulate_temperature,
    ramp_down_magnet,
    warmup_300K,
    wait_forever2,
    switch_to_wait_forever_test,
    open_adr_heatswitch,
    open_charcoal_heatswitch,
    open_pot_heatswitch,
    set_relay_to_ramp,
]
STATES_DICT = {s.name(): s for s in STATES_LIST}
