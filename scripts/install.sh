#!/usr/bin/env bash
# Spectroo v3 — Automated Raspberry Pi Installer
# Sets up the virtual environment, system dependencies, and (optionally) systemd service.
#
# Usage:
#   ./install.sh [--enable-boot-service] [--skip-apt]

set -euo pipefail

# Parse arguments
ENABLE_BOOT=false
SKIP_APT=false
for arg in "$@"; do
    if [ "$arg" == "--enable-boot-service" ]; then
        ENABLE_BOOT=true
    elif [ "$arg" == "--skip-apt" ]; then
        SKIP_APT=true
    fi
done

# Ensure we are in the correct directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=== Spectroo v3 Pi Installer ==="
echo "Project root: $PROJECT_ROOT"

# 1. Verify Python Version (>= 3.11)
MIN_PYTHON_VERSION="3.11"
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 command not found. Please install Python >= $MIN_PYTHON_VERSION." >&2
    exit 1
fi

IS_COMPATIBLE=$(python3 -c "import sys; print(sys.version_info >= (3, 11))")
if [ "$IS_COMPATIBLE" != "True" ]; then
    PYTHON_VER=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
    echo "ERROR: Python version is $PYTHON_VER. Spectroo v3 requires Python >= $MIN_PYTHON_VERSION." >&2
    exit 1
fi
echo "Python version check passed."

# 2. Install System Dependencies (requires root privileges)
if [ "$SKIP_APT" == "true" ]; then
    echo "Skipping system package installation as requested by --skip-apt."
elif command -v apt-get &> /dev/null; then
    echo "Installing system package dependencies..."
    SYSTEM_PACKAGES=(
        # Python tools
        "python3-pip"
        "python3-venv"
        "python3-dev"
        "python3-pyqt5"
        "python3-picamera2"
        
        # Desktop kiosk dependencies (Openbox/X11)
        "xserver-xorg"
        "xinit"
        "openbox"
        "unclutter-xfixes"
        "xterm"
        
        # Web mode NetworkManager and discovery dependencies
        "network-manager"
        "avahi-daemon"
        "iptables"
        "iptables-persistent"
        "dnsmasq"
    )
    
    SUDO=""
    if [ "$EUID" -ne 0 ]; then
        if command -v sudo &> /dev/null; then
            SUDO="sudo"
        else
            echo "ERROR: Root privileges or 'sudo' required to install system packages. Run with --skip-apt to bypass." >&2
            exit 1
        fi
    fi
    
    # Pre-seed iptables-persistent to run non-interactively without user prompts
    export DEBIAN_FRONTEND=noninteractive
    if command -v debconf-set-selections &> /dev/null; then
        echo "iptables-persistent iptables-persistent/prules2 boolean true" | $SUDO debconf-set-selections || true
        echo "iptables-persistent iptables-persistent/ip6rules2 boolean true" | $SUDO debconf-set-selections || true
    fi

    $SUDO apt-get update -y
    $SUDO apt-get install -y "${SYSTEM_PACKAGES[@]}"
else
    echo "apt-get not detected on this system. Skipping system packages."
    echo "Make sure equivalent window manager (Openbox/X11) and NetworkManager packages are installed."
fi

# 3. Create & Activate Virtual Environment
VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR..."
    python3 -m venv --system-site-packages "$VENV_DIR"
else
    echo "Virtual environment already exists at $VENV_DIR."
fi

# Activate virtualenv
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# 4. Install Python Dependencies
echo "Installing python packages in editable mode..."
pip install --upgrade pip setuptools wheel
pip install -e .

# 5. Handle Systemd Service Integration (Optional)

if [ "$ENABLE_BOOT" == "true" ]; then
    echo "Enabling boot service..."
    SERVICE_SOURCE="$SCRIPT_DIR/systemd/spectroo.service"
    SERVICE_DEST="/etc/systemd/system/spectroo.service"
    POLKIT_SOURCE="$SCRIPT_DIR/systemd/10-spectroo-network.rules"
    POLKIT_DEST="/etc/polkit-1/rules.d/10-spectroo-network.rules"
    
    if [ ! -f "$SERVICE_SOURCE" ]; then
        echo "ERROR: Service file not found at $SERVICE_SOURCE" >&2
        exit 1
    fi
    
    if [ -n "$SUDO" ] || [ "$EUID" -eq 0 ]; then
        # Dynamically determine the non-root user who invoked the install script
        INVOKING_USER=${SUDO_USER:-$(whoami)}
        echo "Generating dynamic service file for user '$INVOKING_USER' and path '$PROJECT_ROOT'..."
        
        # Create a temporary file with substituted values
        TEMP_SERVICE=$(mktemp)
        sed -e "s|User=laserquant|User=$INVOKING_USER|g" \
            -e "s|WorkingDirectory=/home/laserquant/Spectroo|WorkingDirectory=$PROJECT_ROOT|g" \
            -e "s|ExecStart=/home/laserquant/Spectroo/scripts/boot_detect.sh|ExecStart=$PROJECT_ROOT/scripts/boot_detect.sh|g" \
            "$SERVICE_SOURCE" > "$TEMP_SERVICE"
            
        echo "Copying service file to $SERVICE_DEST..."
        $SUDO cp "$TEMP_SERVICE" "$SERVICE_DEST"
        rm "$TEMP_SERVICE"
        
        # Copy PolKit rules file for NetworkManager permissions
        if [ -f "$POLKIT_SOURCE" ]; then
            echo "Generating dynamic PolKit rule for user '$INVOKING_USER'..."
            TEMP_POLKIT=$(mktemp)
            sed "s|laserquant|$INVOKING_USER|g" "$POLKIT_SOURCE" > "$TEMP_POLKIT"
            echo "Copying PolKit rule to $POLKIT_DEST..."
            $SUDO cp "$TEMP_POLKIT" "$POLKIT_DEST"
            $SUDO chmod 644 "$POLKIT_DEST"
            rm "$TEMP_POLKIT"
        else
            echo "WARNING: PolKit rules file not found at $POLKIT_SOURCE, skipping."
        fi

        # Reload daemon and enable service
        echo "Registering systemd service..."
        $SUDO systemctl daemon-reload
        $SUDO systemctl enable spectroo.service
        echo "Systemd service 'spectroo.service' enabled successfully for user '$INVOKING_USER'."
    else
        echo "ERROR: Root privileges (sudo) required to enable systemd boot service." >&2
        exit 1
    fi
else
    echo "Skipping systemd boot service installation. (Run with --enable-boot-service to enable)."
fi

# 5b. Hotspot Port Redirection & mDNS Configuration
if [ -n "$SUDO" ] || [ "$EUID" -eq 0 ]; then
    echo "Configuring hotspot port redirection and static mDNS..."

    # Extract variables from config.toml using Python's standard tomllib
    HOTSPOT_IFACE=$(python3 -c "
import tomllib
with open('config.toml', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('hotspot', {}).get('interface', 'wlan0'))
" 2>/dev/null || echo "wlan0")

    GATEWAY_IP=$(python3 -c "
import tomllib
with open('config.toml', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('hotspot', {}).get('gateway_ip', '10.42.0.1'))
" 2>/dev/null || echo "10.42.0.1")

    MDNS_HOSTNAME=$(python3 -c "
import tomllib
with open('config.toml', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('hotspot', {}).get('mdns_hostname', 'spectroo.local'))
" 2>/dev/null || echo "spectroo.local")

    PUBLIC_PORT=$(python3 -c "
import tomllib
with open('config.toml', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('web', {}).get('public_port', 80))
" 2>/dev/null || echo 80)

    INTERNAL_PORT=$(python3 -c "
import tomllib
with open('config.toml', 'rb') as f:
    cfg = tomllib.load(f)
print(cfg.get('web', {}).get('internal_port', 8000))
" 2>/dev/null || echo 8000)

    # Configure mDNS static entry in /etc/avahi/hosts
    AVAHI_HOSTS="/etc/avahi/hosts"
    AVAHI_ENTRY="$GATEWAY_IP $MDNS_HOSTNAME"
    if [ -f "$AVAHI_HOSTS" ]; then
        if ! grep -qxF "$AVAHI_ENTRY" "$AVAHI_HOSTS"; then
            echo "Adding static mDNS entry '$AVAHI_ENTRY' to $AVAHI_HOSTS"
            echo "$AVAHI_ENTRY" | $SUDO tee -a "$AVAHI_HOSTS" > /dev/null
            if systemctl is-active --quiet avahi-daemon; then
                echo "Restarting avahi-daemon to apply changes..."
                $SUDO systemctl restart avahi-daemon
            fi
        else
            echo "mDNS entry for $MDNS_HOSTNAME already exists in $AVAHI_HOSTS."
        fi
    fi

    # Apply NAT port redirection rule idempotently
    if ! $SUDO iptables -t nat -C PREROUTING -i "$HOTSPOT_IFACE" -p tcp --dport "$PUBLIC_PORT" -j REDIRECT --to-port "$INTERNAL_PORT" &>/dev/null; then
        echo "Adding iptables PREROUTING redirect rule: $PUBLIC_PORT -> $INTERNAL_PORT on $HOTSPOT_IFACE"
        $SUDO iptables -t nat -A PREROUTING -i "$HOTSPOT_IFACE" -p tcp --dport "$PUBLIC_PORT" -j REDIRECT --to-port "$INTERNAL_PORT"
    else
        echo "iptables PREROUTING redirect rule already exists."
    fi

    # Save iptables rules so they survive reboot
    if command -v netfilter-persistent &> /dev/null; then
        echo "Persisting iptables rules..."
        $SUDO netfilter-persistent save
    fi

    # Configure dnsmasq resolve entry
    DNSMASQ_CONF="/etc/dnsmasq.conf"
    DNSMASQ_ENTRY="address=/laserquant.spectroo/10.42.0.1"
    if [ -f "$DNSMASQ_CONF" ]; then
        if ! grep -qF "$DNSMASQ_ENTRY" "$DNSMASQ_CONF"; then
            echo "Adding dnsmasq entry '$DNSMASQ_ENTRY' to $DNSMASQ_CONF"
            echo "$DNSMASQ_ENTRY" | $SUDO tee -a "$DNSMASQ_CONF" > /dev/null
            echo "Restarting dnsmasq to apply changes..."
            $SUDO systemctl restart dnsmasq || true
        else
            echo "dnsmasq entry for laserquant.spectroo already exists in $DNSMASQ_CONF."
        fi
    fi
fi

# 6. Print Final Instructions
echo "=== Installation Completed Successfully ==="
echo ""
echo "Dashboard will be available at http://laserquant.spectroo (no port needed)"
echo ""
echo "To run the application manually:"
echo ""
echo "1. Activate the environment:"
echo "   source .venv/bin/activate"
echo ""
echo "2. Run PyQt5 GUI (Desktop mode):"
echo "   python main.py --mode desktop"
echo ""
echo "3. Run FastAPI Server (Web mode):"
echo "   python main.py --mode web"
echo ""
echo "Configuration files live at: config.toml"
echo "Log output matches: ~/spectroo/logs/spectroo.log"
echo ""
