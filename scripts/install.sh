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
        
        # Desktop kiosk dependencies (Openbox/X11)
        "xserver-xorg"
        "xinit"
        "openbox"
        "unclutter-xfixes"
        
        # Web mode NetworkManager dependency
        "network-manager"
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
    python3 -m venv "$VENV_DIR"
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
    
    if [ ! -f "$SERVICE_SOURCE" ]; then
        echo "ERROR: Service file not found at $SERVICE_SOURCE" >&2
        exit 1
    fi
    
    if [ -n "$SUDO" ] || [ "$EUID" -eq 0 ]; then
        echo "Copying service file to $SERVICE_DEST..."
        $SUDO cp "$SERVICE_SOURCE" "$SERVICE_DEST"
        
        # Reload daemon and enable service
        echo "Registering systemd service..."
        $SUDO systemctl daemon-reload
        $SUDO systemctl enable spectroo.service
        echo "Systemd service 'spectroo.service' enabled successfully."
        
        # Check matching username / path
        CURRENT_USER=$(whoami)
        if [ "$CURRENT_USER" != "spectroo" ] || [ "$PROJECT_ROOT" != "/home/spectroo/spectroo_v3" ]; then
            echo "------------------------------------------------------------------"
            echo "WARNING: Current user is '$CURRENT_USER' and install path is '$PROJECT_ROOT'."
            echo "The systemd service defaults assume user 'spectroo' and path '/home/spectroo/spectroo_v3'."
            echo "Please manually edit $SERVICE_DEST if you need to adjust these."
            echo "------------------------------------------------------------------"
        fi
    else
        echo "ERROR: Root privileges (sudo) required to enable systemd boot service." >&2
        exit 1
    fi
else
    echo "Skipping systemd boot service installation. (Run with --enable-boot-service to enable)."
fi

# 6. Print Final Instructions
echo "=== Installation Completed Successfully ==="
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
