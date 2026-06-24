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


def test_control_panel_buttons_logging(caplog):
    import logging
    from unittest.mock import patch
    from spectroo.ui.main_window import SpectrooMainWindow

    caplog.set_level(logging.INFO)

    cfg = {
        "camera": {"exposure_us": 50000, "n_frames": 4},
        "dsp": {"baseline_enabled": True},
        "storage": {"dark_frame_path": "dark_frame.npy"},
        "calibration": {},
        "history": {"db_path": "data/spectroo.db", "max_entries": 500},
    }

    # Patch blocking and background-running dependencies
    with patch("PyQt5.QtWidgets.QMessageBox.information"), \
         patch("PyQt5.QtWidgets.QMessageBox.warning"), \
         patch("PyQt5.QtWidgets.QMessageBox.critical"), \
         patch("PyQt5.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")), \
         patch("subprocess.run"), \
         patch("spectroo.ui.main_window.SingleAcquisitionWorker"), \
         patch("spectroo.ui.main_window.LivePipelineWorker"), \
         patch("spectroo.ui.main_window.DarkFrameWorker"):

        window = SpectrooMainWindow(cfg, dev=True)
        panel = window.control_panel

        caplog.clear()

        # 1. Mode Single Toggle
        panel.single_btn.click()
        assert any("Button clicked: Mode Single" in r.message for r in caplog.records)
        caplog.clear()

        # 2. Mode Live Toggle
        panel.live_btn.click()
        assert any("Button clicked: Mode Live" in r.message for r in caplog.records)
        caplog.clear()

        # 3. Start Button
        panel.start_btn.click()
        assert any("Button clicked: Start" in r.message for r in caplog.records)
        caplog.clear()

        # 4. Stop Button
        # Force enable stop button to click it
        panel.stop_btn.setEnabled(True)
        panel.stop_btn.click()
        assert any("Button clicked: Stop" in r.message for r in caplog.records)
        caplog.clear()

        # 5. Colour Spectrum Toggle
        panel.plot_mode_btn.click()
        assert any("Button clicked: Colour Spectrum toggle" in r.message for r in caplog.records)
        caplog.clear()

        # 6. Baseline Corr Toggle
        panel.baseline_btn.click()
        assert any("Button clicked: Baseline Corr" in r.message for r in caplog.records)
        caplog.clear()

        # 7. Calibrate...
        # Patch the modal dialog box from opening
        with patch.object(window, "_open_dev_window") as mock_open:
            panel.calibrate_btn.click()
            assert any("Button clicked: Calibrate..." in r.message for r in caplog.records)
        caplog.clear()

        # 8. Capture Dark Frame
        panel.dark_btn.click()
        assert any("Button clicked: Capture Dark Frame" in r.message for r in caplog.records)
        caplog.clear()

        # 9. Export JSON
        panel.export_btn.click()
        assert any("Button clicked: Export JSON" in r.message for r in caplog.records)
        caplog.clear()

        # 10. Save Chart
        panel.save_chart_btn.click()
        assert any("Button clicked: Save Chart" in r.message for r in caplog.records)
        caplog.clear()

        # 11. Save Spectrum
        panel.save_btn.click()
        assert any("Button clicked: Save Spectrum" in r.message for r in caplog.records)
        caplog.clear()

        # 12. History
        panel.history_btn.click()
        assert any("Button clicked: History" in r.message for r in caplog.records)
        caplog.clear()

        # 13. Shutdown
        panel.shutdown_btn.click()
        assert any("Button clicked: Shutdown" in r.message for r in caplog.records)
        caplog.clear()
