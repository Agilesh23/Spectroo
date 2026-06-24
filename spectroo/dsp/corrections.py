"""Dark subtraction, response flat-field."""

import os
import json
import logging
import numpy as np

logger = logging.getLogger("spectroo")


def load_dark_frame(dark_path: str) -> np.ndarray | None:
    """Load dark frame array from .npy file.

    Returns:
        np.ndarray | None: Loaded array or None if not found/error.
    """
    if not dark_path:
        logger.warning("Dark frame path not configured.")
        return None
    if not os.path.exists(dark_path):
        logger.warning(f"Dark frame file not found at: {dark_path}")
        return None
    try:
        arr = np.load(dark_path)
        logger.info(f"Successfully loaded dark frame from: {dark_path}")
        return arr
    except Exception as e:
        logger.error(f"Error loading dark frame from {dark_path}: {e}")
        return None


def load_flat_field(flat_path: str) -> np.ndarray | None:
    """Load flat-field correction profile from JSON file.

    Returns:
        np.ndarray | None: Loaded profile array or None if not found/error.
    """
    if not flat_path:
        logger.warning("Flat-field path not configured.")
        return None
    if not os.path.exists(flat_path):
        logger.warning(f"Flat-field file not found at: {flat_path}")
        return None
    try:
        with open(flat_path, "r") as f:
            data = json.load(f)
        arr = np.array(data, dtype=np.float32)
        logger.info(f"Successfully loaded flat-field correction from: {flat_path}")
        return arr
    except Exception as e:
        logger.error(f"Error loading flat-field from {flat_path}: {e}")
        return None


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

