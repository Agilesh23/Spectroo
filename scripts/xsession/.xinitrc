#!/bin/sh
# Spectroo v3 — X11 kiosk session startup
# Launched by startx in desktop mode

# Determine project root if not already exported
if [ -z "$PROJECT_DIR" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
fi
cd "$PROJECT_DIR"

# Disable screen saver, blanking, DPMS
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true

# Start Openbox window manager (no panel, no taskbar)
openbox --sm-disable &

# Activate virtualenv
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    . "$PROJECT_DIR/.venv/bin/activate"
fi

# Exec app — X session lifetime = app lifetime
exec python "$PROJECT_DIR/main.py" --mode desktop

