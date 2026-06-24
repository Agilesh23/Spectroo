# TODO: T11 — review threading model after hardware concurrency test
import time
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from spectroo.core.calibration import PolynomialCalibration
from spectroo.dsp.pipeline import run_pipeline, average_frames, to_greyscale, apply_tilt_correction
from spectroo.dsp.collapse import extract_band, apply_flip
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

            from spectroo.dsp.corrections import load_dark_frame, load_flat_field
            dark_path = self.config.get("storage", {}).get("dark_frame_path", "")
            flat_path = self.config.get("storage", {}).get("flat_field_path", "")
            dark_frame_1d = load_dark_frame(dark_path)
            response_flat = load_flat_field(flat_path)

            self._frame_source.set_exposure_us(
                self.config.get("camera", {}).get("exposure_us", 200000)
            )
            # allow camera to settle after exposure change
            time.sleep(0.5)

            while self._running:
                try:
                    frame = self._frame_source.get_frame() if hasattr(self._frame_source, "get_frame") else self._frame_source.capture_frame()

                    exposure_us = self.config.get("camera", {}).get("exposure_us", 200000)
                    spec = run_pipeline(
                        [frame],
                        optics,
                        dsp_cfg,
                        peaks_cfg,
                        exposure_us,
                        dark_frame_1d=dark_frame_1d,
                        response_flat=response_flat
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
                        "peaks": peak_indices,
                        "dark_frame_loaded": spec.dark_frame_loaded,
                        "flat_field_loaded": spec.flat_field_loaded
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
            self._frame_source.set_exposure_us(
                self.config.get("camera", {}).get("exposure_us", 200000)
            )
            time.sleep(0.5)  # allow camera to settle
            n_frames = self.config.get("camera", {}).get("frame_stack", 4)
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

            from spectroo.dsp.corrections import load_dark_frame, load_flat_field
            dark_path = self.config.get("storage", {}).get("dark_frame_path", "")
            flat_path = self.config.get("storage", {}).get("flat_field_path", "")
            dark_frame_1d = load_dark_frame(dark_path)
            response_flat = load_flat_field(flat_path)

            spec = run_pipeline(
                [averaged],
                optics,
                dsp_cfg,
                peaks_cfg,
                exposure_us,
                dark_frame_1d=dark_frame_1d,
                response_flat=response_flat
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
                "peaks": peak_indices,
                "dark_frame_loaded": spec.dark_frame_loaded,
                "flat_field_loaded": spec.flat_field_loaded
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


class FlatFieldWorker(QThread):
    """
    Captures a flat-field profile and saves it to disk.
    """
    # TODO: T11 — review threading model after hardware concurrency test
    finished = pyqtSignal(str)

    def __init__(self, config: dict, frame_source, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._frame_source = frame_source

    def run(self) -> None:
        try:
            import os
            import json
            import logging
            logger = logging.getLogger("spectroo")

            self._frame_source.set_exposure_us(
                self.config.get("camera", {}).get("exposure_us", 200000)
            )
            time.sleep(0.5)  # allow camera to settle

            n_frames = self.config.get("camera", {}).get("frame_stack", 4)
            frames = []
            for _ in range(n_frames):
                frame = self._frame_source.get_frame() if hasattr(self._frame_source, "get_frame") else self._frame_source.capture_frame()
                frames.append(frame)
                time.sleep(0.01)

            averaged = average_frames(frames)
            grey = to_greyscale(averaged)

            optics = self.config.get("optics", {})
            dsp_cfg = self.config.get("dsp", {})

            tilted = apply_tilt_correction(grey, optics.get("tilt_angle_deg", 0.0))
            band = extract_band(tilted, optics.get("center_y", 0), dsp_cfg.get("band_half_height", 15))
            profile = apply_flip(band, optics.get("flip_spectrum", False))

            # Subtract dark frame if it exists
            dark_path = self.config.get("storage", {}).get("dark_frame_path", "")
            if dark_path and os.path.exists(dark_path):
                try:
                    dark_frame = np.load(dark_path)
                    if dark_frame.ndim == 2:
                        dark_tilted = apply_tilt_correction(dark_frame, optics.get("tilt_angle_deg", 0.0))
                        dark_band = extract_band(dark_tilted, optics.get("center_y", 0), dsp_cfg.get("band_half_height", 15))
                        dark_frame_1d = apply_flip(dark_band, optics.get("flip_spectrum", False))
                    else:
                        dark_frame_1d = dark_frame
                    
                    from spectroo.dsp.corrections import subtract_dark
                    profile = subtract_dark(profile, dark_frame_1d)
                except Exception as e:
                    logger.warning(f"Failed to subtract dark frame: {e}")
            else:
                logger.warning("Dark frame not found, proceeding without dark subtraction.")

            # Clamp to prevent near-zero spikes downstream
            floor = np.mean(profile) * 0.05
            profile = np.clip(profile, floor, None)

            # Normalize by dividing by its mean
            mean_val = np.mean(profile)
            if mean_val <= 0:
                raise ValueError("Cannot normalize flat-field: mean intensity is zero or negative.")
            profile = profile / mean_val

            # Save as JSON array
            flat_path = self.config.get("storage", {}).get("flat_field_path", "data/response_flat.json")
            if flat_path:
                parent_dir = os.path.dirname(flat_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)
                with open(flat_path, "w") as f:
                    json.dump(profile.tolist(), f)
                self.finished.emit(f"Flat-field saved successfully to: {flat_path}")
            else:
                self.finished.emit("Flat-field path not specified in configuration.")
        except Exception as e:
            self.finished.emit(str(e))

