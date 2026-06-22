import numpy as np
import pytest
from spectroo.camera.startup_calibration import (
    detect_tilt,
    detect_spectrum_flip,
    detect_centre_row,
    run_startup_calibration,
)
from spectroo.core.exceptions import CalibrationError


# 1. test_detect_tilt_known_angle: diagonal bright band -> angle close to expected
def test_detect_tilt_known_angle():
    # 100 columns, 100 rows
    # slope = 0.2 (angle = arctan(0.2) * 180 / pi = 11.31 deg)
    # We use a band thicker than 1 pixel to prevent downsampling aliasing
    gray = np.ones((100, 100), dtype=np.uint8) * 10
    for c in range(100):
        r = int(c * 0.2 + 40)
        gray[max(0, r - 10) : min(100, r + 11), c] = 255
    angle = detect_tilt(gray)
    assert angle == pytest.approx(11.31, abs=2.0)


# 2. test_detect_tilt_zero_angle: horizontal bright band -> angle ~0.0
def test_detect_tilt_zero_angle():
    gray = np.ones((100, 100), dtype=np.uint8) * 10
    gray[40:61, :] = 255
    angle = detect_tilt(gray)
    assert angle == pytest.approx(0.0, abs=0.5)


# 3. test_detect_spectrum_flip_correct_orientation: blue-left/red-right -> False
def test_detect_spectrum_flip_correct_orientation():
    # band of size (10, 100, 3)
    rgb = np.ones((10, 100, 3), dtype=np.uint8) * 10
    # Left half blue-dominant
    rgb[:, :50, 2] = 200
    # Right half red-dominant
    rgb[:, 50:, 0] = 200
    res = detect_spectrum_flip(rgb, min_separation_pixels=10)
    assert res is False


# 4. test_detect_spectrum_flip_flipped_orientation: red-left/blue-right -> True
def test_detect_spectrum_flip_flipped_orientation():
    rgb = np.ones((10, 100, 3), dtype=np.uint8) * 10
    # Left half red-dominant
    rgb[:, :50, 0] = 200
    # Right half blue-dominant
    rgb[:, 50:, 2] = 200
    res = detect_spectrum_flip(rgb, min_separation_pixels=10)
    assert res is True


# 5. test_detect_spectrum_flip_ambiguous_returns_none: no color gradient -> None
def test_detect_spectrum_flip_ambiguous_returns_none():
    rgb = np.ones((10, 100, 3), dtype=np.uint8) * 10
    # Only green channel active, no red or blue
    rgb[:, :, 1] = 200
    res = detect_spectrum_flip(rgb, min_separation_pixels=10)
    assert res is None


# 6. test_detect_centre_row_known_position: brightest row at known index using peaking profile
def test_detect_centre_row_known_position():
    gray = np.ones((100, 100), dtype=np.uint8) * 10
    # Create symmetric peaking profile around 65
    for r in range(100):
        val = 255 - abs(r - 65) * 15
        gray[r, :] = max(10, int(val))
    center = detect_centre_row(gray, smoothing_kernel_size=5)
    assert center == pytest.approx(65, abs=1)


# 7. test_run_startup_calibration_happy_path: test-only FrameSource with tilt and correct colors
def test_run_startup_calibration_happy_path():
    class HappyFrameSource:
        def capture_frame(self):
            # 100x100 RGB frame
            frame = np.ones((100, 100, 3), dtype=np.uint8) * 10
            # Tilted band (slope 0.1, centered around row 45 at column 0)
            # Blue on the left (col < 50), red on the right (col >= 50)
            # Use peaking band profile to ensure unique peak detection
            for c in range(100):
                r = int(c * 0.1 + 45)
                for offset in range(-10, 11):
                    row = r + offset
                    if 0 <= row < 100:
                        val = 200 - abs(offset) * 15
                        if c < 50:
                            frame[row, c, 2] = max(10, int(val))  # Blue
                        else:
                            frame[row, c, 0] = max(10, int(val))  # Red
            return frame

    res = run_startup_calibration(
        HappyFrameSource(),
        n_frames=2,
        band_half_height_for_flip_check=5,
        min_separation_pixels=5,
    )
    assert isinstance(res, dict)
    assert "tilt_angle_deg" in res
    assert "flip_spectrum" in res
    assert "center_y" in res
    assert res["flip_spectrum"] is False
    # The rotated band aligns to the center of rotation (about row 50)
    assert res["center_y"] == pytest.approx(50, abs=2)


# 8. test_run_startup_calibration_raises_on_ambiguous_flip: raises CalibrationError
def test_run_startup_calibration_raises_on_ambiguous_flip():
    class AmbiguousFrameSource:
        def capture_frame(self):
            frame = np.ones((100, 100, 3), dtype=np.uint8) * 10
            for c in range(100):
                r = int(c * 0.1 + 45)
                for offset in range(-10, 11):
                    row = r + offset
                    if 0 <= row < 100:
                        val = 200 - abs(offset) * 15
                        frame[row, c, 1] = max(10, int(val))  # Green only
            return frame

    with pytest.raises(CalibrationError):
        run_startup_calibration(
            AmbiguousFrameSource(),
            n_frames=2,
            band_half_height_for_flip_check=5,
            min_separation_pixels=5,
        )
