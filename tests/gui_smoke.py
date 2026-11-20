"""
Offscreen GUI smoke scenarios with the fake station from test_state_machine (no hardware).

Run through tests/test_gui_smoke.py, which starts each scenario in its own process with HOME pointed at a fresh
temporary directory (settings, logs and the ~/.2pac/ipc command channel must never be the real ones) and
QT_QPA_PLATFORM=offscreen. Each scenario prints "RESULT ok" or "RESULT fail: ..." and exits.
"""
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

if os.environ.get("PAC2_GUI_SMOKE") != "1":
    sys.exit("refusing to run: start through tests/test_gui_smoke.py (it isolates HOME)")

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

errors = []
sys.excepthook = lambda *a: errors.append("".join(traceback.format_exception(*a)))
import threading  # noqa: E402
threading.excepthook = lambda a: errors.append("".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))

from PyQt5.QtCore import QEvent, Qt  # noqa: E402
from PyQt5.QtGui import QKeyEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def pump(s=0.5):
    t0 = time.time()
    while time.time() - t0 < s:
        app.processEvents()
        time.sleep(0.02)


def build(prev_state=None, stale_loop=False):
    """Fake station + MyApp. prev_state writes a state.log as if a previous instance had been running it."""
    start = time.time()
    if prev_state:
        d = Path.home() / "2pac_logs" / datetime.now().strftime("%Y-%m-%d")
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "state.log", "w") as f:
            for k in range(5):
                t = start - 100 + 2 * k
                f.write(f"{t},{datetime.fromtimestamp(t)},{prev_state}\n")
    os.environ["PAC2_START_TIME"] = str(start)
    import test_state_machine as T
    import states
    FT = T.FakeTime()
    sim = T.Sim(FT, relay="CONTROL", limit=7)
    sim.ls.running_loop(out=45.0, stale=stale_loop)
    from daily_logger import DailyLogManager
    dl = DailyLogManager()
    world = states.StationWorld(station=sim.station)
    world.datasaver = dl
    import gui
    w = gui.MyApp(world, dl.dataset, states.STATES_DICT, daily_logger=dl)
    w.resize(1600, 1000)
    w.show()
    pump(3)
    return gui, states, sim, world, w


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def scenario_build():
    gui, states, sim, world, w = build(stale_loop=True)
    for c in ("_update_heatswitch_ui", "_relay_switch_blocked_reason", "apply_theme",
              "toggle_theme", "reset_zoom", "_update_faa_card_rms_title", "_cached_relay_state"):
        getattr(w, c)()
    (gui.IPC_DIR / "gui_command.txt").write_text("query_ls370:CMODE?,HTR?\n")
    w._check_telemetry_watchdog()
    pump(5)
    reply = (gui.IPC_DIR / "ls370_state.json")
    check(reply.exists() and '"CMODE?": "4"' in reply.read_text(), "query_ls370 reply missing")
    check(bool(getattr(w, "_ls370_loop", {}).get("stale")), "stale LS370 registers not detected")


def scenario_resume_regulation():
    gui, states, sim, world, w = build(prev_state="regulate_temperature")
    w._cached_relay_state = lambda: "CONTROL"
    w._startup_resume_check()
    pump(4)
    check(w.data_thread.state is not None and w.data_thread.state.name() == "regulate_temperature",
          f"not re-adopted: {w.data_thread.state.name() if w.data_thread.state else None}")


def scenario_resume_cycle_banner():
    gui, states, sim, world, w = build(prev_state="he3_adr_cycle")
    w._startup_resume_check()
    pump(2)
    check(w.data_thread.state.name() == "wait_forever", "a cycle must not resume automatically")
    check(any("He-3 + ADR Cycle" in n["text"] for n in w._alert_notices), "no 'procedure interrupted' notice")


def scenario_alert_window():
    gui, states, sim, world, w = build()
    w.show_operator_banner("notice one")
    pump()
    d = w._alert_dialog
    check(d.isVisible() and d.btn_ack.isVisible() and not d.btn_confirm.isVisible(), "notice layout")
    world.request_operator_action("Launch timed out: Confirm Step Done to demag")
    pump()
    check(d.btn_confirm.isVisible() and len(w._alert_actions) == 1, "action layout")
    app.sendEvent(d, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    d.close()
    pump()
    check(d.isVisible(), "Esc/close must not dismiss")
    d.btn_ack.click()
    pump()
    check(not world.is_operator_action_confirmed() and d.isVisible(), "Acknowledge must not confirm the action")
    world.notify_operator("dup")
    world.notify_operator("dup")
    pump()
    check([n["count"] for n in w._alert_notices] == [2], "duplicates not collapsed")
    d.btn_confirm.click()
    pump()
    check(world.is_operator_action_confirmed(), "Confirm Step Done did not confirm")
    d.btn_ack.click()
    pump()
    check(not d.isVisible(), "window should close when everything is answered")


def scenario_heatswitch_pulse_failure():
    gui, states, sim, world, w = build()
    lj = sim.station.labjack
    lj.heatswitch_adr.v = "CLOSED"
    w._hs_states["adr"] = "CLOSED"

    def fail(_):
        raise IOError("LabJack USB error (fake)")
    lj.heatswitch_adr.on_set = fail
    orig_call = type(lj.heatswitch_adr).__call__

    def call(self, *a):          # like qcodes: the cache only changes when the set succeeds
        if a:
            self.on_set(a[0])
            self.v = a[0]
            return None
        return orig_call(self)
    type(lj.heatswitch_adr).__call__ = call
    w.set_heatswitch_state("adr", "OPEN")
    pump(2)
    check(lj.heatswitch_adr.cache.get() == "CLOSED", "cache changed although the pulse failed")
    check(w._hs_states["adr"] == "CLOSED", "button state not reverted")
    check(any("FAILED" in n["text"] for n in w._alert_notices), "no failure notice")


def scenario_ipc_regulate_temp_units():
    gui, states, sim, world, w = build()
    (gui.IPC_DIR / "gui_command.txt").write_text("set_adr_param:regulate_temp_k:0.055\n")
    pump(4)
    check(abs(w.spin_reg_temp.value() - 55.0) < 1e-6, f"regulation box = {w.spin_reg_temp.value()} (want 55 mK)")


def scenario_query_cryocon():
    gui, states, sim, world, w = build()
    (gui.IPC_DIR / "gui_command.txt").write_text("query_cryocon\n")
    pump(4)
    f = gui.IPC_DIR / "cryocon_state.json"
    check(f.exists(), "no cryocon_state.json")
    import json
    d = json.loads(f.read_text())
    check(d.get("control_enabled") is True, f"control_enabled = {d.get('control_enabled')!r}")


def scenario_metric_cards():
    gui, states, sim, world, w = build()
    keys = list(w.metric_tiles)
    check(keys[0] == "cryocon_chA_temperature", f"first card is {keys[0]}")
    check(w.metric_tiles["cryocon_chA_temperature"]["accent"] == "#0284c7", "60K flange colour != plot colour")
    mr = {"cryocon_chA_temperature": 295.03, "cryocon_chB_temperature": 295.02, "cryocon_chC_temperature": 258.4,
          "cryocon_chD_temperature": 26.67, "faa_temperature": 26.62, "labjack_he3_pressure": 1.0,
          "labjack_kepco_current": 0.0049}
    w._update_latest_status(mr, {}, list(mr))
    pump(0.5)
    txt = {k: w.metric_tiles[k]["val"].text() for k in mr if k in w.metric_tiles}
    check(txt["cryocon_chD_temperature"].startswith("OVERRANGE"), f"pot tile: {txt['cryocon_chD_temperature']}")
    check(txt["faa_temperature"].startswith("OVERRANGE"), f"FAA tile: {txt['faa_temperature']}")
    check("295" in txt["cryocon_chA_temperature"], f"60K tile: {txt['cryocon_chA_temperature']}")
    shot = os.environ.get("PAC2_SMOKE_SHOT")
    if shot:
        w.metric_cards_bar.grab().save(shot)


SCENARIOS = {k[len("scenario_"):]: v for k, v in dict(globals()).items() if k.startswith("scenario_")}

if __name__ == "__main__":
    name = sys.argv[1]
    try:
        SCENARIOS[name]()
        pump(0.5)
        if errors:
            print("RESULT fail: unhandled errors:\n" + "\n----\n".join(e[-1500:] for e in errors[:3]))
        else:
            print("RESULT ok")
    except Exception:
        print("RESULT fail: " + traceback.format_exc(limit=4))
    sys.stdout.flush()
    os._exit(0)
