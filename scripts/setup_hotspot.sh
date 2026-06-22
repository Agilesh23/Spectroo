#!/usr/bin/env bash
# Spectroo v3 — Wi-Fi hotspot setup.
# Run once during deployment (not on every boot).
# Configures hostapd + dnsmasq + Avahi + iptables redirect 80→8000.
# All values read from environment variables with documented defaults.

set -euo pipefail

SSID="${SPECTROO_SSID:-Spectroo}"
PASSPHRASE="${SPECTROO_PASS:-changeme}"
INTERFACE="${SPECTROO_IFACE:-wlan0}"
IP_ADDR="${SPECTROO_IP:-192.168.4.1}"
DHCP_RANGE="${SPECTROO_DHCP:-192.168.4.2,192.168.4.20,255.255.255.0,24h}"
WEB_PORT="${SPECTROO_PORT:-8000}"

echo "Configuring Spectroo hotspot: SSID=$SSID on $INTERFACE"

# 1. hostapd config
cat > /etc/hostapd/hostapd.conf << EOF
interface=$INTERFACE
ssid=$SSID
wpa_passphrase=$PASSPHRASE
hw_mode=g
channel=6
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

# Point hostapd at its config
sed -i 's|#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' \
    /etc/default/hostapd

# 2. dnsmasq config (append; preserve existing config)
cat >> /etc/dnsmasq.conf << EOF

# Spectroo hotspot
interface=$INTERFACE
dhcp-range=$DHCP_RANGE
address=/spectroo.local/$IP_ADDR
EOF

# 3. Static IP for the hotspot interface
cat >> /etc/dhcpcd.conf << EOF

# Spectroo static IP
interface=$INTERFACE
static ip_address=$IP_ADDR/24
nohook wpa_supplicant
EOF

# 4. iptables redirect port 80 → web server port (scoped to hotspot interface)
iptables -t nat -A PREROUTING -i "$INTERFACE" -p tcp --dport 80 \
    -j REDIRECT --to-port "$WEB_PORT"

# Persist iptables rules
if command -v netfilter-persistent &>/dev/null; then
    netfilter-persistent save
else
    echo "WARNING: netfilter-persistent not installed — iptables rules will" \
         "not survive reboot. Install with: apt install iptables-persistent"
fi

# 5. Enable and start services
systemctl unmask hostapd
systemctl enable hostapd dnsmasq
systemctl restart hostapd dnsmasq avahi-daemon

echo "Hotspot setup complete. Connect to '$SSID' and browse to" \
     "http://spectroo.local or http://$IP_ADDR"
