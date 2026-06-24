# Spectroo v3

Spectroo v3 is a Raspberry Pi-powered optical spectrometer application that turns an ArduCAM camera, a diffraction grating spectroscope, and a Raspberry Pi 4B into a fully calibrated, browsable spectral measurement instrument. It supports real-time spectrum acquisition, digital signal processing (DSP), custom QPainter graph rendering, wavelength calibration, history storage, and developer utilities.

## 🛠️ Hardware Requirements

- **Processor Board:** Raspberry Pi 4 Model B (4GB or 8GB recommended).
- **Camera Sensor:** ArduCAM B0035 (OV5647, 5MP sensor with IR filter) connected via CSI ribbon cable.
- **Lens:** M12 mount lens with 12 mm focal length, f/1.2 aperture.
- **Optics:** Handheld diffraction grating gemological spectroscope.
- **Physical Case:** 3D-printed alignment bench to hold the camera lens and spectroscope collinearly.

## 📥 Setup Instructions

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/Agilesh23/Spectroo.git
   cd Spectroo/spectroo_v3
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv .venv
   # On Linux/macOS:
   source .venv/bin/activate
   # On Windows:
   .venv\Scripts\activate
   ```

3. **Install Dependencies in Editable Mode:**
   ```bash
   pip install -e .
   ```

4. **Configuration File Location:**
   All configuration settings live in the `config.toml` file located in the root of the project: `spectroo_v3/config.toml`.

## 🚀 How to Launch

Spectroo v3 operates in dual-mode (Desktop GUI or Web/Hotspot API) based on hardware detection or manual override.

- **Launch as Desktop Application (VNC mode):**
  If running headlessly on a Pi but redirecting the display over VNC:
  ```bash
  QT_QPA_PLATFORM=vnc python main.py --mode desktop
  ```
- **Launch as Web App & Hotspot API:**
  ```bash
  python main.py --mode web
  ```
- **Launch with Dev Mode Enabled:**
  ```bash
  python main.py --dev
  ```

## ⌨️ Dev Mode Keyboard Shortcuts

When developer mode (`--dev`) is enabled or `_dev_mode` is set to `True` in the desktop client, the following shortcuts become active on the main window:
- `Ctrl+Shift+D`: Opens the **Developer Calibration Window** for manually adding wavelength points and executing polynomial fits.
- `Ctrl+Shift+C`: Opens the **Live Camera Feed Preview** to display raw camera imagery, adjust exposure times, and align optical components.

## ⚙️ Configuration Reference (`config.toml`)

Key sections in `config.toml`:
- `[camera]`: Controls resolution, exposure (microseconds), and frame stacking counts.
- `[optics]`: Stores physical alignment corrections (e.g., tilt angle, spectrum flip, and locked center horizontal row).
- `[dsp]`: Sets the band height for extraction, Savitzky-Golay filtering window/polyorder, and baseline subtraction method.
- `[calibration]`: Stores the polynomial coefficients, locked polynomial degree, and minimum data points required for fitting.
- `[peaks]`: Configures prominence thresholds and search constraints for peak identification.
- `[history]`: Defines the SQLite database file path and maximum record counts.
- `[web]`: Configures server ports and developer route authentication passwords.
- `[hotspot]`: Manages standalone Access Point SSID, password, channel, and gateway IP.

## ⚠️ Known Limitations

- **Platform-dependent Camera Driver:** `picamera2` is only supported on Linux/Raspberry Pi. On Windows, macOS, or generic Linux setups lacking `libcamera`, the application automatically falls back to `MockFrameSource` generating synthetic spectrum patterns.
- **Plain HTTP Web Auth:** Dev routes on the Web API (`/dev`) are protected by a password over plain HTTP, which is suitable for local hotspot use but not secure on public networks without SSL/TLS termination.
- **Flat-field Calibration Capture:** The flat-field calibration file (`response_flat.json`) must be pre-populated manually or captured using standard reference light sources, as automated reference acquisition is not fully implemented in the UI.
- **CLI Signal Handling:** Pressing `Ctrl+C` in the CLI during active VNC desktop runs does not always immediately terminate the PyQt event loop, requiring manual process termination in some headless setups.
