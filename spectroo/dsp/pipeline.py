"""Per-frame DSP pipeline orchestrator."""

from datetime import datetime, timezone
import numpy as np
import scipy.ndimage

from spectroo.core.models import Spectrum, Peak
from spectroo.core.calibration import PolynomialCalibration, apply_calibration
from spectroo.dsp.collapse import extract_band, apply_flip
from spectroo.dsp.corrections import subtract_dark, apply_flat_field
from spectroo.dsp.filters import smooth_savgol, subtract_baseline
from spectroo.dsp.peaks import find_spectrum_peaks


def average_frames(frames: list[np.ndarray]) -> np.ndarray:
    """§7 step 2. Average stack of frames to float32."""
    return np.mean(np.stack(frames, axis=0), axis=0).astype(np.float32)


def to_greyscale(frame_rgb: np.ndarray) -> np.ndarray:
    """§7 step 3. Convert RGB to greyscale.

    Luminance = 0.299*R + 0.587*G + 0.114*B.
    Input: shape (H, W, 3) -> Output: shape (H, W), dtype float32.
    """
    r = frame_rgb[..., 0]
    g = frame_rgb[..., 1]
    b = frame_rgb[..., 2]
    return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)


def apply_tilt_correction(
    frame_2d: np.ndarray, tilt_angle_deg: float
) -> np.ndarray:
    """§7 step 4. Apply one-time tilt rotation.

    CRITICAL: reshape=False is mandatory. By default, scipy.ndimage.rotate
    will resize the array boundary box to fit the rotated contents. This would
    change the frame shape during rotation, breaking downstream pixel indices
    (like center_y, band_half_height, centre_pixel).
    """
    return scipy.ndimage.rotate(
        frame_2d,
        angle=tilt_angle_deg,
        reshape=False,
        order=1,
        mode="constant",
        cval=0.0,
    )


def run_pipeline(
    frames: list[np.ndarray],
    optics: dict,
    dsp_cfg: dict,
    peaks_cfg: dict,
    exposure_us: int,
    dark_frame_1d: np.ndarray | None = None,
    response_flat: np.ndarray | None = None,
    wavelengths_lut: np.ndarray | None = None,
    calibration: PolynomialCalibration | None = None,
) -> Spectrum:
    """Orchestrates §7 steps 2-12 in order, producing a Spectrum object."""
    # 1. Average frames
    avg = average_frames(frames)

    # 2. Convert to greyscale
    grey = to_greyscale(avg)

    # 3. Apply tilt correction
    tilted = apply_tilt_correction(grey, optics["tilt_angle_deg"])

    # 4. Band extraction
    band = extract_band(tilted, optics["center_y"], dsp_cfg["band_half_height"])

    # 5. Locked flip correction
    band = apply_flip(band, optics["flip_spectrum"])

    # 6. Dark subtraction
    if dark_frame_1d is not None:
        if dark_frame_1d.ndim == 2:
            dark_tilted = apply_tilt_correction(dark_frame_1d, optics["tilt_angle_deg"])
            dark_band = extract_band(dark_tilted, optics["center_y"], dsp_cfg["band_half_height"])
            dark_frame_1d = apply_flip(dark_band, optics["flip_spectrum"])
        band = subtract_dark(band, dark_frame_1d)


    # 7. Savitzky-Golay smoothing
    band = smooth_savgol(
        band, dsp_cfg["savgol_window"], dsp_cfg["savgol_polyorder"]
    )

    # 8. Baseline subtraction
    band = subtract_baseline(
        band,
        dsp_cfg["baseline_method"],
        dsp_cfg["baseline_window"],
        dsp_cfg["baseline_polyorder"],
    )

    # 9. Response flat-field correction
    if response_flat is not None:
        band = apply_flat_field(band, response_flat)

    # 10. Wavelength mapping
    pixel_indices = np.arange(len(band))
    if calibration is not None:
        wavelengths = apply_calibration(calibration, pixel_indices)
    elif wavelengths_lut is not None:
        wavelengths = wavelengths_lut
    else:
        wavelengths = None

    # 11. Peak detection
    peaks = find_spectrum_peaks(
        band,
        wavelengths,
        peaks_cfg["prominence_pct"],
        peaks_cfg["prominence_min"],
        peaks_cfg["min_distance_px"],
    )

    # 12. Build and return Spectrum
    timestamp = datetime.now(timezone.utc).isoformat()
    return Spectrum(
        pixel_indices=pixel_indices,
        intensity=band,
        wavelengths=wavelengths,
        exposure_us=exposure_us,
        peaks=peaks,
        calibration_rms_at_capture=calibration.rms_nm
        if calibration is not None
        else None,
        timestamp=timestamp,
    )
