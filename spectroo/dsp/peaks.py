"""find_peaks, prominence ranking."""

import scipy.signal
import numpy as np
from spectroo.core.models import Peak


def find_spectrum_peaks(
    intensity_1d: np.ndarray,
    wavelengths: np.ndarray | None,
    prominence_pct: float,
    prominence_min: float,
    min_distance_px: int,
) -> list[Peak]:
    """§7 step 12. Find peaks, prominence ranking.

    Calculate prominence threshold: max(prominence_min, prominence_pct * max(intensity_1d))
    Return all detected peaks sorted by prominence descending.
    """
    if len(intensity_1d) == 0:
        return []

    max_intensity = float(np.max(intensity_1d))
    prominence_threshold = max(prominence_min, prominence_pct * max_intensity)

    indices, properties = scipy.signal.find_peaks(
        intensity_1d, prominence=prominence_threshold, distance=min_distance_px
    )

    prominences = properties.get("prominences", [0.0] * len(indices))
    peaks = []

    for i, idx in enumerate(indices):
        wavelength_nm = (
            float(wavelengths[idx]) if wavelengths is not None else None
        )
        peaks.append(
            Peak(
                pixel_index=int(idx),
                wavelength_nm=wavelength_nm,
                intensity=float(intensity_1d[idx]),
                prominence=float(prominences[i]),
            )
        )

    # Sort descending by prominence
    peaks.sort(key=lambda p: p.prominence, reverse=True)
    return peaks
