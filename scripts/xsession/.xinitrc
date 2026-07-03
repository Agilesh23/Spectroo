#!/bin/sh
# Spectroo v3 — X11 kiosk session startup
# Launched by startx in desktop mode

# Disable screen saver, blanking, DPMS
xset s off
xset -dpms
xset s noblank

# Start Openbox window manager (no panel, no taskbar)
openbox --sm-disable &

# Hide cursor immediately using unclutter-xfixes
# (unclutter-xfixes package must be installed: sudo apt install unclutter-xfixes)
unclutter -idle 0 &

# Activate virtualenv
if [ -f .venv/bin/activate ]; then
    . .venv/bin/activate
fi

# Exec app — X session lifetime = app lifetime
exec python main.py --mode desktop
