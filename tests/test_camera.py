import numpy as np
import pytest
from spectroo.camera.source import MockFrameSource, PiCameraFrameSource
from spectroo.core.exceptions import CameraNotFoundError


# 1. test_mock_frame_source_shape_and_dtype: resolution (40, 20) -> (20, 40, 3) uint8
def test_mock_frame_source_shape_and_dtype():
    # resolution argument in MockFrameSource is (width, height)
    src = MockFrameSource(resolution=(40, 20))
    frame = src.capture_frame()
    # Output shape should be (height, width, 3)
    assert frame.shape == (20, 40, 3)
    assert frame.dtype == np.uint8


# 2. test_mock_frame_source_deterministic_with_seed: identical seeds -> identical frames
def test_mock_frame_source_deterministic_with_seed():
    src1 = MockFrameSource(resolution=(100, 50), seed=42)
    src2 = MockFrameSource(resolution=(100, 50), seed=42)
    f1 = src1.capture_frame()
    f2 = src2.capture_frame()
    assert np.array_equal(f1, f2)


# 3. test_mock_frame_source_different_seeds_differ: seed=1 vs seed=2 -> different frames
def test_mock_frame_source_different_seeds_differ():
    src1 = MockFrameSource(resolution=(100, 50), seed=1)
    src2 = MockFrameSource(resolution=(100, 50), seed=2)
    f1 = src1.capture_frame()
    f2 = src2.capture_frame()
    assert not np.array_equal(f1, f2)


# 4. test_mock_frame_source_set_exposure_no_error: calling set_exposure_us doesn't raise
def test_mock_frame_source_set_exposure_no_error():
    src = MockFrameSource()
    # Should run cleanly without raising errors
    src.set_exposure_us(100000)
    src.close()


# 5. test_pi_camera_frame_source_raises_when_unavailable: raises CameraNotFoundError on Windows
def test_pi_camera_frame_source_raises_when_unavailable():
    with pytest.raises(CameraNotFoundError):
        PiCameraFrameSource()
