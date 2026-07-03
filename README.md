# Spectroo v3

Spectroo v3 is a Raspberry Pi-powered optical spectrometer application that turns an ArduCAM camera, a diffraction grating spectroscope, and a Raspberry Pi 4B into a fully calibrated, browsable spectral measurement instrument. It supports real-time spectrum acquisition, digital signal processing (DSP), custom QPainter graph rendering, wavelength calibration, history storage, and developer utilities.

---

## 📋 Prerequisites

### Operating System & Hardware
* **Hardware Platform:** Raspberry Pi 4 Model B (4GB or 8GB recommended).
* **OS:** Raspberry Pi OS (Debian Bookworm or later).
* **Camera Module:** ArduCAM B0035 (OV5647, 5MP sensor with IR filter) connected via CSI ribbon interface.
* **Optics & Setup:** 3D-printed alignment bench, 12mm f/1.2 M12 lens, and a handheld diffraction grating gemological spectroscope.
* **Development Mode (Fallback):** Generates synthetic spectrum bands when run on Windows, macOS, or generic Linux setups lacking physical camera drivers.

### System Package Dependencies
For full startup orchestration and to bypass slow, fragile compilation of `PyQt5` and `picamera2` from source on Linux, the following system packages must be installed:
* **For Core Python Environment & Display:**
  ```bash
  sudo apt-get update
  sudo apt-get install -y python3-pip python3-venv python3-dev python3-pyqt5 python3-picamera2
  ```
* **For Desktop Kiosk Mode (Openbox/X11):**
  ```bash
  sudo apt-get install -y xserver-xorg xinit openbox unclutter-xfixes
  ```
* **For Web Mode (Access Point Hotspot):**
  NetworkManager is used to auto-start the AP. Ensure `nmcli` is available (standard on Bookworm):
  ```bash
  sudo apt-get install -y network-manager
  ```

---

## ⚡ Automated Installation on Raspberry Pi

For automated setup on a fresh Raspberry Pi OS install, run the provided install script. This script validates your system environment, installs all necessary Debian system packages (X11 server, window manager, NetworkManager), creates the local virtual environment, and installs the package dependencies:

```bash
# 1. Clone the repository
git clone https://github.com/Agilesh23/Spectroo.git
cd Spectroo

# 2. Make the install script executable and run it
chmod +x scripts/install.sh
./scripts/install.sh
```

### Options
* **Enable systemd boot service:** To register and enable the spectroo systemd daemon configuration to run rootless desktop GUI kiosk mode automatically on boot, run the script with:
  ```bash
  ./scripts/install.sh --enable-boot-service
  ```

---

## 📥 Manual Installation

From a clean clone, execute the following commands in order to set up the virtual environment and install the application dependencies:

```bash
# 1. Navigate to the project root directory
cd Spectroo

# 2. Create a virtual environment
# On Linux (allows the venv to access the system PyQt5/picamera2 apt packages):
python3 -m venv --system-site-packages .venv
# On Windows/macOS:
python -m venv .venv

# 3. Activate the virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# 4. Install dependencies in editable mode
pip install -e .
```

---

## 🚀 Running the App

Spectroo v3 automatically boots based on target mode detection (presence of active X11 display session) or manually forced CLI overrides.

### 🖥️ Running in Desktop Kiosk Mode
Launches the full PyQt5 graphical desktop user interface.
```bash
python main.py --mode desktop
```
*Note: If running headlessly on a Pi but redirecting the display output over VNC, execute:*
```bash
QT_QPA_PLATFORM=vnc python main.py --mode desktop
```

### 🌐 Running in Headless Web Mode
Starts the FastAPI web backend server and (on Linux) triggers the NetworkManager hotspot auto-start.
```bash
python main.py --mode web
```

### 🔍 Additional Run Flags
* **Auto-Detection Mode (Default):** Runs auto-detection and boots the corresponding GUI or server target:
  ```bash
  python main.py
  ```
* **Disable Dev Mode Shortcuts:** Launches with production settings, disabling layout adjustments and key shortcuts:
  ```bash
  python main.py --no-dev
  ```
* **Query Boot Mode only (Lightweight):** Prints the auto-detected mode (`desktop` or `web`) and exits immediately without initializing UI or logging services:
  ```bash
  python main.py --detect-mode
  ```

---

## ⚙️ Configuration (`config.toml`)

Key parameters in `config.toml` that a new user should adjust before running:

### `[hotspot]` Section (Web Access Point credentials)
* `ssid`: The broadcast name of the Wi-Fi access point (default: `"Spectroo"`).
* `password`: The WPA2 Personal network password (default: `"spectroo123"`).
* `interface`: The wireless interface name used by NetworkManager (default: `"wlan0"`).

### `[storage]` Section (Calibration profile paths)
* `dark_frame_path`: Binary file location where the captured dark reference frame is saved (default: `"data/dark_frame.npy"`).
* `flat_field_path`: JSON file location where the captured flat-field calibration response is saved (default: `"data/response_flat.json"`).

### `[history]` Section
* `db_path`: The database path for measurement logs (default: `"data/spectroo.db"`).

### `[camera]` & `[optics]` Sections
* `resolution`: The acquisition crop resolution (default: `[2592, 200]`).
* `exposure_us`: The target integration time in microseconds.
* `center_y`: Horizontal pixel index matching the spectroscope optical center.

---

## 📁 Project Structure

```text
Spectroo/
├── config.toml             # Configuration file (camera, dsp, calibration, hotspot settings)
├── main.py                 # Main CLI application entry point
├── pyproject.toml          # Packaging metadata and setuptools specification
├── requirements.txt        # Pinned project dependencies
├── README.md               # App overview and installation manual
├── .gitignore              # Ignore patterns for builds, caches, and runtime data
├── data/                   # Calibration profiles cache and SQLite measurement history
├── docs/                   # Internal architecture and specification guides
└── scripts/                # Startup, hotspot, and system service wrappers
    ├── boot_detect.sh      # Startup auto-detection wrapper script
    ├── start_hotspot.sh    # nmcli hotspot configurator script
    ├── systemd/
    │   └── spectroo.service  # systemd target service wrapper configuration
    └── xsession/
        └── .xinitrc        # Openbox kiosk session loader
```

---

## 📚 Documentation

- [Detailed Architecture Reference](docs/ARCHITECTURE_DETAILED.md) — Technical description of the codebase, data pipelines, database schema, and test strategies.
- [System Specification (SAD)](docs/SYSTEM_SPECIFICATION.md) — Original hardware requirements, physical optics setup, and the T1–T11 hardware integration test plan.
