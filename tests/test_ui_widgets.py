import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PyQt5.QtWidgets import QApplication
from spectroo.ui.status_bar import StatusBar
from spectroo.ui.control_panel import ControlPanel


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# --- StatusBar tests ---

def test_status_bar_constructs():
    status_bar = StatusBar()
    assert status_bar.fps_label.text() == "FPS: 0.0"


def test_status_bar_height():
    status_bar = StatusBar()
    assert status_bar.minimumHeight() == 28


def test_status_bar_update_fps():
    status_bar = StatusBar()
    status_bar.update_status({"fps": 12.5})
    assert status_bar.fps_label.text() == "FPS: 12.5"


def test_status_bar_update_peaks_calibrated():
    status_bar = StatusBar()
    status_bar.update_status({"calibrated": True, "peaks": [435.8, 546.1]})
    assert "nm" in status_bar.peaks_label.text()


def test_status_bar_update_peaks_uncalibrated():
    status_bar = StatusBar()
    status_bar.update_status({"calibrated": False, "peaks": [500.0]})
    assert "px" in status_bar.peaks_label.text()


# --- ControlPanel tests ---

def test_control_panel_constructs():
    panel = ControlPanel()
    assert panel.single_btn.isChecked() is True
    assert panel.live_btn.isChecked() is False


def test_control_panel_width():
    panel = ControlPanel()
    assert panel.minimumWidth() == 200 or panel.maximumWidth() == 200


def test_control_panel_stop_initially_disabled():
    panel = ControlPanel()
    assert panel.stop_btn.isEnabled() is False


def test_set_mode_live():
    panel = ControlPanel()
    panel.set_mode("live")
    assert panel.live_btn.isChecked() is True
    assert panel.stop_btn.isEnabled() is True


def test_set_mode_single():
    panel = ControlPanel()
    panel.set_mode("live")
    panel.set_mode("single")
    assert panel.single_btn.isChecked() is True
    assert panel.stop_btn.isEnabled() is False


def test_exposure_input_default():
    panel = ControlPanel()
    assert panel.exposure_input.text() == "50000"


def test_shutdown_button_exists():
    panel = ControlPanel()
    assert hasattr(panel, "shutdown_btn")
    assert panel.shutdown_btn.text() == "Shutdown"


def test_save_btn_exists():
    from PyQt5.QtWidgets import QPushButton
    panel = ControlPanel()
    assert hasattr(panel, "save_btn")
    assert isinstance(panel.save_btn, QPushButton)


def test_save_clicked_signal_exists():
    panel = ControlPanel()
    assert hasattr(panel, "save_clicked")
    called = False
    def on_click():
        nonlocal called
        called = True
    panel.save_clicked.connect(on_click)
    panel.save_clicked.emit()
    assert called is True


def test_save_btn_label():
    panel = ControlPanel()
    assert panel.save_btn.text() == "Save Spectrum"
