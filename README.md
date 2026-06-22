# Spectroo v3

**A Raspberry Pi–powered optical spectrometer application** that turns an ArduCAM camera, a diffraction grating spectroscope, and a Raspberry Pi 4B into a fully calibrated, browsable spectral measurement instrument.

Spectroo v3 merges the best of its two predecessors — v1's pixel-perfect PyQt5 desktop UI and v2's config-driven dual-mode deployment — into a single, polished end-user product.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Dual-mode boot** | Automatically detects whether a display is connected. Launches as a **desktop app** (PyQt5) or a **Wi-Fi hotspot + web server** (FastAPI). |
| **Real-time spectrum** | Live camera capture → greyscale → tilt correction → band extraction → dark subtraction → Savitzky-Golay smoothing → baseline subtraction → peak detection — all in a single configurable pipeline. |
| **Custom QPainter rendering** | No matplotlib. The entire spectrum visualization (gradient fills, peak annotations, zoom/pan, inspect overlay) is drawn with `QPainter` for maximum performance. |
| **Polynomial calibration** | Adaptive-degree polynomial fit (pixel → wavelength) with RMS error tracking. Calibrate once in developer mode, lock the coefficients in `config.toml`, and never recalibrate. |
| **Spectrum history** | Every saved spectrum is stored in SQLite with a PNG thumbnail, and can be exported as CSV, JSON, or full-size annotated PNG. |
| **Developer mode** | Hidden `Ctrl+Shift+D` shortcut or `--dev` CLI flag unlocks live calibration, camera preview, and config editing tools. |
| **Zero external services** | Runs entirely offline. In web mode, the Pi creates its own hotspot (`spectroo.local`) — no router or internet required. |

---

## 🏗️ Architecture

```
spectroo_v3/
├── config.toml                     # Single source of truth for all parameters
├── main.py                         # Entry point (auto-detect / --mode / --dev)
├── scripts/                        # Shell scripts & systemd units
├── spectroo/
│   ├── core/                       # Models, calibration, config, exceptions
│   ├── camera/                     # PiCameraFrameSource + MockFrameSource
│   ├── dsp/                        # Pipeline, collapse, corrections, filters, peaks
│   ├── storage/                    # SQLite DB + CSV/JSON/PNG export
│   ├── ui/                         # PyQt5 desktop interface
│   │   ├── main_window.py
│   │   ├── plot_widget.py          # QPainter spectrum canvas
│   │   ├── control_panel.py
│   │   ├── history_panel.py
│   │   └── dev/                    # Developer-only calibration & preview tools
│   ├── web/                        # FastAPI + vanilla JS frontend
│   │   ├── app.py
│   │   ├── routes.py / ws.py
│   │   └── static/                 # index.html, history.html, dev.html
│   └── system/                     # Boot detection, shutdown handler
└── tests/                          # 115 unit & integration tests
```

Desktop and web modes are thin shells over **one shared core** — the same camera source, the same DSP pipeline, the same SQLite history, and the same `config.toml`.

---

## 🛠️ Hardware

| Component | Spec |
|---|---|
| Board | Raspberry Pi 4 Model B |
| Camera | ArduCAM B0035 (OV5647 + IR filter), CSI ribbon |
| Lens | M12, 12 mm focal length, f/1.2 aperture |
| Spectroscope | Handheld diffraction grating gemological spectroscope |
| Resolution | 2592 × 200 (cropped from 2592 × 1944) |
| Display | HDMI or DSI touchscreen (auto-detected at boot) |

---

## 🚀 Getting Started

### Prerequisites

- Python ≥ 3.11
- `picamera2` (Linux/Pi only — automatically skipped on Windows/macOS)
- PyQt5 ≥ 5.15

### Installation

```bash
# Clone the repository
git clone https://github.com/Agilesh23/Spectroo.git
cd Spectroo

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# Install in editable mode
pip install -e .
```

### Running

```bash
# Auto-detect mode (desktop if display found, web otherwise)
python main.py

# Force a specific mode
python main.py --mode desktop
python main.py --mode web

# Enable developer tools
python main.py --dev
```

### Running on Windows (development)

On Windows, the camera is unavailable so a `MockFrameSource` generates synthetic spectra automatically. All UI, DSP, storage, and calibration logic works identically.

---

## 🧪 Testing

```bash
# Run the full test suite (115 tests)
pytest

# Run a specific module
pytest tests/test_dev_calibration.py -v
pytest tests/test_dsp.py -v
pytest tests/test_storage.py -v
```

All tests run headlessly using `QT_QPA_PLATFORM=offscreen`.

---

## ⚙️ Configuration

All runtime parameters live in a single [`config.toml`](config.toml):

| Section | Purpose |
|---|---|
| `[camera]` | Resolution, exposure, frame stacking |
| `[optics]` | Tilt angle, flip, center row (locked after startup calibration) |
| `[dsp]` | Band height, Savitzky-Golay window, baseline method |
| `[calibration]` | Polynomial degree, min points, coefficients |
| `[peaks]` | Prominence thresholds, display caps |
| `[boot]` | Auto/desktop/web mode, warm-up delay |
| `[hotspot]` | SSID, password, channel, gateway |
| `[web]` | Ports, dev password |
| `[history]` | SQLite path, max entries |

---

## 📡 Web API (Hotspot Mode)

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Live spectrum dashboard |
| `/history` | GET | Browsable history page |
| `/api/spectrum` | GET | Current spectrum as JSON |
| `/api/history` | GET | List saved records |
| `/api/history/{id}` | GET | Single record detail |
| `/api/export/{id}/{fmt}` | GET | Download CSV / JSON / PNG |
| `/ws/spectrum` | WS | Real-time spectrum stream |

---

## 🔬 DSP Pipeline

Each frame passes through these stages in order:

1. **Average** — stack `N` frames to float32
2. **Greyscale** — luminance conversion (0.299R + 0.587G + 0.114B)
3. **Tilt correction** — `scipy.ndimage.rotate` with `reshape=False`
4. **Band extraction** — collapse rows around locked `center_y`
5. **Flip** — reverse array if `flip_spectrum` is set
6. **Dark subtraction** — subtract stored 1D dark frame
7. **Savitzky-Golay smoothing** — configurable window and polynomial order
8. **Baseline subtraction** — minimum filter + SG method
9. **Flat-field correction** — spectral response normalization
10. **Wavelength mapping** — polynomial calibration or grating LUT
11. **Peak detection** — `scipy.signal.find_peaks` with prominence ranking

---

## 📜 License

This project is developed for educational and research purposes.

---

## 👤 Author

**Agilesh** — [GitHub](https://github.com/Agilesh23)
