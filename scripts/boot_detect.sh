#!/usr/bin/env bash
# Spectroo v3 — boot detection wrapper.
# Called by the systemd service as ExecStart.
# Activates the venv and delegates to main.py.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_DIR/.venv"
MAIN="$PROJECT_DIR/main.py"

if [[ ! -f "$VENV/bin/activate" ]]; then
    echo "ERROR: venv not found at $VENV" >&2
    exit 1
fi

source "$VENV/bin/activate"

# Query boot mode (lightweight -- no UI, no logging, exits immediately)
BOOT_MODE=$(python "$MAIN" --detect-mode)
echo "[spectroo] Boot mode: $BOOT_MODE"

if [[ "$BOOT_MODE" == "desktop" ]]; then
    XINITRC="$SCRIPT_DIR/xsession/.xinitrc"
    echo "[spectroo] Starting X11 kiosk session..."
    # NOTE: "$@" is intentionally NOT passed after -- since everything after
    # -- goes to Xorg server as flags, not to the client script.
    exec startx "$XINITRC" -- -nocursor
else
    echo "[spectroo] Starting web server..."
    exec python "$MAIN" --mode web
fi
