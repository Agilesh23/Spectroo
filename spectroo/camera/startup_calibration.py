"""Combined tilt + flip + centre-row routine."""

import numpy as np
from spectroo.core.exceptions import CalibrationError
from spectroo.dsp.pipeline import average_frames, to_greyscale, apply_tilt_correction


def detect_tilt(gray_image: np.ndarray) -> float:
    """Detect the tilt angle of the spectral band in a grayscale image.

    Ported verbatim from reference/v1 corrections/tilt.py.
    """
    sampled = gray_image[::4, :]
    H, W = sampled.shape
    n_cols = 8
    col_positions = np.linspace(0, W - 1, n_cols, dtype=int)
    row_positions = []
    for col in col_positions:
        col_data = sampled[:, col]
        brightest_row = int(np.argmax(col_data)) * 4  # scale back to full image
        row_positions.append(brightest_row)
    col_arr = col_positions.astype(float)
    row_arr = np.array(row_positions, dtype=float)
    slope = np.polyfit(col_arr, row_arr, 1)[0]
    angle = float(np.degrees(np.arctan(slope)))
    return angle


def detect_spectrum_flip(
    rgb_band: np.ndarray, min_separation_pixels: int = 30
) -> bool | None:
    """Return True when red-dominant signal is left of blue-dominant signal.

    Ported verbatim from reference/v1 live/pi_camera_source.py.
    """
    if rgb_band.ndim != 3 or rgb_band.shape[2] < 3:
        return None

    red = rgb_band[:, :, 0].mean(axis=0)
    green = rgb_band[:, :, 1].mean(axis=0)
    blue = rgb_band[:, :, 2].mean(axis=0)

    red_dominance = np.clip(red - 0.5 * (green + blue), 0.0, None)
    blue_dominance = np.clip(blue - 0.5 * (red + green), 0.0, None)

    red_total = float(red_dominance.sum())
    blue_total = float(blue_dominance.sum())
    if red_total <= 0.0 or blue_total <= 0.0:
        return None

    pixels = np.arange(rgb_band.shape[1], dtype=float)
    red_centroid = float(np.sum(pixels * red_dominance) / red_total)
    blue_centroid = float(np.sum(pixels * blue_dominance) / blue_total)

    if abs(red_centroid - blue_centroid) < min_separation_pixels:
        return None

    return red_centroid < blue_centroid


def detect_centre_row(
    gray_image: np.ndarray, smoothing_kernel_size: int = 11
) -> int:
    """Determine the sensor row (center_y) where the spectral band is centered.

    Simplified from v1's inlined dynamic tracking logic to a static one-shot calculation.
    """
    row_maxima = gray_image.max(axis=1)
    kernel = np.ones(smoothing_kernel_size) / smoothing_kernel_size
    row_smooth = np.convolve(row_maxima, kernel, mode="same")
    return int(np.argmax(row_smooth))


def run_startup_calibration(
    frame_source,
    n_frames: int = 4,
    band_half_height_for_flip_check: int = 25,
    min_separation_pixels: int = 30,
) -> dict:
    """Run the combined one-time developer-mode calibration routine."""
    # 1. Capture and average frames
    frames = [frame_source.capture_frame() for _ in range(n_frames)]
    avg_rgb = average_frames(frames)

    # 2. Greyscale conversion
    grey = to_greyscale(avg_rgb)

    # 3. Detect tilt angle
    tilt_angle_deg = detect_tilt(grey)

    # 4. Correct tilt on both grayscale and RGB frames
    tilted_grey = apply_tilt_correction(grey, tilt_angle_deg)
    tilted_rgb = np.stack(
        [
            apply_tilt_correction(avg_rgb[:, :, c], tilt_angle_deg)
            for c in range(3)
        ],
        axis=-1,
    )

    # 5. Detect brightest center row
    center_y = detect_centre_row(tilted_grey)

    # 6. Slices the RGB band for the flip check
    start_y = max(0, center_y - band_half_height_for_flip_check)
    end_y = min(tilted_rgb.shape[0], center_y + band_half_height_for_flip_check + 1)
    rgb_band_slice = tilted_rgb[start_y:end_y, :, :]

    # 7. Check if wavelength orientation is flipped
    flip_spectrum = detect_spectrum_flip(
        rgb_band_slice, min_separation_pixels
    )

    if flip_spectrum is None:
        raise CalibrationError(
            "Wavelength flip check was ambiguous. Please retry with a fuller-spectrum "
            "light source (e.g. CFL bulb) to establish clear red/blue centroids."
        )

    # 8. Return configuration parameters
    return {
        "tilt_angle_deg": tilt_angle_deg,
        "flip_spectrum": flip_spectrum,
        "center_y": center_y,
    }
