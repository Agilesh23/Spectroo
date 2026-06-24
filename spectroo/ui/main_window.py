import numpy as np
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog
from PyQt5.QtCore import Qt
import logging

logger = logging.getLogger("spectroo")

from spectroo.ui.plot_widget import SpectrumPlotWidget
from spectroo.ui.control_panel import ControlPanel
from spectroo.ui.status_bar import StatusBar
from spectroo.ui.workers import LivePipelineWorker, SingleAcquisitionWorker, DarkFrameWorker
from spectroo.storage.export import export_csv, export_json
from spectroo.core.models import HistoryRecord, Peak
from spectroo.ui.history_panel import HistoryPanel
from spectroo.storage.db import get_record



class SpectrooMainWindow(QMainWindow):
    """
    Main QMainWindow for user interaction.
    """

    def __init__(self, config: dict, parent=None, dev: bool = False) -> None:
        super().__init__(parent)
        self.config = config
        self._dev_mode = dev
        self.current_mode = "single"
        self.baseline_enabled = True
        self.current_spectrum = None

        self._dev_mode = True
        res = tuple(self.config.get("camera", {}).get("resolution", [2592, 200]))
        try:
            from spectroo.camera.source import PiCameraFrameSource
            self._frame_source = PiCameraFrameSource(resolution=res)
        except Exception:
            from spectroo.camera.source import MockFrameSource
            self._frame_source = MockFrameSource(resolution=res)

        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        self.dev_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self.dev_shortcut.activated.connect(self._open_dev_window)

        self.setWindowTitle("Spectroo")
        self.setMinimumSize(1000, 600)
        self.setStyleSheet("background-color: #ffffff;")

        # Layout assembly (exact structure from v1)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.plot_widget = SpectrumPlotWidget(self)
        self.control_panel = ControlPanel(self)

        content_layout.addWidget(self.plot_widget, stretch=1)
        content_layout.addWidget(self.control_panel)
        main_layout.addLayout(content_layout)

        self.history_panel = HistoryPanel(self.config, self)
        main_layout.insertWidget(1, self.history_panel)

        self.status_bar = StatusBar(self)
        main_layout.addWidget(self.status_bar)

        self._connect_signals()

    def _connect_signals(self) -> None:
        self.control_panel.mode_changed.connect(self._on_mode_changed)
        self.control_panel.start_requested.connect(self._on_start)
        self.control_panel.stop_requested.connect(self._on_stop)
        self.control_panel.exposure_changed.connect(self._on_exposure_changed)
        self.control_panel.plot_mode_changed.connect(self.plot_widget.set_fill_mode)
        self.control_panel.calibrate_requested.connect(self._on_calibrate)
        self.control_panel.dark_frame_requested.connect(self._on_dark_frame)
        self.control_panel.baseline_toggled.connect(self._on_baseline_toggled)
        self.control_panel.export_requested.connect(self._on_export)
        self.control_panel.save_chart_requested.connect(self._on_save_chart)
        self.control_panel.shutdown_requested.connect(self._on_shutdown)
        self.control_panel.history_toggled.connect(self._on_history_toggled)
        self.history_panel.record_selected.connect(self._on_history_record_selected)
        self.control_panel.save_clicked.connect(self._on_save_clicked)

    def _on_mode_changed(self, mode: str) -> None:
        self.current_mode = mode
        self._on_stop()
        self.control_panel.set_mode(mode)

    def _on_start(self) -> None:
        logger.info("Button clicked: Start | Mode: %s | Exposure: %s", self.current_mode, self.config.get("camera", {}).get("exposure_us"))
        self._on_stop()
        if self.current_mode == "single":
            self.control_panel.start_btn.setEnabled(False)
            self._acq_worker = SingleAcquisitionWorker(self.config, self)
            self._acq_worker.frame_ready.connect(self._on_frame_ready)
            self._acq_worker.error_occurred.connect(self._on_worker_error)
            self._acq_worker.finished.connect(self._acq_worker.deleteLater)
            self._acq_worker.finished.connect(
                lambda: self.control_panel.start_btn.setEnabled(True)
            )
            self._acq_worker.start()
        elif self.current_mode == "live":
            self.control_panel.start_btn.setEnabled(False)
            self.control_panel.stop_btn.setEnabled(True)
            self._live_worker = LivePipelineWorker(self.config, self)
            self._live_worker.frame_ready.connect(self._on_frame_ready)
            self._live_worker.error_occurred.connect(self._on_worker_error)
            self._live_worker.fps_updated.connect(
                lambda fps: self.status_bar.update_status({"fps": fps})
            )
            self._live_worker.start()

    def _on_stop(self) -> None:
        logger.info("Button clicked: Stop | Mode: %s", self.current_mode)
        if hasattr(self, "_live_worker") and self._live_worker:
            self._live_worker.stop()
            self._live_worker = None
        if hasattr(self, "_acq_worker") and self._acq_worker:
            try:
                self._acq_worker.quit()
                self._acq_worker.wait()
            except RuntimeError:
                pass
            self._acq_worker = None
        self.control_panel.start_btn.setEnabled(True)
        if self.current_mode == "single":
            self.control_panel.stop_btn.setEnabled(False)

    def _on_exposure_changed(self, exposure_us: int) -> None:
        self.config["camera"]["exposure_us"] = exposure_us

    def _on_baseline_toggled(self, enabled: bool) -> None:
        logger.info("Button clicked: Baseline Corr | Enabled: %s", enabled)
        self.baseline_enabled = enabled
        self.config["dsp"]["baseline_enabled"] = enabled

    def _on_calibrate(self) -> None:
        logger.info("Button clicked: Calibrate... | Dev Mode: %s", self._dev_mode)
        if self._dev_mode:
            self._open_dev_window()

    def _open_dev_window(self) -> None:
        from spectroo.ui.dev.calibration_window import CalibrationWindow
        cal_window = CalibrationWindow(self.config, self._frame_source, parent=self)
        cal_window.calibration_applied.connect(self._on_calibration_applied)
        cal_window.exec_()

    def _on_calibration_applied(self) -> None:
        from spectroo.core.config import load_config
        import os
        base_dir = os.path.abspath(os.path.dirname(__file__))
        config_path = "config.toml"
        for _ in range(5):
            if os.path.exists(os.path.join(base_dir, "config.toml")):
                config_path = os.path.join(base_dir, "config.toml")
                break
            base_dir = os.path.dirname(base_dir)

        try:
            new_config = load_config(config_path)
            self.config.clear()
            self.config.update(new_config)
        except Exception:
            pass

        calib_cfg = self.config.get("calibration", {})
        has_calib = bool(calib_cfg.get("coefficients", None))
        self.status_bar.update_status({"calibrated": has_calib})

    def _on_shutdown(self) -> None:
        logger.info("Button clicked: Shutdown")
        import subprocess
        self._on_stop()
        subprocess.run(["sudo", "shutdown", "-h", "now"])

    def _on_history_toggled(self) -> None:
        logger.info("Button clicked: History")
        self.history_panel._on_toggle()

    def closeEvent(self, event) -> None:
        self._on_stop()
        event.accept()

    def _on_history_record_selected(self, record_id: int) -> None:
        try:
            db_path = self.config.get("history", {}).get("db_path", "data/spectroo.db")
            record = get_record(db_path, record_id)
            if record is None:
                return
            wavelengths = np.array(record.wavelengths)
            intensities = np.array(record.intensities)
            peaks = [p.pixel_index for p in record.peaks] if record.peaks else []
            self.plot_widget.set_data(wavelengths, intensities, peaks)
            is_calibrated = (float(wavelengths[-1]) - float(wavelengths[0])) > 200
            peak_vals = [float(wavelengths[i]) for i in peaks if i < len(wavelengths)]
            self.status_bar.update_status({
                "calibrated": is_calibrated,
                "peaks": peak_vals,
            })
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "History", f"Could not load record: {e}")

    def _on_frame_ready(self, data: dict) -> None:
        wavelengths = data["wavelengths"]
        intensities = data["intensities"]
        peaks = data["peaks"]
        self.plot_widget.set_data(wavelengths, intensities, peaks)
        is_calibrated = (float(wavelengths[-1]) - float(wavelengths[0])) > 200
        peak_vals = [float(wavelengths[i]) for i in peaks if i < len(wavelengths)]
        self.status_bar.update_status({
            "calibrated": is_calibrated,
            "peaks": peak_vals,
        })
        dark_path = self.config.get("storage", {}).get("dark_frame_path", "")
        self.status_bar.update_status({"dark_loaded": bool(dark_path and __import__("os").path.exists(dark_path))})
        
        # Reconstruct Peak objects list from peak indices
        peaks_list = []
        for idx in peaks:
            if idx < len(intensities):
                wl = wavelengths[idx] if wavelengths is not None else None
                peaks_list.append(Peak(
                    pixel_index=int(idx),
                    wavelength_nm=wl,
                    intensity=float(intensities[idx]),
                    prominence=0.0
                ))
                
        from spectroo.core.models import Spectrum
        self.current_spectrum = Spectrum(
            pixel_indices=np.arange(len(intensities)),
            intensity=np.array(intensities),
            wavelengths=np.array(wavelengths) if wavelengths is not None else None,
            exposure_us=self.config.get("camera", {}).get("exposure_us", 200000),
            peaks=peaks_list,
            calibration_rms_at_capture=None,
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        )

    def _on_worker_error(self, message: str) -> None:
        self.control_panel.start_btn.setEnabled(True)
        QMessageBox.critical(self, "Acquisition Error", message)

    def _on_dark_frame(self) -> None:
        logger.info("Button clicked: Capture Dark Frame | Exposure: %s", self.config.get("camera", {}).get("exposure_us"))
        QMessageBox.information(
            self,
            "Capture Dark Frame",
            "Cover the lens completely to block all light, then click OK."
        )
        self._dark_worker = DarkFrameWorker(self.config, self)
        self._dark_worker.finished.connect(self._on_dark_frame_finished)
        self._dark_worker.start()

    def _on_dark_frame_finished(self, message: str) -> None:
        QMessageBox.information(self, "Dark Frame", message)
        dark_path = self.config.get("storage", {}).get("dark_frame_path", "")
        self.status_bar.update_status({"dark_loaded": bool(dark_path and __import__("os").path.exists(dark_path))})
        self._dark_worker.deleteLater()

    def _on_export(self) -> None:
        logger.info("Button clicked: Export JSON")
        wavelengths = self.plot_widget.wavelengths
        intensities = self.plot_widget.intensities
        if wavelengths is None or intensities is None:
            QMessageBox.warning(self, "Export", "No spectrum data to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export", "", "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        try:
            peaks_list = []
            if hasattr(self.plot_widget, "peaks") and self.plot_widget.peaks:
                for idx in self.plot_widget.peaks:
                    if idx < len(intensities):
                        wl = wavelengths[idx] if wavelengths is not None else None
                        peaks_list.append(Peak(pixel_index=int(idx), wavelength_nm=wl, intensity=float(intensities[idx]), prominence=0.0))

            record = HistoryRecord(
                id=None,
                timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                exposure_us=self.config.get("camera", {}).get("exposure_us", 200000),
                pixel_indices=list(range(len(intensities))),
                intensity=list(map(float, intensities)),
                wavelengths=list(map(float, wavelengths)) if wavelengths is not None else None,
                peaks=peaks_list,
                png_path="",
                calibration_rms_at_capture=None
            )

            if path.endswith(".csv"):
                export_csv(record, path)
            else:
                export_json(record, path)
            QMessageBox.information(self, "Export", f"Saved to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _on_save_chart(self) -> None:
        logger.info("Button clicked: Save Chart")
        path, _ = QFileDialog.getSaveFileName(self, "Save Chart", "", "PNG (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            try:
                self.plot_widget.grab().save(path, "PNG")
                QMessageBox.information(self, "Save Chart", f"Saved to {path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Chart Failed", str(e))

    def save_spectrum(self) -> None:
        if self.current_spectrum is None:
            return
        try:
            from spectroo.storage.db import save_record, init_db
            db_path = self.config.get("history", {}).get("db_path", "data/spectroo.db")
            max_entries = self.config.get("history", {}).get("max_entries", 500)
            try:
                init_db(db_path)
            except Exception:
                pass
            
            spec = self.current_spectrum
            record = HistoryRecord(
                id=None,
                timestamp=spec.timestamp,
                exposure_us=spec.exposure_us,
                pixel_indices=list(spec.pixel_indices),
                intensity=list(map(float, spec.intensity)),
                wavelengths=list(map(float, spec.wavelengths)) if spec.wavelengths is not None else None,
                peaks=spec.peaks,
                png_path="",
                calibration_rms_at_capture=spec.calibration_rms_at_capture
            )
            save_record(db_path, record, max_entries=max_entries)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _on_save_clicked(self) -> None:
        logger.info("Button clicked: Save Spectrum")
        if self.current_spectrum is None:
            import logging
            logging.getLogger("spectroo.ui").warning("No spectrum to save.")
            return
        self.save_spectrum()
        self.history_panel.refresh()
