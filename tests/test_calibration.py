import os
import numpy as np
import pytest
from spectroo.core.calibration import apply_calibration, fit_calibration, PolynomialCalibration
from spectroo.core.config import load_config
from spectroo.core.exceptions import CalibrationError, ConfigError
from spectroo.core.grating_model import build_grating_lut, pixel_to_wavelength_nm
from spectroo.core.models import CalibrationPoint


# 1. fit_calibration with exactly 2 points -> degree == 1
def test_fit_calibration_two_points():
    points = [
        CalibrationPoint(pixel_index=100, known_wavelength_nm=400.0),
        CalibrationPoint(pixel_index=200, known_wavelength_nm=500.0),
    ]
    cal = fit_calibration(points, degree_low=2, degree_high=3, degree_threshold_points=4)
    assert cal.degree == 1
    assert len(cal.coefficients) == 2


# 2. fit_calibration with 4 points -> degree == degree_high
def test_fit_calibration_four_points():
    points = [
        CalibrationPoint(pixel_index=100, known_wavelength_nm=400.0),
        CalibrationPoint(pixel_index=200, known_wavelength_nm=500.0),
        CalibrationPoint(pixel_index=300, known_wavelength_nm=600.0),
        CalibrationPoint(pixel_index=400, known_wavelength_nm=700.0),
    ]
    cal = fit_calibration(points, degree_low=2, degree_high=3, degree_threshold_points=4)
    assert cal.degree == 3
    assert len(cal.coefficients) == 4


# 3. fit_calibration with 1 point -> raises CalibrationError
def test_fit_calibration_one_point():
    points = [
        CalibrationPoint(pixel_index=100, known_wavelength_nm=400.0),
    ]
    with pytest.raises(CalibrationError):
        fit_calibration(points, min_points=2)


# 4. apply_calibration on a known simple linear fit returns expected values
def test_apply_calibration_linear():
    # Linear fit: y = 2*x + 100
    # Coefficients: [2.0, 100.0]
    cal = PolynomialCalibration(coefficients=[2.0, 100.0], degree=1, rms_nm=0.0)
    pixels = np.array([0, 10, 50, 100], dtype=float)
    expected = 2.0 * pixels + 100.0
    actual = apply_calibration(cal, pixels)
    assert actual == pytest.approx(expected)


# 5. pixel_to_wavelength_nm at centre_pixel returns ~0 nm (theta=0 -> sin(0)=0)
def test_pixel_to_wavelength_nm_centre():
    val = pixel_to_wavelength_nm(
        pixel_index=500,
        centre_pixel=500.0,
        pixel_size_mm=0.0014,
        focal_length_mm=12.0,
        lines_per_mm=600.0,
        diffraction_order=1,
    )
    assert val == pytest.approx(0.0, abs=1e-9)


# 6. build_grating_lut returns array of correct length and is monotonic
def test_build_grating_lut_monotonic():
    lut = build_grating_lut(
        n_pixels=1000,
        centre_pixel=500.0,
        pixel_size_mm=0.0014,
        focal_length_mm=12.0,
        lines_per_mm=600.0,
        diffraction_order=1,
    )
    assert len(lut) == 1000

    # Monotonic check: all differences are positive or all are negative
    diffs = np.diff(lut)
    assert np.all(diffs > 0) or np.all(diffs < 0)


# 7. load_config: write a temp TOML, load it, assert access; write malformed TOML, assert ConfigError
def test_load_config(tmp_path):
    # Valid TOML file
    valid_file = tmp_path / "valid_config.toml"
    valid_file.write_text(
        """
[app]
name = "Spectroo Test"
version = "1.0"
"""
    )
    config = load_config(str(valid_file))
    assert config["app"]["name"] == "Spectroo Test"
    assert config["app"]["version"] == "1.0"

    # Malformed TOML file
    malformed_file = tmp_path / "malformed_config.toml"
    malformed_file.write_text(
        """
[app
name = "Spectroo Test"
"""
    )
    with pytest.raises(ConfigError):
        load_config(str(malformed_file))

    # Non-existent TOML file
    non_existent = tmp_path / "non_existent.toml"
    with pytest.raises(ConfigError):
        load_config(str(non_existent))
