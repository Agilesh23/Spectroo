#!/usr/bin/env bash
# Spectroo v3 — Automated Uninstaller
# Stops and purges system configurations, NetworkManager rules, mDNS hosts, and (optionally) deletes the project files.
#
# Usage:
#   sudo ./scripts/uninstall.sh [--force]
#
# Options:
#   --force  Bypasses the confirmation prompt before deleting the project directory.

set -euo pipefail

# 1. Require root/sudo privileges
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo &> /dev/null; then
        SUDO="sudo"
    else
        echo "ERROR: Root privileges or 'sudo' required to execute this script." >&2
        exit 1
    fi
fi

# 2. Determine PROJECT_DIR (script parent parent folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_PATH="$PROJECT_DIR/config.toml"

echo "=== Spectroo v3 Pi Uninstaller ==="
echo "Project directory: $PROJECT_DIR"
echo ""

# Parse arguments
FORCE=false
for arg in "$@"; do
    if [ "$arg" == "--force" ]; then
        FORCE=true
    fi
done

# 3. Stop and disable systemd services
echo "Stopping and disabling systemd services..."
SERVICES=("spectroo.service" "spectroo-web.service" "spectroo-desktop.service")

for SVC in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$SVC" 2>/dev/null || systemctl is-enabled --quiet "$SVC" 2>/dev/null; then
        $SUDO systemctl stop "$SVC" || true
        $SUDO systemctl disable "$SVC" || true
        echo "  Stopped and disabled $SVC."
    fi
    SVC_FILE="/etc/systemd/system/$SVC"
    if [ -f "$SVC_FILE" ] || [ -L "$SVC_FILE" ]; then
        $SUDO rm -f "$SVC_FILE"
        echo "  Removed service file/link at $SVC_FILE."
    fi
done
$SUDO systemctl daemon-reload

# 4. Remove PolKit rule
echo "Removing PolKit rules..."
POLKIT_FILE="/etc/polkit-1/rules.d/10-spectroo-network.rules"
if [ -f "$POLKIT_FILE" ]; then
    $SUDO rm -f "$POLKIT_FILE"
    if systemctl is-active --quiet polkit 2>/dev/null; then
        $SUDO systemctl restart polkit || true
    fi
    echo "  Removed PolKit rules file at $POLKIT_FILE."
else
    echo "  PolKit network rules file not found."
fi

# 5. Delete NetworkManager connection profile
echo "Deleting NetworkManager connection..."
if nmcli connection show "spectroo-hotspot" &>/dev/null; then
    $SUDO nmcli connection delete "spectroo-hotspot" || true
    echo "  Connection profile 'spectroo-hotspot' deleted."
else
    echo "  Connection profile 'spectroo-hotspot' not found."
fi

# 6. Extract config parameters and clean up networking redirection BEFORE directory deletion
if [ -f "$CONFIG_PATH" ]; then
    echo "Reading network settings from config.toml..."
    
    HOTSPOT_IFACE=$(python3 -c "
import tomllib
with open('$CONFIG_PATH', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('hotspot', {}).get('interface', 'wlan0'))
" 2>/dev/null || echo "wlan0")

    GATEWAY_IP=$(python3 -c "
import tomllib
with open('$CONFIG_PATH', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('hotspot', {}).get('gateway_ip', '10.42.0.1'))
" 2>/dev/null || echo "10.42.0.1")

    MDNS_HOSTNAME=$(python3 -c "
import tomllib
with open('$CONFIG_PATH', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('hotspot', {}).get('mdns_hostname', 'spectroo.local'))
" 2>/dev/null || echo "spectroo.local")

    PUBLIC_PORT=$(python3 -c "
import tomllib
with open('$CONFIG_PATH', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('web', {}).get('public_port', 80))
" 2>/dev/null || echo 80)

    INTERNAL_PORT=$(python3 -c "
import tomllib
with open('$CONFIG_PATH', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('web', {}).get('internal_port', 8000))
" 2>/dev/null || echo 8000)

    # 6a. Remove Avahi Static Hosts entry
    echo "Removing static mDNS hosts..."
    AVAHI_HOSTS="/etc/avahi/hosts"
    if [ -f "$AVAHI_HOSTS" ]; then
        if grep -q "$MDNS_HOSTNAME" "$AVAHI_HOSTS"; then
            $SUDO sed -i "/$MDNS_HOSTNAME/d" "$AVAHI_HOSTS"
            if systemctl is-active --quiet avahi-daemon 2>/dev/null; then
                $SUDO systemctl restart avahi-daemon || true
            fi
            echo "  Removed mDNS static host entry '$GATEWAY_IP $MDNS_HOSTNAME' from $AVAHI_HOSTS."
        else
            echo "  mDNS host entry for '$MDNS_HOSTNAME' not found."
        fi
    fi

    # 6b. Remove NAT redirection rule idempotently
    echo "Removing port redirection rule..."
    if $SUDO iptables -t nat -C PREROUTING -i "$HOTSPOT_IFACE" -p tcp --dport "$PUBLIC_PORT" -j REDIRECT --to-port "$INTERNAL_PORT" &>/dev/null; then
        $SUDO iptables -t nat -D PREROUTING -i "$HOTSPOT_IFACE" -p tcp --dport "$PUBLIC_PORT" -j REDIRECT --to-port "$INTERNAL_PORT"
        echo "  Removed iptables REDIRECT rule: $PUBLIC_PORT -> $INTERNAL_PORT on $HOTSPOT_IFACE."
        if command -v netfilter-persistent &> /dev/null; then
            $SUDO netfilter-persistent save || true
        fi
    else
        echo "  iptables redirection rule not found."
    fi
else
    echo "WARNING: config.toml not found at $CONFIG_PATH. Skipping config-dependent network removals."
fi

# 7. Prompt for confirmation before deleting project directory
CONFIRM="yes"
if [ "$FORCE" = "false" ]; then
    echo ""
    echo "⚠️  WARNING: This will permanently delete the project directory at:"
    echo "   $PROJECT_DIR"
    echo "including all calibration profiles, raw records database, and config.toml."
    read -p "Type 'yes' to confirm deletion: " USER_INPUT
    CONFIRM="$USER_INPUT"
fi

DIR_DELETED=false
if [ "$CONFIRM" = "yes" ]; then
    echo "Deleting project directory at $PROJECT_DIR..."
    # Jump out of the directory to be safe before executing removal
    cd /tmp
    $SUDO rm -rf "$PROJECT_DIR"
    DIR_DELETED=true
else
    echo "Skipping project directory deletion."
fi

# 8. Print Final Summary
echo ""
echo "=== Uninstall Completed ==="
if [ "$DIR_DELETED" = "true" ]; then
    echo "  [OK] Project directory at $PROJECT_DIR was permanently deleted."
else
    echo "  [SKIP] Project directory was retained."
fi
echo "  [OK] System services, PolKit rules, NM connection, and routing configurations cleared."
