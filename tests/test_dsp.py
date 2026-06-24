import numpy as np
import pytest
from spectroo.core.models import Spectrum, Peak
from spectroo.core.calibration import PolynomialCalibration
from spectroo.dsp.collapse import extract_band, apply_flip
from spectroo.dsp.corrections import subtract_dark, apply_flat_field
from spectroo.dsp.filters import smooth_savgol, subtract_baseline
from spectroo.dsp.peaks import find_spectrum_peaks
from spectroo.dsp.pipeline import (
    average_frames,
    to_greyscale,
    apply_tilt_correction,
    run_pipeline,
)


# 1. average_frames: 2 known small frames -> exact expected average
def test_average_frames():
    f1 = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    f2 = np.array([[3.0, 4.0], [5.0, 6.0]], dtype=np.float32)
    expected = np.array([[2.0, 3.0], [4.0, 5.0]], dtype=np.float32)
    actual = average_frames([f1, f2])
    np.testing.assert_array_equal(actual, expected)
    assert actual.dtype == np.float32


# 2. to_greyscale: one known RGB pixel -> exact expected luminance value
def test_to_greyscale():
    # Shape (1, 1, 3)
    rgb = np.array([[[100.0, 150.0, 200.0]]], dtype=np.float32)
    # L = 0.299*100 + 0.587*150 + 0.114*200 = 29.9 + 88.05 + 22.8 = 140.75
    expected = np.array([[140.75]], dtype=np.float32)
    actual = to_greyscale(rgb)
    np.testing.assert_array_almost_equal(actual, expected)
    assert actual.dtype == np.float32


# 3. apply_tilt_correction at angle=0.0 -> output shape equals input shape, and values unchanged
def test_apply_tilt_correction_zero_angle():
    frame = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    actual = apply_tilt_correction(frame, 0.0)
    assert actual.shape == frame.shape
    np.testing.assert_array_almost_equal(actual, frame)


# 4. extract_band: small known 2D array, known center_y/band_half_height -> exact expected averaged result
def test_extract_band():
    # 5 rows, 3 cols
    frame = np.array(
        [
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
            [7.0, 8.0, 9.0],
            [10.0, 11.0, 12.0],
            [13.0, 14.0, 15.0],
        ],
        dtype=np.float32,
    )
    # center_y = 2, half_height = 1 -> rows 1, 2, 3 (inclusive)
    # rows:
    # [4.0, 5.0, 6.0]
    # [7.0, 8.0, 9.0]
    # [10.0, 11.0, 12.0]
    # Column mean: [7.0, 8.0, 9.0]
    expected = np.array([7.0, 8.0, 9.0], dtype=np.float32)
    actual = extract_band(frame, center_y=2, band_half_height=1)
    np.testing.assert_array_equal(actual, expected)


# 5. apply_flip: True reverses, False leaves unchanged; assert original is not mutated
def test_apply_flip():
    arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)

    # False does not mutate and returns original unchanged reference
    out_false = apply_flip(arr, flip_spectrum=False)
    np.testing.assert_array_equal(out_false, arr)
    assert out_false is arr

    # True returns a new reversed copy
    out_true = apply_flip(arr, flip_spectrum=True)
    np.testing.assert_array_equal(
        out_true, np.array([3.0, 2.0, 1.0], dtype=np.float32)
    )
    assert out_true is not arr
    # assert original is not mutated
    np.testing.assert_array_equal(arr, np.array([1.0, 2.0, 3.0], dtype=np.float32))


# 6. subtract_dark: includes negative subtraction clipping to 0
def test_subtract_dark():
    intensity = np.array([10.0, 5.0, 2.0], dtype=np.float32)
    dark = np.array([3.0, 6.0, 1.0], dtype=np.float32)
    expected = np.array([7.0, 0.0, 1.0], dtype=np.float32)
    actual = subtract_dark(intensity, dark)
    np.testing.assert_array_equal(actual, expected)


# 7. apply_flat_field: near-zero response flat-field -> floor clipping applied
def test_apply_flat_field():
    intensity = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    flat = np.array([0.5, 0.0001, 1.0], dtype=np.float32)
    # floor = 0.001 -> clipped flat becomes [0.5, 0.001, 1.0]
    # division results -> [1.0/0.5, 2.0/0.001, 3.0/1.0] = [2.0, 2000.0, 3.0]
    expected = np.array([2.0, 2000.0, 3.0], dtype=np.float32)
    actual = apply_flat_field(intensity, flat, floor=0.001)
    np.testing.assert_allclose(actual, expected, rtol=1e-5)


# 8. smooth_savgol: shape preserved
def test_smooth_savgol():
    intensity = np.array(
        [1.0, 2.0, 5.0, 2.0, 1.0, 2.0, 5.0, 2.0, 1.0], dtype=np.float32
    )
    actual = smooth_savgol(intensity, window=5, polyorder=2)
    assert actual.shape == intensity.shape


# 9. subtract_baseline: both methods ("minimum_filter1d_sg" and "sg_only") -> shape preserved
def test_subtract_baseline():
    intensity = np.array(
        [
            1.0,
            2.0,
            5.0,
            6.0,
            5.0,
            2.0,
            1.0,
            0.0,
            1.0,
            2.0,
            5.0,
            2.0,
            1.0,
            0.5,
            0.5,
        ],
        dtype=np.float32,
    )

    out_sg = subtract_baseline(
        intensity, method="sg_only", window=5, polyorder=2
    )
    assert out_sg.shape == intensity.shape
    assert not np.array_equal(out_sg, intensity)

    out_min_sg = subtract_baseline(
        intensity, method="minimum_filter1d_sg", window=5, polyorder=2
    )
    assert out_min_sg.shape == intensity.shape
    assert not np.array_equal(out_min_sg, intensity)

    with pytest.raises(ValueError):
        subtract_baseline(
            intensity, method="invalid_method", window=5, polyorder=2
        )


# 10. find_spectrum_peaks: synthetic intensity array with one single peak
def test_find_spectrum_peaks():
    # Obvious peak at index 3
    intensity = np.array([1.0, 2.0, 3.0, 10.0, 3.0, 2.0, 1.0], dtype=np.float32)
    wavelengths = np.array(
        [400.0, 410.0, 420.0, 430.0, 440.0, 450.0, 460.0], dtype=np.float32
    )

    peaks = find_spectrum_peaks(
        intensity,
        wavelengths,
        prominence_pct=0.1,
        prominence_min=0.5,
        min_distance_px=2,
    )

    assert len(peaks) == 1
    assert peaks[0].pixel_index == 3
    assert peaks[0].intensity == pytest.approx(10.0)
    assert peaks[0].wavelength_nm == pytest.approx(430.0)
    assert peaks[0].prominence > 0.0


# 11. run_pipeline: basic run without dark/flat-field/calibration
def test_run_pipeline_basic():
    # Size 8x6x3
    f1 = np.ones((8, 6, 3), dtype=np.float32) * 10.0
    f2 = np.ones((8, 6, 3), dtype=np.float32) * 12.0
    # Obvious peak in the middle
    f1[4, 3, :] = 100.0
    f2[4, 3, :] = 100.0

    frames = [f1, f2]
    optics = {"tilt_angle_deg": 0.0, "center_y": 4, "flip_spectrum": False}
    dsp_cfg = {
        "band_half_height": 1,
        "savgol_window": 5,
        "savgol_polyorder": 2,
        "baseline_method": "sg_only",
        "baseline_window": 5,
        "baseline_polyorder": 2,
    }
    peaks_cfg = {
        "prominence_pct": 0.1,
        "prominence_min": 0.5,
        "min_distance_px": 2,
    }

    spec = run_pipeline(frames, optics, dsp_cfg, peaks_cfg, exposure_us=200000)

    assert isinstance(spec, Spectrum)
    assert spec.wavelengths is None
    assert spec.calibration_rms_at_capture is None
    assert spec.exposure_us == 200000
    assert len(spec.pixel_indices) == 6
    assert isinstance(spec.peaks, list)


# 12. run_pipeline: with calibration passed in
def test_run_pipeline_calibrated():
    f1 = np.ones((8, 6, 3), dtype=np.float32) * 10.0
    f2 = np.ones((8, 6, 3), dtype=np.float32) * 10.0
    frames = [f1, f2]
    optics = {"tilt_angle_deg": 0.0, "center_y": 4, "flip_spectrum": False}
    dsp_cfg = {
        "band_half_height": 1,
        "savgol_window": 5,
        "savgol_polyorder": 2,
        "baseline_method": "sg_only",
        "baseline_window": 5,
        "baseline_polyorder": 2,
    }
    peaks_cfg = {
        "prominence_pct": 0.1,
        "prominence_min": 0.5,
        "min_distance_px": 2,
    }

    # Linear calibration y = 2.0*x + 400.0
    cal = PolynomialCalibration(coefficients=[2.0, 400.0], degree=1, rms_nm=0.12)

    spec = run_pipeline(
        frames,
        optics,
        dsp_cfg,
        peaks_cfg,
        exposure_us=200000,
        calibration=cal,
    )

    assert spec.wavelengths is not None
    # 6 pixels, indices 0..5
    expected_wavelengths = 2.0 * np.arange(6) + 400.0
    np.testing.assert_array_almost_equal(spec.wavelengths, expected_wavelengths)
    assert spec.calibration_rms_at_capture == pytest.approx(0.12)


def test_corrections_loading_and_pipeline_flags(tmp_path):
    import json
    from spectroo.dsp.corrections import load_dark_frame, load_flat_field
    
    # Paths
    valid_dark_path = tmp_path / "valid_dark.npy"
    corrupt_dark_path = tmp_path / "corrupt_dark.npy"
    valid_flat_path = tmp_path / "valid_flat.json"
    corrupt_flat_path = tmp_path / "corrupt_flat.json"
    missing_path = tmp_path / "does_not_exist.ext"
    
    # 1. Prepare files
    # Valid dark (.npy)
    dummy_dark = np.ones(6, dtype=np.float32) * 5.0
    np.save(str(valid_dark_path), dummy_dark)
    
    # Corrupt dark (write garbage bytes)
    with open(corrupt_dark_path, "wb") as f:
        f.write(b"garbage data")
        
    # Valid flat (JSON array)
    dummy_flat = [1.0, 1.1, 0.9, 1.0, 1.2, 0.8]
    with open(valid_flat_path, "w") as f:
        json.dump(dummy_flat, f)
        
    # Corrupt flat (invalid JSON or invalid structure)
    with open(corrupt_flat_path, "w") as f:
        f.write("invalid json {")
        
    # 2. Test load functions
    # Valid files
    loaded_dark = load_dark_frame(str(valid_dark_path))
    assert loaded_dark is not None
    np.testing.assert_array_equal(loaded_dark, dummy_dark)
    
    loaded_flat = load_flat_field(str(valid_flat_path))
    assert loaded_flat is not None
    np.testing.assert_array_equal(loaded_flat, np.array(dummy_flat, dtype=np.float32))
    
    # Missing files
    assert load_dark_frame(str(missing_path)) is None
    assert load_flat_field(str(missing_path)) is None
    assert load_dark_frame("") is None
    assert load_flat_field("") is None
    
    # Corrupt files
    assert load_dark_frame(str(corrupt_dark_path)) is None
    assert load_flat_field(str(corrupt_flat_path)) is None
    
    # 3. Test run_pipeline flags with these loaded values
    f1 = np.ones((8, 6, 3), dtype=np.float32) * 10.0
    frames = [f1]
    optics = {"tilt_angle_deg": 0.0, "center_y": 4, "flip_spectrum": False}
    dsp_cfg = {
        "band_half_height": 1,
        "savgol_window": 5,
        "savgol_polyorder": 2,
        "baseline_method": "sg_only",
        "baseline_window": 5,
        "baseline_polyorder": 2,
    }
    peaks_cfg = {
        "prominence_pct": 0.1,
        "prominence_min": 0.5,
        "min_distance_px": 2,
    }
    
    # Case A: Both loaded successfully
    spec_both = run_pipeline(
        frames,
        optics,
        dsp_cfg,
        peaks_cfg,
        exposure_us=200000,
        dark_frame_1d=loaded_dark,
        response_flat=loaded_flat
    )
    assert spec_both.dark_frame_loaded is True
    assert spec_both.flat_field_loaded is True
    
    # Case B: Both missing/None
    spec_none = run_pipeline(
        frames,
        optics,
        dsp_cfg,
        peaks_cfg,
        exposure_us=200000,
        dark_frame_1d=None,
        response_flat=None
    )
    assert spec_none.dark_frame_loaded is False
    assert spec_none.flat_field_loaded is False
    
    # Case C: Only dark frame loaded
    spec_only_dark = run_pipeline(
        frames,
        optics,
        dsp_cfg,
        peaks_cfg,
        exposure_us=200000,
        dark_frame_1d=loaded_dark,
        response_flat=None
    )
    assert spec_only_dark.dark_frame_loaded is True
    assert spec_only_dark.flat_field_loaded is False
    
    # Case D: Only flat field loaded
    spec_only_flat = run_pipeline(
        frames,
        optics,
        dsp_cfg,
        peaks_cfg,
        exposure_us=200000,
        dark_frame_1d=None,
        response_flat=loaded_flat
    )
    assert spec_only_flat.dark_frame_loaded is False
    assert spec_only_flat.flat_field_loaded is True

