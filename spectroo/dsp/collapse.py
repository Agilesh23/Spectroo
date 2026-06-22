"""Band extraction using locked center_y."""

import numpy as np


def extract_band(
    frame_2d: np.ndarray, center_y: int, band_half_height: int
) -> np.ndarray:
    """§7 step 5. frame_2d is a 2D greyscale, tilt-corrected frame (H, W).

    Average rows [center_y - band_half_height, center_y + band_half_height]
    inclusive, column-wise, producing a 1D array of length W.
    """
    h, w = frame_2d.shape
    start_y = max(0, center_y - band_half_height)
    end_y = min(h, center_y + band_half_height + 1)
    band_slice = frame_2d[start_y:end_y, :]
    return np.mean(band_slice, axis=0)


def apply_flip(intensity_1d: np.ndarray, flip_spectrum: bool) -> np.ndarray:
    """§7 step 6. If flip_spectrum is True, reverse the array.

    Returns a new reversed copy without mutating the original in place.
    Otherwise, returns the array unchanged.
    """
    if flip_spectrum:
        return intensity_1d[::-1].copy()
    return intensity_1d
