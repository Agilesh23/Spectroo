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
