import numpy as np
import pytest
from spectroo.core.calibration import apply_calibration, fit_calibration, PolynomialCalibration
from spectroo.core.config import load_config, write_calibration_to_config
from spectroo.core.exceptions import CalibrationError, ConfigError
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


# 5. tomli_w dependency import regression test
def test_tomli_w_dependency_import():
    """Regression test: assert tomli_w dependency is installed and importable."""
    import tomli_w
    assert hasattr(tomli_w, "dump") or hasattr(tomli_w, "dumps")


# 6. Full calibration save/load persistence round-trip test
def test_calibration_write_and_load_persistence(tmp_path):
    """Assert write_calibration_to_config and load_config preserve exact precision, ordering, and evaluation."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[app]
name = "Spectroo Test"

[calibration]
coefficients = []
degree = 3
n_points = 0
"""
    )

    # 4 sample calibration points fit to a 3rd degree polynomial
    points = [
        CalibrationPoint(pixel_index=100, known_wavelength_nm=435.8),
        CalibrationPoint(pixel_index=250, known_wavelength_nm=546.1),
        CalibrationPoint(pixel_index=400, known_wavelength_nm=640.2),
        CalibrationPoint(pixel_index=500, known_wavelength_nm=702.4),
    ]

    fit = fit_calibration(points, degree_high=3)
    orig_coefs = fit.coefficients  # High-to-low degree order [c3, c2, c1, c0]
    orig_degree = fit.degree
    orig_n_points = len(points)

    # Save to temp config via write_calibration_to_config
    write_calibration_to_config(str(config_file), orig_coefs, orig_degree, orig_n_points)

    # Load back using load_config
    reloaded = load_config(str(config_file))
    cal_sec = reloaded.get("calibration", {})

    reloaded_coefs = cal_sec.get("coefficients")
    reloaded_degree = cal_sec.get("degree")
    reloaded_n_points = cal_sec.get("n_points")

    # Assert exact structural matches
    assert reloaded_degree == orig_degree
    assert reloaded_n_points == orig_n_points
    assert len(reloaded_coefs) == len(orig_coefs)

    # Assert coefficient ordering and full floating-point precision (no rounding)
    assert reloaded_coefs == orig_coefs

    # Assert polyval wavelength evaluation matches exactly across sample pixel range
    test_pixels = np.array([0, 100, 250, 400, 500, 1024, 2592], dtype=float)
    expected_wavelengths = np.polyval(orig_coefs, test_pixels)
    reloaded_wavelengths = np.polyval(reloaded_coefs, test_pixels)

    np.testing.assert_allclose(reloaded_wavelengths, expected_wavelengths, rtol=1e-9, atol=1e-9)


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
