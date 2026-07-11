# Spectroo v3

Spectroo v3 is a Raspberry Pi-powered optical spectrometer application that turns an ArduCAM camera, a diffraction grating spectroscope, and a Raspberry Pi 4B into a fully calibrated, browsable spectral measurement instrument. It supports real-time spectrum acquisition, digital signal processing (DSP), wavelength calibration, history storage, and comparison analysis.

---

## 📋 Prerequisites & Hardware Requirements

* **Hardware Platform:** Raspberry Pi 4 Model B (4GB or 8GB recommended).
* **OS:** Raspberry Pi OS (Debian Bookworm or later).
* **Camera Module:** ArduCAM B0035 (OV5647, 5MP sensor with IR filter) connected via CSI ribbon interface.
* **Optics & Setup:** 3D-printed alignment bench, 12mm f/1.2 M12 lens, and a handheld diffraction grating gemological spectroscope.
* **Development Mode (Fallback):** Generates synthetic spectrum bands when run on Windows, macOS, or generic Linux setups lacking physical camera drivers.

---

## ⚡ Installation on Raspberry Pi

For automated setup on a fresh Raspberry Pi OS install, run the provided install script from the repository root:

```bash
# 1. Clone the repository
git clone https://github.com/Agilesh23/Spectroo.git
cd Spectroo

# 2. Make the install script executable and run it
chmod +x scripts/install.sh
sudo ./scripts/install.sh
```

### Installation Flags
* `--enable-boot-service`: Installs and enables the `spectroo` systemd service to run the app automatically on boot.
* `--skip-apt`: Skips the installation of system packages via `apt-get` (useful for offline or customized environments).

---

## 🚀 Accessing the Device

Once installation is complete, Spectroo will run in either Desktop Kiosk mode or Web server mode:

### 🌐 Web Mode
1. Connect your device (computer, tablet, or phone) to the Spectroo Wi-Fi Access Point (refer to the `[hotspot]` section of `config.toml` for the default Wi-Fi SSID and password details).
2. Open your browser and navigate to `http://spectroo.local:8000` (or `http://10.42.0.1:8000`).
3. You will be greeted by the Spectroo web dashboard.

### 🖥️ Desktop Kiosk Mode
If a physical monitor is attached directly to the Raspberry Pi, the application will boot into a full-screen local touchscreen/kiosk interface.

---

## 📖 Basic Usage & User Guide

For detailed operating instructions, peak calibration walkthroughs, and ratio comparisons:
* **Interactive Help:** Click **Help** > **User Guide** in the application menu bar to open the comprehensive user manual directly in the app.
* **Troubleshooting:** The User Guide contains standard diagnostic pointers for flat signals, sensor saturation, and connection state errors.
