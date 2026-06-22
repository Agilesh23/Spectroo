"""SG smoothing + baseline (method per T6)."""

import scipy.ndimage
import scipy.signal
import numpy as np


def smooth_savgol(
    intensity_1d: np.ndarray, window: int, polyorder: int
) -> np.ndarray:
    """§7 step 8. Apply scipy.signal.savgol_filter."""
    return scipy.signal.savgol_filter(
        intensity_1d, window_length=window, polyorder=polyorder
    )


def subtract_baseline(
    intensity_1d: np.ndarray, method: str, window: int, polyorder: int
) -> np.ndarray:
    """§7 step 9 / T6.

    Two methods supported:
    - "minimum_filter1d_sg"
    - "sg_only"

    Returns intensity_1d - baseline.
    Raises ValueError for any other method string.
    """
    if method == "minimum_filter1d_sg":
        # ASSUMPTION: We reuse the config's baseline_window parameter as both
        # the size parameter for minimum_filter1d and the window_length for the
        # baseline Savitzky-Golay filter, because the spec only registers a single window.
        min_filtered = scipy.ndimage.minimum_filter1d(intensity_1d, size=window)
        baseline = scipy.signal.savgol_filter(
            min_filtered, window_length=window, polyorder=polyorder
        )
    elif method == "sg_only":
        baseline = scipy.signal.savgol_filter(
            intensity_1d, window_length=window, polyorder=polyorder
        )
    else:
        raise ValueError(f"Unknown baseline subtraction method: '{method}'")

    return intensity_1d - baseline
