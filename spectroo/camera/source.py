"""PiCameraFrameSource (RGB888) + MockFrameSource."""

from abc import ABC, abstractmethod
import logging
import numpy as np
from spectroo.core.exceptions import CameraNotFoundError

logger = logging.getLogger("spectroo.camera")


class FrameSource(ABC):
    """Abstract base class representing a camera frame source."""

    @abstractmethod
    def capture_frame(self) -> np.ndarray:
        """Capture a single frame from the source.

        Returns:
            np.ndarray of shape (H, W, 3), dtype uint8.
        """
        pass

    @abstractmethod
    def set_exposure_us(self, exposure_us: int) -> None:
        """Set the exposure time in microseconds."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release camera interface and cleanup resources."""
        pass


class MockFrameSource(FrameSource):
    """Synthetic frame generator for development/testing without real hardware."""

    def __init__(
        self,
        resolution: tuple[int, int] = (2592, 200),
        seed: int | None = None,
    ):
        """Initialize mock camera with resolution (width, height) and random seed."""
        self._width, self._height = resolution
        self._rng = np.random.default_rng(seed)
        self._exposure_us = 200000

    def capture_frame(self) -> np.ndarray:
        """Generate a synthetic 2D frame of shape (height, width, 3), dtype uint8."""
        w, h = self._width, self._height
        x = np.arange(w)
        y = np.arange(h)[:, np.newaxis]

        # Background baseline value
        frame = np.ones((h, w), dtype=float) * 10.0

        # 4 Gaussian-shaped intensity bumps
        fractions = [0.20, 0.45, 0.70, 0.90]
        sigma_x = 0.01 * w
        sigma_y = 0.1 * h if h > 1 else 1.0

        for frac in fractions:
            mu_x = frac * w
            mu_y = h / 2.0
            amp = self._rng.uniform(150.0, 255.0)

            g_x = np.exp(-((x - mu_x) ** 2) / (2.0 * sigma_x**2))
            g_y = np.exp(-((y - mu_y) ** 2) / (2.0 * sigma_y**2))
            frame += amp * g_y * g_x

        # Add small Gaussian noise
        noise = self._rng.normal(0.0, 3.0, (h, w))
        frame += noise

        # Clip and cast
        frame_clipped = np.clip(frame, 0, 255).astype(np.uint8)

        # Replicate to 3 channels (RGB)
        return np.stack([frame_clipped, frame_clipped, frame_clipped], axis=-1)

    def set_exposure_us(self, exposure_us: int) -> None:
        """Set the exposure value on the mock (stored without visual effect)."""
        self._exposure_us = exposure_us

    def close(self) -> None:
        """No-op cleanup."""
        pass


class PiCameraFrameSource(FrameSource):
    """Real hardware capture via picamera2/libcamera.

    Requests RGB888 directly to avoid manual Bayer/BGR handling.
    """

    def __init__(
        self,
        resolution: tuple[int, int] = (2592, 200),
        exposure_us: int = 200000,
    ):
        """Initialize Pi camera hardware interface.

        Import picamera2 dynamically to ensure importability on non-Pi systems.
        """
        try:
            import picamera2
        except ImportError as e:
            raise CameraNotFoundError(
                "picamera2 library is not installed or available on this system."
            ) from e

        try:
            self._picam2 = picamera2.Picamera2()
            config = self._picam2.create_still_configuration(
                main={"size": resolution, "format": "RGB888"}
            )
            self._picam2.configure(config)
            self._picam2.start()
            self._picam2.set_controls({"ExposureTime": exposure_us})
        except Exception as e:
            raise CameraNotFoundError(
                f"Failed to initialize Pi camera hardware on startup: {e}"
            ) from e

    def capture_frame(self) -> np.ndarray:
        """Return frame array from camera sensor."""
        return self._picam2.capture_array()

    def set_exposure_us(self, exposure_us: int) -> None:
        """Set camera sensor exposure time."""
        self._picam2.set_controls({"ExposureTime": exposure_us})

    def close(self) -> None:
        """Stop capture stream and release the camera device back to the camera manager."""
        try:
            self._picam2.stop()
        except Exception:
            logger.warning("Error stopping camera", exc_info=True)
        try:
            self._picam2.close()
        except Exception:
            logger.warning("Error closing camera", exc_info=True)
