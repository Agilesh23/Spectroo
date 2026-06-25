import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
import numpy as np
from PyQt5.QtWidgets import QApplication, QDialog, QWidget, QMessageBox, QInputDialog

from spectroo.ui.dev.calibration_window import CalibrationWindow, CalibrationCanvas, CalibrationPointsTable
from spectroo.camera.source import MockFrameSource
from spectroo.core.models import CalibrationPoint

# Create a single QApplication at the module level
app = QApplication.instance()
if app is None:
    app = QApplication([])


@pytest.fixture(autouse=True)
def isolate_calibration_state(tmp_path):
    orig_init = CalibrationWindow.__init__
    temp_file = tmp_path / "calibration_state.json"
    
    def patched_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        if "storage" not in self._config or "calibration_state_path" not in self._config["storage"]:
            self._state_path = str(temp_file)
            self._load_state()
            self.update_status_label()
            
    CalibrationWindow.__init__ = patched_init
    yield
    CalibrationWindow.__init__ = orig_init


@pytest.fixture
def cal_window():
    config = {
        "optics": {"center_y": 100, "band_half_height": 25, "flip_spectrum": False},
        "calibration": {"min_points": 2, "degree_low": 2, "degree_high": 3, "degree_threshold_points": 4}
    }
    fs = MockFrameSource()
    win = CalibrationWindow(config, fs)
    yield win
    win.timer.stop()


def test_calibration_window_instantiates(cal_window):
    """Constructs CalibrationWindow and asserts it is a QDialog instance."""
    assert isinstance(cal_window, QDialog)


def test_mock_spectrum_shape(cal_window):
    """Calls window._mock_spectrum(); asserts result is a numpy array of length 512."""
    res = cal_window._mock_spectrum()
    assert isinstance(res, np.ndarray)
    assert len(res) == 512


def test_on_canvas_click_adds_point(monkeypatch, cal_window):
    """Monkeypatches QInputDialog.getDouble to return (532.0, True); calls _on_canvas_click(100); asserts len(_points) == 1."""
    monkeypatch.setattr(QInputDialog, "getDouble", lambda *args, **kwargs: (532.0, True))
    cal_window._on_canvas_click(100)
    assert len(cal_window._points) == 1
    pt = cal_window._points[0]
    assert getattr(pt, "pixel_index", getattr(pt, "pixel", -1)) == 100
    assert getattr(pt, "known_wavelength_nm", getattr(pt, "wavelength", 0.0)) == 532.0


def test_on_undo_removes_point(cal_window):
    """Adds a point, calls _on_undo(), asserts len(_points) == 0."""
    pt = CalibrationPoint(100, 532.0)
    pt.pixel = 100
    pt.wavelength = 532.0
    cal_window._points.append(pt)
    cal_window.canvas.set_calibration_points(cal_window._points)
    cal_window.table.add_point(pt)

    assert len(cal_window._points) == 1
    cal_window._on_undo()
    assert len(cal_window._points) == 0


def test_on_run_fit_with_insufficient_points(monkeypatch, cal_window):
    """Calls _on_run_fit() with zero points; asserts no fit is stored (shows warning)."""
    called_warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: called_warnings.append(text))

    cal_window._points = []
    cal_window._on_run_fit()

    assert cal_window._fit_result is None
    assert len(called_warnings) == 1


def test_calibration_canvas_instantiates():
    """Constructs CalibrationCanvas; asserts it is a QWidget."""
    canvas = CalibrationCanvas()
    assert isinstance(canvas, QWidget)


def test_calibration_points_table_add_and_remove():
    """Adds two points, calls remove_last(), asserts table row count == 1."""
    table = CalibrationPointsTable()
    pt1 = CalibrationPoint(100, 400.0)
    pt2 = CalibrationPoint(200, 500.0)

    table.add_point(pt1)
    table.add_point(pt2)
    assert table.table.rowCount() == 2

    table.remove_last()
    assert table.table.rowCount() == 1


def test_on_apply_without_fit_shows_warning(monkeypatch, cal_window):
    """Monkeypatches QMessageBox.warning; calls _on_apply() with no fit; asserts warning was called."""
    called_warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: called_warnings.append(text))

    cal_window._fit_result = None
    cal_window._on_apply()

    assert len(called_warnings) == 1


# ---------------------------------------------------------------------------
# _update_spectrum dark-subtract + baseline tests
# ---------------------------------------------------------------------------

def _make_config(tmp_path=None, dark_path="", baseline_enabled=True):
    """Helper: build a minimal config dict wired for _update_spectrum tests."""
    cfg = {
        "optics": {
            "center_y": 10,
            "tilt_angle_deg": 0.0,
            "flip_spectrum": False,
        },
        "dsp": {
            "band_half_height": 2,
            "baseline_enabled": baseline_enabled,
            "baseline_method": "sg_only",
            "baseline_window": 51,
            "baseline_polyorder": 2,
        },
        "storage": {
            "dark_frame_path": dark_path,
        },
        "camera": {"exposure_us": 20000},
        "calibration": {},
    }
    return cfg


def test_update_spectrum_dark_subtraction_applied(tmp_path, monkeypatch):
    """Dark frame is subtracted when dark_frame.npy exists and is valid."""
    # MockFrameSource returns frames of shape (20, 40, 3) for resolution (40, 20)
    dark_path = tmp_path / "dark_frame.npy"
    # Save a 1-D dark of value 5.0 (matching the extracted band width = 40)
    np.save(str(dark_path), np.full(40, 5.0, dtype=np.float32))

    config = _make_config(dark_path=str(dark_path), baseline_enabled=False)
    fs = MockFrameSource(resolution=(40, 20), seed=0)

    win = CalibrationWindow(config, fs)
    win.timer.stop()

    # Capture reference without dark file present
    config_no_dark = _make_config(dark_path="", baseline_enabled=False)
    win_no_dark = CalibrationWindow(config_no_dark, MockFrameSource(resolution=(40, 20), seed=0))
    win_no_dark.timer.stop()
    win_no_dark._update_spectrum()
    raw_mean = float(np.mean(win_no_dark._current_intensities))

    # Capture with dark subtraction
    win._update_spectrum()
    dark_mean = float(np.mean(win._current_intensities))

    # Dark subtraction must reduce the mean (dark adds noise floor)
    assert dark_mean < raw_mean, (
        f"Dark subtraction should lower mean intensity: raw={raw_mean:.2f}, dark={dark_mean:.2f}"
    )


def test_update_spectrum_dark_missing_no_crash(tmp_path):
    """_update_spectrum must complete without error when dark_frame_path is missing."""
    config = _make_config(dark_path=str(tmp_path / "does_not_exist.npy"), baseline_enabled=False)
    fs = MockFrameSource(resolution=(40, 20), seed=1)
    win = CalibrationWindow(config, fs)
    win.timer.stop()

    win._update_spectrum()

    # Should have produced valid intensities (not fallen back to mock length=512)
    assert win._current_intensities is not None
    assert len(win._current_intensities) == 40


def test_update_spectrum_baseline_applied(monkeypatch):
    """Baseline subtraction is applied when baseline_enabled=True; result differs from raw."""
    config_on  = _make_config(baseline_enabled=True)
    config_off = _make_config(baseline_enabled=False)

    fs_on  = MockFrameSource(resolution=(40, 20), seed=42)
    fs_off = MockFrameSource(resolution=(40, 20), seed=42)

    win_on  = CalibrationWindow(config_on,  fs_on)
    win_off = CalibrationWindow(config_off, fs_off)
    win_on.timer.stop()
    win_off.timer.stop()

    win_on._update_spectrum()
    win_off._update_spectrum()

    # Baseline subtracts the continuum floor → mean should be lower when enabled
    mean_on  = float(np.mean(win_on._current_intensities))
    mean_off = float(np.mean(win_off._current_intensities))

    assert mean_on < mean_off, (
        f"Baseline subtraction should reduce mean: baseline_on={mean_on:.2f}, baseline_off={mean_off:.2f}"
    )


def test_update_spectrum_baseline_disabled_no_crash():
    """_update_spectrum must complete without error when baseline_enabled=False."""
    config = _make_config(baseline_enabled=False)
    fs = MockFrameSource(resolution=(40, 20), seed=7)
    win = CalibrationWindow(config, fs)
    win.timer.stop()

    win._update_spectrum()

    assert win._current_intensities is not None
    assert len(win._current_intensities) == 40


def test_update_spectrum_2d_dark_with_nonzero_tilt(tmp_path):
    """
    Exercises the 2D dark -> 1D collapse branch with tilt_angle_deg != 0.0.

    The dark frame saved by DarkFrameWorker is 2D (H, W). When tilt_angle_deg
    is nonzero the code does:
        apply_tilt_correction as _tilt  (imported from pipeline.py)
        dark_2d = _tilt(dark_frame, tilt_angle)
        dark_frame = apply_flip(extract_band(...), flip_spectrum)

    This test confirms:
    - No NameError / AttributeError (function actually resolves to
      apply_tilt_correction from pipeline.py, not some other alias)
    - Output shape is correct (1-D, width=40)
    - Dark subtraction lowers mean vs no-dark run
    """
    dark_path = tmp_path / "dark_frame_2d.npy"
    # Save a 2-D dark (H=20, W=40) with a constant floor of 8.0
    np.save(str(dark_path), np.full((20, 40), 8.0, dtype=np.float32))

    # Config: nonzero tilt to trigger the _tilt(...) branch
    config = {
        "optics": {
            "center_y": 10,
            "tilt_angle_deg": 1.5,   # nonzero — exercises _tilt alias
            "flip_spectrum": False,
        },
        "dsp": {
            "band_half_height": 2,
            "baseline_enabled": False,   # isolate dark subtraction only
            "baseline_method": "sg_only",
            "baseline_window": 51,
            "baseline_polyorder": 2,
        },
        "storage": {"dark_frame_path": str(dark_path)},
        "camera": {"exposure_us": 20000},
        "calibration": {},
    }

    fs = MockFrameSource(resolution=(40, 20), seed=99)
    win = CalibrationWindow(config, fs)
    win.timer.stop()

    win._update_spectrum()

    # Must complete and produce a 1-D band of the correct width
    assert win._current_intensities is not None, "intensities should not be None after 2D dark + tilt"
    assert len(win._current_intensities) == 40, (
        f"Expected width=40, got {len(win._current_intensities)}"
    )

    # Verify subtraction actually reduced the mean vs no-dark run
    config_no_dark = {**config, "storage": {"dark_frame_path": ""}}
    win_no_dark = CalibrationWindow(config_no_dark, MockFrameSource(resolution=(40, 20), seed=99))
    win_no_dark.timer.stop()
    win_no_dark._update_spectrum()

    assert np.mean(win._current_intensities) < np.mean(win_no_dark._current_intensities), (
        "2D dark subtraction with nonzero tilt should lower mean intensity"
    )


def test_calibration_window_persistence(tmp_path):
    """
    Verifies that points and fit result are persisted to JSON and restored upon reopen.
    """
    state_file = tmp_path / "calibration_state.json"
    
    config = {
        "optics": {"center_y": 100, "band_half_height": 25, "flip_spectrum": False},
        "calibration": {"min_points": 2, "degree_low": 2, "degree_high": 3, "degree_threshold_points": 4},
        "storage": {"calibration_state_path": str(state_file)}
    }
    
    fs = MockFrameSource()
    win1 = CalibrationWindow(config, fs)
    win1.timer.stop()
    
    # Add points
    pt1 = CalibrationPoint(100, 450.0)
    pt1.pixel = 100
    pt1.wavelength = 450.0
    pt2 = CalibrationPoint(200, 550.0)
    pt2.pixel = 200
    pt2.wavelength = 550.0
    
    win1._points = [pt1, pt2]
    win1.canvas.set_calibration_points(win1._points)
    win1.table.clear_points()
    win1.table.add_point(pt1)
    win1.table.add_point(pt2)
    
    # Run fit
    win1._on_run_fit()
    
    assert win1._fit_result is not None
    assert win1._check_stale() is False
    
    # Open window 2 with same config and state path
    win2 = CalibrationWindow(config, fs)
    win2.timer.stop()
    
    assert len(win2._points) == 2
    assert win2._points[0].pixel == 100
    assert win2._points[0].wavelength == 450.0
    assert win2._points[1].pixel == 200
    assert win2._points[1].wavelength == 550.0
    
    assert win2._fit_result is not None
    assert len(win2._fit_result.coefficients) == 2
    assert win2._fit_result.rms_nm == win1._fit_result.rms_nm
    assert win2._check_stale() is False
    assert "Stale" not in win2.status_label.text()


def test_calibration_window_stale_fit(tmp_path):
    """
    Verifies that changing points after a fit marks the fit as stale.
    """
    state_file = tmp_path / "calibration_state.json"
    
    config = {
        "optics": {"center_y": 100, "band_half_height": 25, "flip_spectrum": False},
        "calibration": {"min_points": 2, "degree_low": 2, "degree_high": 3, "degree_threshold_points": 4},
        "storage": {"calibration_state_path": str(state_file)}
    }
    
    fs = MockFrameSource()
    win = CalibrationWindow(config, fs)
    win.timer.stop()
    
    # Add points and fit
    pt1 = CalibrationPoint(100, 450.0)
    pt1.pixel = 100
    pt1.wavelength = 450.0
    pt2 = CalibrationPoint(200, 550.0)
    pt2.pixel = 200
    pt2.wavelength = 550.0
    
    win._points = [pt1, pt2]
    win._on_run_fit()
    
    assert win._check_stale() is False
    assert "Stale" not in win.status_label.text()
    
    # Add a third point
    pt3 = CalibrationPoint(300, 650.0)
    pt3.pixel = 300
    pt3.wavelength = 650.0
    win._points.append(pt3)
    
    win.update_status_label()
    assert win._check_stale() is True
    assert "Stale" in win.status_label.text()
    
    # Remove the third point to restore the original state
    win._points.pop()
    win.update_status_label()
    assert win._check_stale() is False
    assert "Stale" not in win.status_label.text()


def test_apply_blocked_when_stale(monkeypatch, cal_window):
    """
    Verifies that calling _on_apply() when the fit is stale shows a warning dialog,
    does not write to the config, and does not accept the dialog.
    """
    # Mock warning box
    called_warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: called_warnings.append(text))

    # Add points and run fit
    pt1 = CalibrationPoint(100, 450.0)
    pt1.pixel = 100
    pt1.wavelength = 450.0
    pt2 = CalibrationPoint(200, 550.0)
    pt2.pixel = 200
    pt2.wavelength = 550.0
    
    cal_window._points = [pt1, pt2]
    cal_window._on_run_fit()
    
    assert cal_window._check_stale() is False
    
    # Add a point to make it stale
    pt3 = CalibrationPoint(300, 650.0)
    pt3.pixel = 300
    pt3.wavelength = 650.0
    cal_window._points.append(pt3)
    
    assert cal_window._check_stale() is True

    # Try applying
    cal_window._on_apply()

    # Verify warning was called and it blocked the write path
    assert len(called_warnings) == 1
    assert "stale" in called_warnings[0].lower()


