#!/bin/bash
# -----------------------------------------------------------------------------
# Install the 2PAC GUI launchers. All of them start scripts/run_supervised.sh, which restarts the GUI after a
# crash (a normal window close stops it).
#   - application menu entry  ~/.local/share/applications/2pac_gui.desktop
#   - desktop shortcut        ~/Desktop/2pac_gui.desktop
#   - login autostart         ~/.config/autostart/2pac_gui.desktop   (skip with --no-autostart)
# Only one GUI can run at a time (lock in ~/.2pac/gui.lock), so autostart + a manual click is harmless.
# -----------------------------------------------------------------------------
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd )"
ICON_PATH="$PROJECT_DIR/assets/adr_gui_icon.png"
[ ! -f "$ICON_PATH" ] && ICON_PATH="$PROJECT_DIR/adr_gui_icon.png"
LAUNCHER_PATH="$PROJECT_DIR/scripts/run_supervised.sh"
AUTOSTART=1
[ "$1" = "--no-autostart" ] && AUTOSTART=0

chmod +x "$LAUNCHER_PATH" "$PROJECT_DIR/launch_gui.sh"

entry() {
cat <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=2pac gui
Comment=Hardware Control & Telemetry GUI for 2PAC ADR (auto-restarts after a crash)
Exec=$LAUNCHER_PATH
Path=$PROJECT_DIR
Icon=$ICON_PATH
Terminal=false
StartupWMClass=2pac_gui
StartupNotify=true
Categories=Utility;Science;
$1
EOF
}

mkdir -p "$HOME/.local/share/applications"
entry "" > "$HOME/.local/share/applications/2pac_gui.desktop"
chmod +x "$HOME/.local/share/applications/2pac_gui.desktop"
echo "Menu entry:       $HOME/.local/share/applications/2pac_gui.desktop"

if [ -d "$HOME/Desktop" ]; then
    entry "" > "$HOME/Desktop/2pac_gui.desktop"
    chmod +x "$HOME/Desktop/2pac_gui.desktop"
    command -v gio &> /dev/null && gio set "$HOME/Desktop/2pac_gui.desktop" metadata::trusted true 2>/dev/null || true
    echo "Desktop shortcut: $HOME/Desktop/2pac_gui.desktop"
fi

if [ $AUTOSTART -eq 1 ]; then
    mkdir -p "$HOME/.config/autostart"
    entry "X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=20" > "$HOME/.config/autostart/2pac_gui.desktop"
    echo "Login autostart:  $HOME/.config/autostart/2pac_gui.desktop"
else
    rm -f "$HOME/.config/autostart/2pac_gui.desktop"
    echo "Login autostart:  removed"
fi

command -v update-desktop-database &> /dev/null && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Done."
