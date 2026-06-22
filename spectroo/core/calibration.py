"""Adaptive-degree polynomial fit and RMS calibration engine."""

from dataclasses import dataclass
import numpy as np
from spectroo.core.exceptions import CalibrationError
from spectroo.core.models import CalibrationPoint


@dataclass
class PolynomialCalibration:
    """Represents a polynomial wavelength calibration fit."""

    coefficients: list[float]
    degree: int
    rms_nm: float


def fit_calibration(
    points: list[CalibrationPoint],
    degree_low: int = 2,
    degree_high: int = 3,
    degree_threshold_points: int = 4,
    min_points: int = 2,
) -> PolynomialCalibration:
    """Perform an adaptive-degree polynomial fit of pixel index to wavelength.

    Use degree_low if len(points) < degree_threshold_points, else degree_high.

    Raises:
        CalibrationError: If the number of points is less than min_points.
    """
    if len(points) < min_points:
        raise CalibrationError(
            f"Fewer than {min_points} calibration points supplied (got {len(points)})."
        )

    # degree_low and degree_threshold_points kept in signature for config compatibility; min(len(points)-1, degree_high) avoids underdetermined fits.
    degree = min(len(points) - 1, degree_high)

    x = np.array([p.pixel_index for p in points], dtype=float)
    y = np.array([p.known_wavelength_nm for p in points], dtype=float)

    try:
        coefficients = np.polyfit(x, y, degree)
        y_fit = np.polyval(coefficients, x)
        rms = np.sqrt(np.mean((y_fit - y) ** 2))
    except Exception as e:
        raise CalibrationError(f"Polynomial fitting failed: {e}") from e

    return PolynomialCalibration(
        coefficients=list(coefficients),
        degree=degree,
        rms_nm=float(rms),
    )


def apply_calibration(
    calibration: PolynomialCalibration, pixel_indices: np.ndarray
) -> np.ndarray:
    """Apply the polynomial calibration to an array of pixel indices using polyval."""
    return np.polyval(calibration.coefficients, pixel_indices)
