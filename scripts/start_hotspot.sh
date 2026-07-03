#!/usr/bin/env bash
# Spectroo v3 — start WiFi hotspot via NetworkManager
# Called by boot_detect.sh in web mode before launching the Python server.
# Reads SSID, password, and interface from config.toml via a Python one-liner.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG="$PROJECT_DIR/config.toml"
VENV="$PROJECT_DIR/.venv"

source "$VENV/bin/activate"

# Read hotspot config from config.toml
SSID=$(python -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['hotspot']['ssid'])")
PASSWORD=$(python -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['hotspot']['password'])")
INTERFACE=$(python -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['hotspot']['interface'])")

echo "[spectroo] Starting hotspot: SSID=$SSID on $INTERFACE"

# Delete existing hotspot connection if present (avoid nmcli duplicate error)
nmcli connection delete "spectroo-hotspot" 2>/dev/null || true

# Create and activate hotspot
nmcli connection add \
    type wifi \
    ifname "$INTERFACE" \
    con-name "spectroo-hotspot" \
    autoconnect no \
    ssid "$SSID" \
    -- \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASSWORD" \
    ipv4.method shared \
    ipv6.method disabled

nmcli connection up "spectroo-hotspot"

echo "[spectroo] Hotspot active on $INTERFACE"
