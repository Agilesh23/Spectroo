#!/usr/bin/env bash
# Spectroo v3 — start WiFi hotspot via NetworkManager
# Called by boot_detect.sh in web mode before launching the Python server.
# Reads SSID, password, and interface from config.toml via a Python one-liner.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
mkdir -p "$PROJECT_DIR/logs"
exec > >(tee -a "$PROJECT_DIR/logs/hotspot.log") 2>&1
echo "=== start_hotspot.sh invoked at $(date -Iseconds) ==="
set -x

CONFIG="$PROJECT_DIR/config.toml"
VENV="$PROJECT_DIR/.venv"

source "$VENV/bin/activate"

# Read hotspot config from config.toml
SSID=$(python -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['hotspot']['ssid'])")
PASSWORD=$(python -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['hotspot']['password'])")
INTERFACE=$(python -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['hotspot']['interface'])")
GATEWAY_IP=$(python -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c.get('hotspot', {}).get('gateway_ip', '10.42.0.1'))")
MDNS_HOSTNAME=$(python -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c.get('hotspot', {}).get('mdns_hostname', 'spectroo.local'))")

PREV_CONN=$(nmcli -t -f NAME,DEVICE connection show --active | grep ":$INTERFACE$" | cut -d: -f1 || true)
if [[ -n "$PREV_CONN" ]]; then
    nmcli connection down "$PREV_CONN" 2>/dev/null || true
fi

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
    802-11-wireless.mode ap \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASSWORD" \
    ipv4.method shared \
    ipv6.method disabled

# Configure dnsmasq under NetworkManager shared configuration for standard DNS resolution
sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
echo "address=/$MDNS_HOSTNAME/$GATEWAY_IP" | sudo tee /etc/NetworkManager/dnsmasq-shared.d/spectroo.conf > /dev/null

if ! nmcli connection up "spectroo-hotspot"; then
    echo "[spectroo] WARNING: hotspot failed to activate, falling back to previous connection" >&2
    if [[ -n "$PREV_CONN" ]]; then
        nmcli connection up "$PREV_CONN" 2>/dev/null || true
    fi
    exit 1
fi

echo "[spectroo] Hotspot active on $INTERFACE"
