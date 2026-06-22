import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
import numpy as np
from PyQt5.QtWidgets import QApplication
from spectroo.ui.plot_widget import wavelength_to_rgb, SpectrumPlotWidget


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_wavelength_to_rgb_violet():
    r, g, b = wavelength_to_rgb(410.0)
    assert r < 0.5
    assert b > 0.5


def test_wavelength_to_rgb_green():
    r, g, b = wavelength_to_rgb(530.0)
    assert g > 0.5
    assert r < 0.4
    assert b < 0.3


def test_wavelength_to_rgb_red():
    r, g, b = wavelength_to_rgb(660.0)
    assert r > 0.5
    assert g < 0.1
    assert b < 0.1


def test_wavelength_to_rgb_out_of_range():
    r, g, b = wavelength_to_rgb(200.0)
    assert r == 0.0
    assert g == 0.0
    assert b == 0.0


def test_widget_constructs():
    widget = SpectrumPlotWidget()
    assert widget.wavelengths is None
    assert widget.fill_mode == "color"


def test_set_data_stores_arrays():
    widget = SpectrumPlotWidget()
    wls = np.linspace(380.0, 780.0, 100)
    intensities = np.full(100, 50.0)
    widget.set_data(wls, intensities, [10, 20])
    assert len(widget.wavelengths) == 100
    assert len(widget.intensities) == 100
    assert widget.peaks == [10, 20]


def test_set_data_rejects_none():
    widget = SpectrumPlotWidget()
    widget.set_data(None, None, [])
    assert widget.wavelengths is None


def test_set_fill_mode_plain():
    widget = SpectrumPlotWidget()
    widget.set_fill_mode("plain")
    assert widget.fill_mode == "plain"


def test_set_fill_mode_ignores_invalid():
    widget = SpectrumPlotWidget()
    widget.set_fill_mode("rainbow")
    assert widget.fill_mode == "color"


def test_paint_does_not_crash():
    widget = SpectrumPlotWidget()
    # Give the widget a size so calculations inside paintEvent work
    widget.resize(800, 600)
    
    # Check no-data path
    pixmap_no_data = widget.grab()
    assert not pixmap_no_data.isNull()

    # Check with-data path (both calibrated and uncalibrated)
    wls = np.linspace(380.0, 780.0, 100)
    intensities = np.full(100, 50.0)
    widget.set_data(wls, intensities, [10, 20])
    widget.inspect_idx = 15
    widget.inspect_x = float(wls[15])
    
    pixmap_calibrated = widget.grab()
    assert not pixmap_calibrated.isNull()

    # Switch to uncalibrated
    widget_uncalib = SpectrumPlotWidget()
    widget_uncalib.resize(800, 600)
    wls_uncalib = np.linspace(0.0, 100.0, 100)
    intensities_uncalib = np.full(100, 50.0)
    widget_uncalib.set_data(wls_uncalib, intensities_uncalib, [10])
    widget_uncalib.set_fill_mode("plain")
    widget_uncalib.inspect_idx = 15
    widget_uncalib.inspect_x = float(wls_uncalib[15])

    pixmap_uncalibrated = widget_uncalib.grab()
    assert not pixmap_uncalibrated.isNull()
