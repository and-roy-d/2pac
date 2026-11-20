"""
Offscreen GUI smoke tests (no hardware, no real settings): each scenario in tests/gui_smoke.py runs in its own
process with HOME set to a fresh temporary directory.

    .venv/bin/python tests/test_gui_smoke.py            (plain runner)
    .venv/bin/python -m pytest tests/                   (if pytest is installed)
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SCENARIO_NAMES = ["build", "resume_regulation", "resume_cycle_banner", "alert_window",
                  "heatswitch_pulse_failure", "ipc_regulate_temp_units", "query_cryocon",
                  "metric_cards"]


def run_scenario(name, timeout=180):
    with tempfile.TemporaryDirectory(prefix="pac2_gui_smoke_") as home:
        (Path(home) / "2pac_logs").mkdir()
        env = dict(os.environ, HOME=home, QT_QPA_PLATFORM="offscreen", PAC2_GUI_SMOKE="1")
        env.pop("PAC2_SUPERVISED", None)
        p = subprocess.run([sys.executable, "-I", str(HERE / "gui_smoke.py"), name], env=env,
                           capture_output=True, text=True, timeout=timeout)
    out = p.stdout + p.stderr
    result = [l for l in out.splitlines() if l.startswith("RESULT")]
    return (result[-1] if result else "RESULT fail: no result line\n" + out[-2000:]), out


def _make_test(name):
    def t():
        res, out = run_scenario(name)
        assert res == "RESULT ok", res
    t.__name__ = f"test_gui_{name}"
    return t


for _n in SCENARIO_NAMES:
    globals()[f"test_gui_{_n}"] = _make_test(_n)


if __name__ == "__main__":
    fails = 0
    for n in SCENARIO_NAMES:
        res, _ = run_scenario(n)
        ok = res == "RESULT ok"
        fails += not ok
        print(("PASS" if ok else "FAIL") + f" gui:{n}" + ("" if ok else f"\n{res}"))
    print(f"\n{fails} failure(s)")
    sys.exit(1 if fails else 0)
