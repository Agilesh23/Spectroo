# Spectroo v3 — Raspberry Pi OS Fresh Install Manual

This manual provides clear, step-by-step, copy-pasteable instructions for setting up **Spectroo v3** from scratch on a fresh Raspberry Pi OS installation.

---

## 📌 1. Prerequisites

### Hardware Requirements
* **Single-Board Computer:** Raspberry Pi 4 Model B (4GB/8GB recommended) or Raspberry Pi 5.
* **Camera Module:** ArduCAM B0035 (OV5647, 5MP) or libcamera-compatible CSI camera module.
* **Optics Setup:** Diffraction grating spectroscope aligned to the camera module.

### Operating System & Software Requirements
* **OS:** Raspberry Pi OS 64-bit (Debian 12 "Bookworm" or later recommended).
* **Python Version:** Python **3.11** or higher.

---

## 🔄 2. Update System Packages

Open a terminal on your Raspberry Pi (or connect via SSH) and update the local package index and upgrade all installed packages to their latest versions:

```bash
sudo apt update && sudo apt upgrade -y
```

---

## 📦 3. Install Python & System-Level Dependencies

Spectroo relies on system-level libraries for camera interfacing (`picamera2`), desktop GUI rendering (`PyQt5`), and networking/hotspot configuration. Install all required system packages:

```bash
sudo apt install -y \
    git \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-pyqt5 \
    python3-picamera2 \
    xserver-xorg \
    xinit \
    openbox \
    unclutter-xfixes \
    xterm \
    network-manager \
    avahi-daemon \
    iptables \
    iptables-persistent \
    dnsmasq
```

### Dependency Overview
* **`python3-pip`, `python3-venv`, `python3-dev`**: Python environment management and build tools.
* **`python3-pyqt5`, `python3-picamera2`**: System-native Python bindings for desktop GUI and Raspberry Pi camera drivers.
* **`openbox`, `xserver-xorg`, `unclutter-xfixes`**: Lightweight display window manager for desktop kiosk mode.
* **`network-manager`, `avahi-daemon`, `iptables`, `dnsmasq`**: Wireless hotspot and local mDNS host discovery (`spectroo.local`).

---

## 📥 4. Clone the Repository

Clone the Spectroo repository to your home directory:

```bash
git clone https://github.com/Agilesh23/Spectroo.git
cd Spectroo
```

---

## 🐍 5. Set Up the Python Virtual Environment

Create a Python virtual environment named `.venv`.

> ⚠️ **IMPORTANT:** You **must** pass `--system-site-packages` so the virtual environment can access system-installed packages like `python3-picamera2` and `python3-pyqt5`.

```bash
# Create the virtual environment with access to system packages
python3 -m venv --system-site-packages .venv

# Activate the virtual environment
source .venv/bin/activate
```

---

## ⚡ 6. Install Python Dependencies (`requirements.txt` / `pyproject.toml`)

With the virtual environment activated, upgrade core package utilities and install the application dependencies:

```bash
# Ensure core packaging tools are up to date
pip install --upgrade pip setuptools wheel

# Option A: Install dependencies via requirements.txt
pip install -r requirements.txt

# Option B: Or install the project in editable mode via pyproject.toml
pip install -e .
```

> 🔑 **PREVENTING THE `tomli_w` MISSING MODULE ERROR:**  
> The step above installs **`tomli-w`** (`tomli_w`). `tomli_w` is required to save wavelength calibration coefficients and user configuration settings to `config.toml`.  
> Installing dependencies via `requirements.txt` or `pyproject.toml` guarantees `tomli_w` is present in your environment, resolving the `"Failed to save coefficients to config: No module named 'tomli_w'"` runtime error.

---

## 🔑 7. Set Up System Permissions & Hardware Access

To allow your user account to access USB devices, cameras, serial interfaces, and NetworkManager configurations without requiring `sudo` for every invocation:

1. **Add your user to hardware groups:**
   ```bash
   sudo usermod -aG video,dialout,render,gpio,i2c,spi $USER
   ```

2. **(Optional) Install PolKit permissions for NetworkManager:**
   If you plan to run Spectroo Web Mode or Wi-Fi Hotspot management without root:
   ```bash
   sudo cp scripts/systemd/10-spectroo-network.rules /etc/polkit-1/rules.d/
   sudo chmod 644 /etc/polkit-1/rules.d/10-spectroo-network.rules
   ```

3. **Apply group changes:**  
   Log out and back in, or run:
   ```bash
   newgrp video
   ```

---

## 🤖 8. Automated Setup Script & Boot Service (Alternative Option)

Spectroo includes an automated installer script that executes all the steps above and optionally registers a `systemd` service to launch Spectroo automatically when the Pi boots:

```bash
# Make installer executable
chmod +x scripts/install.sh

# Run installer (optional flag: --enable-boot-service)
sudo ./scripts/install.sh --enable-boot-service
```

---

## 🚀 9. Running Spectroo for the First Time

Always ensure your virtual environment is activated before launching the application manually:

```bash
source .venv/bin/activate
```

### Option A: Desktop Kiosk Mode (PyQt5 GUI)
Runs the interactive desktop GUI on a display attached to the Raspberry Pi:
```bash
python main.py --mode desktop
```

### Option B: Web Server Mode (FastAPI + WebSockets)
Runs the headless web server dashboard accessible across your local network:
```bash
python main.py --mode web
```
Access the dashboard in your web browser at:
* `http://spectroo.local:8000` (or `http://10.42.0.1:8000` when connected to hotspot)

---

## 🧪 10. Running the Test Suite

Verify that your installation is correctly configured and all modules are functioning properly by running the unit test suite:

```bash
# Ensure virtual environment is active
source .venv/bin/activate

# Run pytest
pytest
```

---

## 🛠️ 11. Troubleshooting

### Issue 1: `ModuleNotFoundError: No module named 'tomli_w'`
* **Cause:** The virtual environment was activated, but `requirements.txt` was not installed, or `tomli-w` was missed.
* **Fix:** Activate your `.venv` and run:
  ```bash
  source .venv/bin/activate
  pip install tomli-w
  ```

### Issue 2: `ModuleNotFoundError: No module named 'picamera2'` or `'PyQt5'`
* **Cause:** The virtual environment `.venv` was created without the `--system-site-packages` flag.
* **Fix:** Recreate the virtual environment with system package inheritance:
  ```bash
  deactivate 2>/dev/null || true
  rm -rf .venv
  python3 -m venv --system-site-packages .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

### Issue 3: `Permission denied` accessing `/dev/video*` or USB spectrometer devices
* **Cause:** Your user account does not have permission to access camera or serial/USB devices.
* **Fix:** Grant video and serial access to your user account and reboot:
  ```bash
  sudo usermod -aG video,dialout,render $USER
  sudo reboot
  ```

### Issue 4: How to Verify Virtual Environment is Activated Correctly
* **Check Python Binary Location:**
  ```bash
  which python
  ```
  *Expected output:* `/home/<username>/Spectroo/.venv/bin/python` (pointing inside `.venv`).
* **Check Installed Packages inside `.venv`:**
  ```bash
  pip list | grep tomli-w
  ```
  *Expected output:* `tomli-w  1.x.x`

---

## 🧹 12. Uninstalling Spectroo

If you wish to remove Spectroo and revert changes made to your system:

### Step 1: Stop and Remove Systemd Boot Service (if installed)
```bash
sudo systemctl stop spectroo.service 2>/dev/null || true
sudo systemctl disable spectroo.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/spectroo.service
sudo rm -f /etc/polkit-1/rules.d/10-spectroo-network.rules
sudo systemctl daemon-reload
```

### Step 2: Deactivate and Remove Virtual Environment
```bash
# Deactivate virtualenv if currently active
deactivate 2>/dev/null || true

# Remove the .venv folder
rm -rf .venv
```

### Step 3: Remove Cloned Repository
```bash
cd ..
rm -rf Spectroo
```

### Step 4: Revert User Permissions / Groups (Optional)
If you wish to remove your user from hardware groups created for Spectroo:
```bash
sudo gpasswd -d $USER dialout
sudo gpasswd -d $USER video
```

### Step 5: Remove System Packages Installed via `apt` (Optional)
If you want to perform a complete system cleanup of apt packages installed specifically for Spectroo:
```bash
sudo apt purge -y \
    python3-picamera2 \
    python3-pyqt5 \
    openbox \
    unclutter-xfixes \
    avahi-daemon \
    dnsmasq
sudo apt autoremove -y
```
