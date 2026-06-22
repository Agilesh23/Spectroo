import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
import numpy as np
from PyQt5.QtWidgets import QApplication
from spectroo.ui.main_window import SpectrooMainWindow
from spectroo.ui.plot_widget import SpectrumPlotWidget
from spectroo.ui.control_panel import ControlPanel
from spectroo.ui.status_bar import StatusBar

MINIMAL_CONFIG = {
    "camera": {"exposure_us": 50000, "n_frames": 4},
    "dsp": {"baseline_enabled": True},
    "storage": {"dark_frame_path": "dark_frame.npy"},
    "calibration": {},
}


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def window():
    # Make a copy of MINIMAL_CONFIG to avoid test crosstalk
    cfg = {
        "camera": dict(MINIMAL_CONFIG["camera"]),
        "dsp": dict(MINIMAL_CONFIG["dsp"]),
        "storage": dict(MINIMAL_CONFIG["storage"]),
        "calibration": dict(MINIMAL_CONFIG["calibration"]),
    }
    return SpectrooMainWindow(cfg)


def test_main_window_constructs(window):
    assert window is not None


def test_main_window_has_plot_widget(window):
    assert isinstance(window.plot_widget, SpectrumPlotWidget)


def test_main_window_has_control_panel(window):
    assert isinstance(window.control_panel, ControlPanel)


def test_main_window_has_status_bar(window):
    assert isinstance(window.status_bar, StatusBar)


def test_main_window_initial_mode(window):
    assert window.current_mode == "single"


def test_exposure_change_updates_config(window):
    window._on_exposure_changed(100000)
    assert window.config["camera"]["exposure_us"] == 100000


def test_baseline_toggle_updates_config(window):
    window._on_baseline_toggled(False)
    assert window.config["dsp"]["baseline_enabled"] is False


def test_on_frame_ready_updates_plot(window):
    data = {
        "wavelengths": np.linspace(400, 700, 100),
        "intensities": np.ones(100) * 50.0,
        "peaks": [],
    }
    window._on_frame_ready(data)
    assert window.plot_widget.wavelengths is not None


def test_on_save_clicked_no_spectrum(window):
    from unittest.mock import MagicMock
    window.current_spectrum = None
    window.save_spectrum = MagicMock()
    window.history_panel.refresh = MagicMock()
    
    window._on_save_clicked()
    
    window.save_spectrum.assert_not_called()
    window.history_panel.refresh.assert_not_called()


def test_on_save_clicked_calls_save_and_refresh(window):
    from unittest.mock import MagicMock
    from spectroo.core.models import Spectrum
    
    dummy_spectrum = Spectrum(
        pixel_indices=np.arange(10),
        intensity=np.ones(10) * 100.0,
        wavelengths=np.linspace(400, 500, 10),
        exposure_us=200000,
        peaks=[],
        calibration_rms_at_capture=None,
        timestamp="2026-06-22T12:00:00Z"
    )
    
    window.current_spectrum = dummy_spectrum
    window.save_spectrum = MagicMock()
    window.history_panel.refresh = MagicMock()
    
    window._on_save_clicked()
    
    window.save_spectrum.assert_called_once()
    window.history_panel.refresh.assert_called_once()
