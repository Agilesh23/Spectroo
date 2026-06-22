"""Grating equation lookup table (LUT) model."""

import numpy as np


def pixel_to_wavelength_nm(
    pixel_index: int,
    centre_pixel: float,
    pixel_size_mm: float,
    focal_length_mm: float,
    lines_per_mm: float,
    diffraction_order: int = 1,
) -> float:
    """Calculate the wavelength in nm for a single pixel index.

    Equations:
        theta = arctan((x - centre_pixel) * pixel_size_mm / focal_length_mm)
        lambda = (1 / lines_per_mm) * sin(theta) * (1 / diffraction_order) * 1e6
    """
    theta = np.arctan((pixel_index - centre_pixel) * pixel_size_mm / focal_length_mm)
    wavelength = (1.0 / lines_per_mm) * np.sin(theta) * (1.0 / diffraction_order) * 1e6
    return float(wavelength)


def build_grating_lut(
    n_pixels: int,
    centre_pixel: float,
    pixel_size_mm: float,
    focal_length_mm: float,
    lines_per_mm: float,
    diffraction_order: int = 1,
) -> np.ndarray:
    """Build a lookup table (LUT) mapping pixel indices to wavelengths in nm.

    Returns an array of length n_pixels containing the wavelength per pixel index.
    """
    x = np.arange(n_pixels, dtype=float)
    theta = np.arctan((x - centre_pixel) * pixel_size_mm / focal_length_mm)
    wavelengths = (1.0 / lines_per_mm) * np.sin(theta) * (1.0 / diffraction_order) * 1e6
    return wavelengths
