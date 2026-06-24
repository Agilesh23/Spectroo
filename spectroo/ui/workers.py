# TODO: T11 — review threading model after hardware concurrency test
import time
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from spectroo.core.calibration import PolynomialCalibration
from spectroo.dsp.pipeline import run_pipeline, average_frames, to_greyscale
from spectroo.dsp.peaks import find_spectrum_peaks

if not hasattr(PolynomialCalibration, "evaluate"):
    PolynomialCalibration.evaluate = lambda self, x: np.polyval(self.coefficients, x)


class LivePipelineWorker(QThread):
    """
    Runs the live capture loop in a background thread.
    """
    # TODO: T11 — review threading model after hardware concurrency test
    frame_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    fps_updated = pyqtSignal(float)

    def __init__(self, config: dict, frame_source, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._frame_source = frame_source
        self._running = False
        self.frame_times = []

        N = config.get("camera", {}).get("resolution", [2592, 200])[0]
        cal_coefs = config.get("calibration", {}).get("coefficients", None)
        if cal_coefs:
            cal = PolynomialCalibration(coefficients=cal_coefs, degree=len(cal_coefs)-1, rms_nm=0.0)
            self._wavelengths = cal.evaluate(np.arange(N))
        else:
            self._wavelengths = np.arange(N)

    def run(self) -> None:
        self._running = True
        self.frame_times = []
        try:
            optics = self.config.get("optics", {})
            dsp_cfg = self.config.get("dsp", {})
            peaks_cfg = self.config.get("peaks", {})

            # Load 1D dark frame if path exists
            dark_path = self.config.get("storage", {}).get("dark_frame_path", "")
            dark_frame_1d = None
            if dark_path and __import__("os").path.exists(dark_path):
                try:
                    dark_frame_1d = np.load(dark_path)
                except Exception:
                    pass

            while self._running:
                try:
                    self._frame_source.set_exposure_us(self.config.get("camera", {}).get("exposure_us", 200000))
                    frame = self._frame_source.get_frame() if hasattr(self._frame_source, "get_frame") else self._frame_source.capture_frame()

                    exposure_us = self.config.get("camera", {}).get("exposure_us", 200000)
                    spec = run_pipeline(
                        [frame],
                        optics,
                        dsp_cfg,
                        peaks_cfg,
                        exposure_us,
                        dark_frame_1d=dark_frame_1d
                    )
                    intensities = spec.intensity

                    peaks = find_spectrum_peaks(
                        intensities,
                        self._wavelengths,
                        peaks_cfg.get("prominence_pct", 0.10),
                        peaks_cfg.get("prominence_min", 0.01),
                        peaks_cfg.get("min_distance_px", 20)
                    )
                    peak_indices = [p.pixel_index for p in peaks]

                    self.frame_ready.emit({
                        "wavelengths": self._wavelengths,
                        "intensities": intensities,
                        "peaks": peak_indices
                    })

                    now = time.time()
                    self.frame_times.append(now)
                    if len(self.frame_times) > 15:
                        self.frame_times.pop(0)

                    if len(self.frame_times) > 1:
                        duration = self.frame_times[-1] - self.frame_times[0]
                        if duration > 0:
                            fps = (len(self.frame_times) - 1) / duration
                            self.fps_updated.emit(fps)

                    time.sleep(0.005)
                except Exception as e:
                    self.error_occurred.emit(str(e))
                    break
        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self) -> None:
        self._running = False
        self.wait()


class SingleAcquisitionWorker(QThread):
    """
    Captures one averaged spectrum on demand.
    """
    # TODO: T11 — review threading model after hardware concurrency test
    frame_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, config: dict, frame_source, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._frame_source = frame_source

        N = config.get("camera", {}).get("resolution", [2592, 200])[0]
        cal_coefs = config.get("calibration", {}).get("coefficients", None)
        if cal_coefs:
            cal = PolynomialCalibration(coefficients=cal_coefs, degree=len(cal_coefs)-1, rms_nm=0.0)
            self._wavelengths = cal.evaluate(np.arange(N))
        else:
            self._wavelengths = np.arange(N)

    def run(self) -> None:
        try:
            n_frames = self.config.get("camera", {}).get("n_frames", 4)
            frames = []
            for _ in range(n_frames):
                frame = self._frame_source.get_frame() if hasattr(self._frame_source, "get_frame") else self._frame_source.capture_frame()
                frames.append(frame)
                time.sleep(0.01)

            averaged = average_frames(frames)

            optics = self.config.get("optics", {})
            dsp_cfg = self.config.get("dsp", {})
            peaks_cfg = self.config.get("peaks", {})
            exposure_us = self.config.get("camera", {}).get("exposure_us", 200000)

            dark_path = self.config.get("storage", {}).get("dark_frame_path", "")
            dark_frame_1d = None
            if dark_path and __import__("os").path.exists(dark_path):
                try:
                    dark_frame_1d = np.load(dark_path)
                except Exception:
                    pass

            spec = run_pipeline(
                [averaged],
                optics,
                dsp_cfg,
                peaks_cfg,
                exposure_us,
                dark_frame_1d=dark_frame_1d
            )
            intensities = spec.intensity

            peaks = find_spectrum_peaks(
                intensities,
                self._wavelengths,
                peaks_cfg.get("prominence_pct", 0.10),
                peaks_cfg.get("prominence_min", 0.01),
                peaks_cfg.get("min_distance_px", 20)
            )
            peak_indices = [p.pixel_index for p in peaks]

            self.frame_ready.emit({
                "wavelengths": self._wavelengths,
                "intensities": intensities,
                "peaks": peak_indices
            })
        except Exception as e:
            self.error_occurred.emit(str(e))


class DarkFrameWorker(QThread):
    """
    Captures a dark frame and saves it to disk.
    """
    # TODO: T11 — review threading model after hardware concurrency test
    finished = pyqtSignal(str)

    def __init__(self, config: dict, frame_source, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._frame_source = frame_source

    def run(self) -> None:
        try:
            frames = []
            for _ in range(4):
                frame = self._frame_source.get_frame() if hasattr(self._frame_source, "get_frame") else self._frame_source.capture_frame()
                frames.append(frame)
                time.sleep(0.01)

            averaged = average_frames(frames)
            grey = to_greyscale(averaged)

            dark_path = self.config.get("storage", {}).get("dark_frame_path", "")
            if dark_path:
                parent_dir = __import__("os").path.dirname(dark_path)
                if parent_dir:
                    __import__("os").makedirs(parent_dir, exist_ok=True)
                np.save(dark_path, grey)
                self.finished.emit(f"Dark frame saved successfully to: {dark_path}")
            else:
                self.finished.emit("Dark frame path not specified in configuration.")
        except Exception as e:
            self.finished.emit(str(e))
