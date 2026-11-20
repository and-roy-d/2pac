#!/bin/bash
# -----------------------------------------------------------------------------
# Run the 2PAC GUI and restart it if it crashes or the telemetry watchdog exits it.
#
#   exit 0              operator closed the window      -> stop
#   exit 3              another GUI already running     -> stop
#   exit 143 / 130      killed with SIGTERM / Ctrl-C    -> stop
#   anything else       crash (1, 139 segfault, ...) or watchdog restart (75) -> restart after 10 s
#
# More than 5 restarts within an hour stops the loop (crash loop) and shows a desktop notification.
# After a restart the GUI re-adopts a running regulation loop by itself; cycles and ramps do NOT resume
# (a banner says what was running). Instruments keep their settings across restarts.
#
# GUI output: ~/2pac_logs/gui_stdout/gui_<date>_<time>.log ; restarts: ~/2pac_logs/gui_stdout/supervisor.log
# -----------------------------------------------------------------------------
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
LOGDIR="$HOME/2pac_logs/gui_stdout"
mkdir -p "$LOGDIR"
export PAC2_SUPERVISED=1
export PYTHONUNBUFFERED=1   # so ~/2pac_logs/gui_stdout logs are complete even after a crash

slog() { echo "$(date '+%F %T') $*" >> "$LOGDIR/supervisor.log"; }
notify() { command -v notify-send >/dev/null && notify-send -u critical "2PAC GUI" "$1"; }

restarts=()
slog "supervisor started (pid $$)"
while true; do
    LOG="$LOGDIR/gui_$(date +%F_%H%M%S).log"
    "$DIR/launch_gui.sh" > "$LOG" 2>&1 < /dev/null
    rc=$?
    slog "GUI exited with code $rc (log $LOG)"
    case $rc in
        0)        slog "normal close; supervisor stopping"; break ;;
        3)        slog "another instance is running; supervisor stopping"; break ;;
        130|143)  slog "killed by signal; supervisor stopping"; break ;;
    esac
    now=$(date +%s)
    kept=()
    for t in "${restarts[@]}"; do
        [ $((now - t)) -lt 3600 ] && kept+=("$t")
    done
    restarts=("${kept[@]}" "$now")
    if [ ${#restarts[@]} -gt 5 ]; then
        slog "more than 5 restarts in an hour; giving up"
        notify "2PAC GUI crashed more than 5 times in an hour and was NOT restarted. See $LOGDIR."
        break
    fi
    notify "2PAC GUI exited (code $rc); restarting in 10 s."
    sleep 10
done
