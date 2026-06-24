"""Spectrum, CalibrationPoint, HistoryRecord data models."""

from dataclasses import dataclass
import numpy as np


@dataclass
class Peak:
    """Represents a detected peak in the spectrum."""
    pixel_index: int
    wavelength_nm: float | None
    intensity: float
    prominence: float


@dataclass
class CalibrationPoint:
    """Represents a mapping between a pixel coordinate and a known emission wavelength."""
    pixel_index: int
    known_wavelength_nm: float


@dataclass
class Spectrum:
    """Represents a measured or processed spectrum frame."""
    pixel_indices: np.ndarray
    intensity: np.ndarray
    wavelengths: np.ndarray | None
    exposure_us: int
    peaks: list[Peak]
    calibration_rms_at_capture: float | None
    timestamp: str  # ISO 8601 UTC
    dark_frame_loaded: bool = False
    flat_field_loaded: bool = False


@dataclass
class HistoryRecord:
    """Represents a historical spectrum record persisted in SQLite."""
    id: int | None
    timestamp: str
    exposure_us: int
    pixel_indices: list[int]
    intensity: list[float]
    wavelengths: list[float] | None
    peaks: list[Peak]
    png_path: str
    calibration_rms_at_capture: float | None
