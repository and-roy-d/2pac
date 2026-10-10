#!/bin/bash
# -----------------------------------------------------------------------------
# Install 2PAC GUI Desktop Launcher
# -----------------------------------------------------------------------------
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -f "$SCRIPT_DIR/main.py" ]; then
    PROJECT_DIR="$SCRIPT_DIR"
else
    PROJECT_DIR="$( cd "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd )"
fi
ICON_PATH="$PROJECT_DIR/assets/adr_gui_icon.png"
[ ! -f "$ICON_PATH" ] && ICON_PATH="$PROJECT_DIR/adr_gui_icon.png"
LAUNCHER_PATH="$PROJECT_DIR/launch_gui.sh"

chmod +x "$LAUNCHER_PATH"

DESKTOP_ENTRY="[Desktop Entry]
Version=1.0
Type=Application
Name=2pac gui
Comment=Hardware Control & Telemetry GUI for 2PAC ADR
Exec=$LAUNCHER_PATH
Path=$PROJECT_DIR