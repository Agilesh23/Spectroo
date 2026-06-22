"""Dark subtraction, response flat-field."""

import numpy as np


def subtract_dark(
    intensity_1d: np.ndarray, dark_frame_1d: np.ndarray
) -> np.ndarray:
    """§7 step 7. Subtract elementwise, clip result to minimum 0."""
    return np.maximum(0.0, intensity_1d - dark_frame_1d)


def apply_flat_field(
    intensity_1d: np.ndarray, response_flat: np.ndarray, floor: float = 0.001
) -> np.ndarray:
    """§7 step 10. Divide elementwise by response_flat.

    response_flat is first clipped to a minimum of `floor` to avoid division blow-up.
    """
    clipped_flat = np.maximum(response_flat, floor)
    return intensity_1d / clipped_flat
