"""Per-frame DSP pipeline orchestrator."""

from datetime import datetime, timezone
import logging
import threading
import numpy as np
import scipy.ndimage

from spectroo.core.models import Spectrum
from spectroo.core.calibration import PolynomialCalibration, apply_calibration
from spectroo.dsp.collapse import extract_band, apply_flip
from spectroo.dsp.corrections import subtract_dark, apply_flat_field
from spectroo.dsp.filters import smooth_savgol, subtract_baseline
from spectroo.dsp.peaks import find_spectrum_peaks

logger = logging.getLogger("spectroo.dsp.pipeline")

_pipeline_state_lock = threading.Lock()
_pipeline_state = {
    "dark_loaded": None,
    "flat_loaded": None,
    "baseline_enabled": None,
    "baseline_method": None,
    "baseline_window": None,
    "calibration_active": None,
}



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
    global _pipeline_state

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

    # Log dark frame state once on change
    dark_loaded_now = dark_frame_1d is not None
    with _pipeline_state_lock:
        if dark_loaded_now != _pipeline_state["dark_loaded"]:
            _pipeline_state["dark_loaded"] = dark_loaded_now
            logger.info("DSP: Dark frame subtraction %s", "enabled" if dark_loaded_now else "disabled")

    # 7. Savitzky-Golay smoothing
    band = smooth_savgol(
        band, dsp_cfg["savgol_window"], dsp_cfg["savgol_polyorder"]
    )

    # 8. Baseline subtraction (skipped when baseline_enabled is False)
    if dsp_cfg.get("baseline_enabled", True):
        band = subtract_baseline(
            band,
            dsp_cfg["baseline_method"],
            dsp_cfg["baseline_window"],
            dsp_cfg["baseline_polyorder"],
        )

    # Log baseline correction state once on change
    base_enabled_now = dsp_cfg.get("baseline_enabled", True)
    base_method_now = dsp_cfg.get("baseline_method", "")
    base_window_now = dsp_cfg.get("baseline_window", 0)
    with _pipeline_state_lock:
        if (base_enabled_now != _pipeline_state["baseline_enabled"] or 
            base_method_now != _pipeline_state["baseline_method"] or
            base_window_now != _pipeline_state["baseline_window"]):
            _pipeline_state["baseline_enabled"] = base_enabled_now
            _pipeline_state["baseline_method"] = base_method_now
            _pipeline_state["baseline_window"] = base_window_now
            if base_enabled_now:
                logger.info("DSP: Baseline correction enabled (method: %s, window: %d)", base_method_now, base_window_now)
            else:
                logger.info("DSP: Baseline correction disabled")

    # 9. Response flat-field correction
    if response_flat is not None:
        band = apply_flat_field(band, response_flat)

    # Log flat field state once on change
    flat_loaded_now = response_flat is not None
    with _pipeline_state_lock:
        if flat_loaded_now != _pipeline_state["flat_loaded"]:
            _pipeline_state["flat_loaded"] = flat_loaded_now
            logger.info("DSP: Flat-field correction %s", "enabled" if flat_loaded_now else "disabled")

    # 10. Wavelength mapping
    pixel_indices = np.arange(len(band))
    if calibration is not None:
        wavelengths = apply_calibration(calibration, pixel_indices)
    elif wavelengths_lut is not None:
        wavelengths = wavelengths_lut
    else:
        wavelengths = None

    # Log calibration state once on change
    cal_active_now = calibration is not None
    with _pipeline_state_lock:
        if cal_active_now != _pipeline_state["calibration_active"]:
            _pipeline_state["calibration_active"] = cal_active_now
            if cal_active_now:
                logger.info("DSP: Calibration active (degree: %d, RMS: %.4f nm)", calibration.degree, calibration.rms_nm)
            else:
                logger.info("DSP: Calibration inactive (using fallback grating equation or pixel indices)")

    # 11. Peak detection
    peaks = find_spectrum_peaks(
        band,
        wavelengths,
        peaks_cfg["prominence_pct"],
        peaks_cfg["prominence_min"],
        peaks_cfg["min_distance_px"],
    )
    logger.debug("DSP: Peak detection found %d peaks", len(peaks))

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
        dark_frame_loaded=dark_frame_1d is not None,
        flat_field_loaded=response_flat is not None,
    )
