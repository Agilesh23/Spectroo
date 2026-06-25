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

- **Launch with Display Auto-detection (Default):**
  Auto-detects whether a physical screen is present. Launches PyQt5 GUI on screen detection, falling back to Uvicorn/FastAPI headless server otherwise:
  ```bash
  python main.py
  ```
- **Force Launch as Desktop Application (VNC mode):**
  If running headlessly on a Pi but redirecting the display over VNC:
  ```bash
  QT_QPA_PLATFORM=vnc python main.py --mode desktop
  ```
- **Force Launch as Web App & Hotspot API:**
  ```bash
  python main.py --mode web
  ```
- **Launch with Dev Mode Disabled:**
  ```bash
  python main.py --no-dev
  ```

## ⌨️ Dev Mode Keyboard Shortcuts

When developer mode is active (default is enabled, use `--no-dev` to disable), developer shortcuts are available depending on the runtime interface:

### PyQt5 Desktop GUI Shortcuts (Main Window)
- `Ctrl+Shift+D`: Opens the **Developer Calibration Window** for manually adding wavelength points and executing polynomial fits.
- `Ctrl+Shift+C`: Opens the **Live Camera Feed Preview** to display raw camera imagery, adjust exposure times, and align optical components.
- `Ctrl+Shift+F`: Captures a **Flat-field Reference** profile, saving it to `data/response_flat.json`.
- `Ctrl+Shift+Q`: Captures a **Dark-frame Reference** profile, saving it to `data/dark_frame.npy` (or path configured in `config.toml`).

### Headless Web Interface
- `Ctrl+Shift+Alt+D`: Prompts for the developer password to access the **Developer Tools & Calibration** modal. Hitting "Calibration" opens a dedicated two-panel wavelength calibration modal (`#dev-calib-modal`) with a live spectrum canvas on the left and point mapping inputs on the right. Point configurations are held in-memory during the session (no localStorage persistence), and running a successful fit applies the calibration instantly to `config.toml` on the backend. See `docs/ARCHITECTURE_DETAILED.md` Section 3 for details.
  *Note: To prevent hotkey collision and ensure clean resource releasing in browser environments, other actions (Camera Preview, Dark/Flat capture) are accessed via dedicated buttons inside the modal rather than keyboard shortcuts.*

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
- `[storage]`: Holds file path configuration for dark frame binary arrays, flat-field JSON coefficients, and persistent calibration UI states.

## ⚠️ Known Limitations

- **Platform-dependent Camera Driver:** `picamera2` is only supported on Linux/Raspberry Pi. On Windows, macOS, or generic Linux setups lacking `libcamera`, the application automatically falls back to `MockFrameSource` generating synthetic spectrum patterns.
- **Plain HTTP Web Auth:** Dev routes on the Web API (`/api/dev/*`) are protected by a password over plain HTTP, which is suitable for local hotspot use but not secure on public networks without SSL/TLS termination.
- **CLI Signal Handling:** Pressing `Ctrl+C` in the CLI during active VNC desktop runs does not always immediately terminate the PyQt event loop, requiring manual process termination in some headless setups.
