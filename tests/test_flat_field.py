import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import json
import pytest
import numpy as np
from PyQt5.QtWidgets import QApplication
from spectroo.camera.source import MockFrameSource
from spectroo.ui.workers import FlatFieldWorker
from spectroo.ui.main_window import SpectrooMainWindow

@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

def test_flat_field_worker_normal_capture(tmp_path):
    # Setup paths
    dark_path = tmp_path / "dark_frame.npy"
    flat_path = tmp_path / "response_flat.json"

    # Save a 2D dummy dark frame (height 20, width 40)
    # The MockFrameSource will produce frames of (height, width, 3)
    # Let's use resolution (40, 20) -> frame shape (20, 40, 3)
    dummy_dark = np.ones((20, 40), dtype=np.float32) * 5.0
    np.save(str(dark_path), dummy_dark)

    config = {
        "camera": {"exposure_us": 100000, "frame_stack": 2, "resolution": [40, 20]},
        "optics": {"tilt_angle_deg": 0.0, "center_y": 10, "flip_spectrum": False},
        "dsp": {"band_half_height": 2},
        "storage": {
            "dark_frame_path": str(dark_path),
            "flat_field_path": str(flat_path)
        }
    }

    # Custom mock source to return deterministic frames
    fs = MockFrameSource(resolution=(40, 20), seed=42)

    worker = FlatFieldWorker(config, fs)
    
    # Track signal emission
    messages = []
    worker.finished.connect(messages.append)
    
    # Run synchronously
    worker.run()
    
    assert len(messages) == 1
    assert "saved successfully" in messages[0]
    assert flat_path.exists()

    with open(flat_path, "r") as f:
        flat_curve = json.load(f)
    
    assert isinstance(flat_curve, list)
    assert len(flat_curve) == 40
    # Mean of normalized profile should be 1.0
    assert np.isclose(np.mean(flat_curve), 1.0)


def test_flat_field_worker_missing_dark_frame_fallback(tmp_path):
    flat_path = tmp_path / "response_flat.json"
    config = {
        "camera": {"exposure_us": 100000, "frame_stack": 2, "resolution": [40, 20]},
        "optics": {"tilt_angle_deg": 0.0, "center_y": 10, "flip_spectrum": False},
        "dsp": {"band_half_height": 2},
        "storage": {
            "dark_frame_path": str(tmp_path / "does_not_exist.npy"),
            "flat_field_path": str(flat_path)
        }
    }

    fs = MockFrameSource(resolution=(40, 20), seed=42)
    worker = FlatFieldWorker(config, fs)
    
    messages = []
    worker.finished.connect(messages.append)
    worker.run()
    
    assert len(messages) == 1
    assert "saved successfully" in messages[0]
    assert flat_path.exists()


def test_flat_field_worker_zero_frame_guard(tmp_path, monkeypatch):
    flat_path = tmp_path / "response_flat.json"
    config = {
        "camera": {"exposure_us": 100000, "frame_stack": 2, "resolution": [40, 20]},
        "optics": {"tilt_angle_deg": 0.0, "center_y": 10, "flip_spectrum": False},
        "dsp": {"band_half_height": 2},
        "storage": {
            "dark_frame_path": "",
            "flat_field_path": str(flat_path)
        }
    }

    fs = MockFrameSource(resolution=(40, 20))
    # Mock capture_frame to return all zeros
    monkeypatch.setattr(fs, "capture_frame", lambda: np.zeros((20, 40, 3), dtype=np.uint8))

    worker = FlatFieldWorker(config, fs)
    
    messages = []
    worker.finished.connect(messages.append)
    worker.run()
    
    assert len(messages) == 1
    assert "Cannot normalize flat-field: mean intensity is zero or negative." in messages[0]
    assert not flat_path.exists()


def test_flat_field_worker_clamping_behavior(tmp_path, monkeypatch):
    flat_path = tmp_path / "response_flat.json"
    config = {
        "camera": {"exposure_us": 100000, "frame_stack": 1, "resolution": [40, 20]},
        "optics": {"tilt_angle_deg": 0.0, "center_y": 10, "flip_spectrum": False},
        "dsp": {"band_half_height": 2},
        "storage": {
            "dark_frame_path": "",
            "flat_field_path": str(flat_path)
        }
    }

    fs = MockFrameSource(resolution=(40, 20))
    # We want a frame where one pixel is zero and others are large, so the mean is large.
    # The mean of band will be e.g. 100, so 5% of mean is 5.
    # The zero pixel should be clamped to 5.
    frame = np.ones((20, 40, 3), dtype=np.uint8) * 100
    # Set column 0 to 0 (which is very low)
    frame[:, 0, :] = 0
    monkeypatch.setattr(fs, "capture_frame", lambda: frame)

    worker = FlatFieldWorker(config, fs)
    messages = []
    worker.finished.connect(messages.append)
    worker.run()

    assert flat_path.exists()
    with open(flat_path, "r") as f:
        flat_curve = json.load(f)

    # Clamping floor should be mean * 0.05.
    # Since all other columns are 100, column 0 is clamped to floor.
    # Let's verify that no element in flat_curve is extremely small/zero.
    assert min(flat_curve) > 0.01
    # Check that it's around 0.05 of the normalized values
    assert np.isclose(min(flat_curve), 0.05, rtol=1e-2)


def test_flat_field_shortcut_dev_mode_gated():
    config = {
        "camera": {"exposure_us": 50000, "n_frames": 4},
        "dsp": {"baseline_enabled": True},
        "storage": {"dark_frame_path": "dark_frame.npy"},
        "calibration": {},
    }
    
    # 1. Dev mode True -> Shortcut exists
    win_dev = SpectrooMainWindow(config, dev=True)
    assert hasattr(win_dev, "flat_field_shortcut")
    assert win_dev.flat_field_shortcut is not None

    # 2. Dev mode False -> Shortcut does not exist
    win_prod = SpectrooMainWindow(config, dev=False)
    assert not hasattr(win_prod, "flat_field_shortcut")
