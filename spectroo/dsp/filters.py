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
    """§7 step 9 / T6."""
    if method == "minimum_filter1d_sg" or method == "sg_only":
        _w = max(1, len(intensity_1d) // 20)
        min_filtered = scipy.ndimage.minimum_filter1d(intensity_1d, size=2 * _w, mode='nearest')
        sg_win = min(51, len(intensity_1d))
        if sg_win % 2 == 0:
            sg_win -= 1
        if sg_win < 3:
            baseline = min_filtered
        else:
            baseline = scipy.signal.savgol_filter(min_filtered, window_length=sg_win, polyorder=2)
    else:
        raise ValueError(f"Unknown baseline subtraction method: '{method}'")
    return np.clip(intensity_1d - baseline, 0, None)
