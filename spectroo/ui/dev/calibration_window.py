import math
import inspect
import os
import numpy as np
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QDialog, QTableWidget, QTableWidgetItem, QPushButton,
    QVBoxLayout, QHBoxLayout, QMessageBox, QInputDialog, QHeaderView, QLabel,
    QSpinBox, QLineEdit
)
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QPolygonF, QFont

from spectroo.core.models import CalibrationPoint
from spectroo.core.calibration import fit_calibration
from spectroo.core.exceptions import CalibrationError
from spectroo.dsp.collapse import extract_band, apply_flip


class CalibrationCanvas(QWidget):
    """
    Custom widget using QPainter to display raw spectrum intensities,
    dashed calibration lines, and the red fitted polynomial curve.
    Supports zoom and pan on the pixel horizontal axis.
    """
    point_clicked = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._intensities = None
        self._points = []
        self._fit_curve = None

        # Margins matching SpectrooPlotWidget layout
        self.margin_left = 65
        self.margin_right = 65  # Enlarged to display secondary Y axis ticks/labels
        self.margin_top = 35
        self.margin_bottom = 50

        # Zoom & pan state
        self.zoom_xmin = None
        self.zoom_xmax = None
        self._pan_active = False
        self._pan_start_x = None
        self._pan_start_zoom = None

        self.setFocusPolicy(Qt.StrongFocus)

    def set_spectrum(self, intensities: np.ndarray) -> None:
        self._intensities = np.array(intensities)
        self.update()

    def set_calibration_points(self, points: list[CalibrationPoint]) -> None:
        self._points = list(points)
        self.update()

    def set_fit_curve(self, wavelengths: np.ndarray | None) -> None:
        if wavelengths is not None:
            self._fit_curve = np.array(wavelengths)
        else:
            self._fit_curve = None
        self.update()

    def reset_zoom(self) -> None:
        self.zoom_xmin = None
        self.zoom_xmax = None
        self.update()

    def _get_zoom_range(self) -> tuple[float, float]:
        full_max = float(len(self._intensities) - 1) if (self._intensities is not None and len(self._intensities) > 0) else 511.0
        xmin = self.zoom_xmin if self.zoom_xmin is not None else 0.0
        xmax = self.zoom_xmax if self.zoom_xmax is not None else full_max
        return (xmin, xmax)

    def wheelEvent(self, event) -> None:
        if self._intensities is None or len(self._intensities) == 0:
            return
        delta = event.angleDelta().y()
        factor = 0.8 if delta > 0 else 1.25
        xmin, xmax = self._get_zoom_range()
        plot_w = self.width() - self.margin_left - self.margin_right
        if plot_w <= 0:
            return
        mouse_x = event.x() - self.margin_left
        t = max(0.0, min(1.0, mouse_x / plot_w))
        center = xmin + t * (xmax - xmin)
        new_half = (xmax - xmin) * factor / 2
        full_min = 0.0
        full_max = float(len(self._intensities) - 1)
        new_min = max(full_min, center - new_half)
        new_max = min(full_max, center + new_half)
        if new_max - new_min < 5:
            return
        if new_min <= full_min and new_max >= full_max:
            self.zoom_xmin = None
            self.zoom_xmax = None
        else:
            self.zoom_xmin = new_min
            self.zoom_xmax = new_max
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._intensities is None or len(self._intensities) == 0:
            return
        if self._pan_active and self._pan_start_zoom is not None:
            dx = event.x() - self._pan_start_x
            xmin0, xmax0 = self._pan_start_zoom
            plot_w = self.width() - self.margin_left - self.margin_right
            data_per_px = (xmax0 - xmin0) / plot_w if plot_w > 0 else 1
            shift = -dx * data_per_px
            full_min = 0.0
            full_max = float(len(self._intensities) - 1)
            rng = xmax0 - xmin0
            new_min = max(full_min, xmin0 + shift)
            new_max = new_min + rng
            if new_max > full_max:
                new_max = full_max
                new_min = new_max - rng
            self.zoom_xmin = new_min
            self.zoom_xmax = new_max
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._pan_active = False

    def mouseDoubleClickEvent(self, event) -> None:
        self.reset_zoom()

    def mousePressEvent(self, event) -> None:
        if self._intensities is None or len(self._intensities) == 0:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.RightButton:
            self.reset_zoom()
            return

        # Check for drag pan keys
        is_pan_click = (event.button() == Qt.MidButton) or (
            event.button() == Qt.LeftButton and bool(event.modifiers() & Qt.ControlModifier)
        )
        if is_pan_click:
            self._pan_active = True
            self._pan_start_x = event.x()
            self._pan_start_zoom = self._get_zoom_range()
            return

        if event.button() == Qt.LeftButton:
            x_start = self.margin_left
            plot_w = self.width() - self.margin_left - self.margin_right
            if plot_w <= 0:
                return

            click_x = event.x()
            if click_x < x_start:
                click_x = x_start
            elif click_x > x_start + plot_w:
                click_x = x_start + plot_w

            xmin, xmax = self._get_zoom_range()
            frac = (click_x - x_start) / float(plot_w)
            target = xmin + frac * (xmax - xmin)

            pixel = int(round(target))
            full_max = len(self._intensities) - 1
            pixel = max(0, min(full_max, pixel))
            self.point_clicked.emit(pixel)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Clear background
        painter.fillRect(self.rect(), Qt.white)

        # Layout boundaries
        x_start = self.margin_left
        x_end = self.width() - self.margin_right
        y_start = self.margin_top
        y_end = self.height() - self.margin_bottom
        plot_w = x_end - x_start
        plot_h = y_end - y_start

        if plot_w <= 0 or plot_h <= 0:
            return

        # Draw axis bounding box
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawRect(x_start, y_start, plot_w, plot_h)

        if self._intensities is None or len(self._intensities) == 0:
            painter.setFont(QFont("Arial", 11))
            painter.drawText(QRectF(x_start, y_start, plot_w, plot_h), Qt.AlignCenter, "Awaiting Frame Data...")
            return

        # Y scaling for intensity counts
        y_max = max(1.0, float(np.max(self._intensities)))
        y_limit = y_max * 1.15

        # Horizontal zoom range (in pixels)
        x_min, x_max = self._get_zoom_range()

        # Left Y-axis label (Intensity)
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.setPen(QPen(QColor("#333333"), 1))
        painter.save()
        painter.translate(x_start - 48, y_start + plot_h / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-100, -10, 200, 20), Qt.AlignCenter, "Intensity (Counts)")
        painter.restore()

        # X-axis label (Pixel index)
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.setPen(QPen(QColor("#333333"), 1))
        painter.drawText(QRectF(x_start, y_end + 28, plot_w, 20), Qt.AlignCenter, "Pixel Index")

        # Draw X ticks & vertical gridlines
        painter.setFont(QFont("Arial", 8))
        range_x = x_max - x_min
        if range_x > 0:
            step = max(1.0, math.ceil(range_x / 6.0))
        else:
            step = 1.0

        start_tick = math.ceil(x_min / step) * step
        while start_tick <= x_max:
            px = x_start + (start_tick - x_min) / (x_max - x_min) * plot_w
            if x_start <= px <= x_end:
                # Vertical grid line
                painter.setPen(QPen(QColor("#eeeeee"), 1))
                painter.drawLine(QPointF(px, y_start), QPointF(px, y_end))
                # Tick line
                painter.setPen(QPen(QColor("#555555"), 1))
                painter.drawLine(QPointF(px, y_end), QPointF(px, y_end + 5))
                # Tick label
                painter.setPen(QPen(QColor("#333333"), 1))
                painter.drawText(QRectF(px - 30, y_end + 8, 60, 20), Qt.AlignCenter, f"{int(start_tick)}")
            start_tick += step

        # Draw Left Y ticks & horizontal gridlines
        y_ticks = [i * (y_limit / 4.0) for i in range(5)]
        for y_val in y_ticks:
            py = y_end - (y_val / y_limit) * plot_h
            # Horizontal grid line
            painter.setPen(QPen(QColor("#eeeeee"), 1))
            painter.drawLine(QPointF(x_start, py), QPointF(x_end, py))
            # Tick mark
            painter.setPen(QPen(QColor("#555555"), 1))
            painter.drawLine(QPointF(x_start - 5, py), QPointF(x_start, py))
            # Tick label
            painter.setPen(QPen(QColor("#333333"), 1))
            painter.drawText(QRectF(x_start - 55, py - 10, 48, 20), Qt.AlignRight | Qt.AlignVCenter, f"{int(round(y_val))}")

        # Draw vertical lines for calibration points
        for pt in self._points:
            pixel_idx = getattr(pt, "pixel_index", getattr(pt, "pixel", 0))
            wl_nm = getattr(pt, "known_wavelength_nm", getattr(pt, "wavelength", 0.0))
            px = x_start + (pixel_idx - x_min) / (x_max - x_min) * plot_w
            if x_start <= px <= x_end:
                # Dashed vertical line
                painter.setPen(QPen(QColor("#3366cc"), 1.5, Qt.DashLine))
                painter.drawLine(QPointF(px, y_start), QPointF(px, y_end))
                # Wavelength label above the peak line
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.setPen(QPen(QColor("#333333"), 1))
                painter.drawText(QRectF(px - 40, y_start + 5, 80, 15), Qt.AlignCenter, f"{wl_nm:.1f} nm")

        # Draw right Y-axis and fitted curve (red) if fit exists
        if self._fit_curve is not None and len(self._fit_curve) > 0:
            w_vals = list(self._fit_curve)
            if self._points:
                w_vals.extend([getattr(p, "known_wavelength_nm", getattr(p, "wavelength", 0.0)) for p in self._points])
            w_min = float(np.min(w_vals))
            w_max = float(np.max(w_vals))
            if w_max == w_min:
                w_max = w_min + 1.0
            w_range = w_max - w_min
            w_limit_min = w_min - 0.05 * w_range
            w_limit_max = w_max + 0.05 * w_range

            # Right Y-axis label (Wavelength)
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            painter.setPen(QPen(Qt.red, 1))
            painter.save()
            painter.translate(x_end + 48, y_start + plot_h / 2)
            painter.rotate(90)
            painter.drawText(QRectF(-100, -10, 200, 20), Qt.AlignCenter, "Fitted Wavelength (nm)")
            painter.restore()

            # Right Y ticks
            w_ticks = [w_limit_min + i * ((w_limit_max - w_limit_min) / 4.0) for i in range(5)]
            for w_val in w_ticks:
                py = y_end - ((w_val - w_limit_min) / (w_limit_max - w_limit_min)) * plot_h
                painter.setPen(QPen(Qt.red, 1))
                painter.drawLine(QPointF(x_end, py), QPointF(x_end + 5, py))
                painter.setPen(QPen(QColor("#333333"), 1))
                painter.drawText(QRectF(x_end + 8, py - 10, 48, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{w_val:.1f}")

            # Draw Red Fitted Curve
            painter.save()
            painter.setClipRect(x_start, y_start, plot_w, plot_h)
            fit_points = []
            for idx in range(len(self._fit_curve)):
                if x_min <= idx <= x_max:
                    cx = x_start + (idx - x_min) / (x_max - x_min) * plot_w
                    cy = y_end - ((self._fit_curve[idx] - w_limit_min) / (w_limit_max - w_limit_min)) * plot_h
                    fit_points.append(QPointF(cx, cy))

            if len(fit_points) > 1:
                painter.setPen(QPen(Qt.red, 2, Qt.SolidLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawPolyline(QPolygonF(fit_points))
            painter.restore()

        # Draw 1D spectrum curve (grey)
        painter.save()
        painter.setClipRect(x_start, y_start, plot_w, plot_h)
        curve_points = []
        for idx in range(len(self._intensities)):
            if x_min <= idx <= x_max:
                cx = x_start + (idx - x_min) / (x_max - x_min) * plot_w
                cy = y_end - (self._intensities[idx] / y_limit) * plot_h
                curve_points.append(QPointF(cx, cy))

        if len(curve_points) > 1:
            painter.setPen(QPen(QColor("#444444"), 2, Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolyline(QPolygonF(curve_points))
        painter.restore()


class CalibrationPointsTable(QWidget):
    """
    Table widget wrapping QTableWidget with Pixel, λ (nm), and Delete columns.
    Emits point_deleted signal when individual row delete buttons are clicked.
    """
    point_deleted = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Pixel", "λ (nm)", "Delete"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

    def add_point(self, point: CalibrationPoint) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        pixel = getattr(point, "pixel_index", getattr(point, "pixel", 0))
        wavelength = getattr(point, "known_wavelength_nm", getattr(point, "wavelength", 0.0))

        # Pixel item
        pixel_item = QTableWidgetItem(str(pixel))
        pixel_item.setFlags(pixel_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, pixel_item)

        # Wavelength item
        wl_item = QTableWidgetItem(f"{wavelength:.1f}")
        wl_item.setFlags(wl_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 1, wl_item)

        # Delete button cell
        del_btn = QPushButton("Delete", self)
        del_btn.setStyleSheet(
            "QPushButton { background-color: #ff4444; color: white; border: none; padding: 4px; border-radius: 2px; }"
            "QPushButton:hover { background-color: #cc0000; }"
        )
        del_btn.clicked.connect(lambda _, p=pixel: self.point_deleted.emit(p))
        self.table.setCellWidget(row, 2, del_btn)

    def remove_last(self) -> None:
        row_count = self.table.rowCount()
        if row_count > 0:
            self.table.removeRow(row_count - 1)

    def clear_points(self) -> None:
        self.table.setRowCount(0)


class CalibrationWindow(QDialog):
    """
    Main developer window for calibrating pixel to wavelength mapping.
    Contains layout: Left = Live spectrum plot + reset zoom. Right = Point list + action controls.
    """
    calibration_applied = pyqtSignal()

    def __init__(self, config: dict, frame_source, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._frame_source = frame_source
        self._points = []
        self._fit_result = None
        self._current_intensities = None

        self.setWindowTitle("Spectroo — Developer Calibration")
        self.setMinimumSize(900, 450)
        self.setStyleSheet("background-color: #ffffff;")

        # Primary horizontal split layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Left Panel (Live Canvas + Reset Zoom)
        left_layout = QVBoxLayout()
        left_layout.setSpacing(10)
        self.canvas = CalibrationCanvas(self)
        self.canvas.point_clicked.connect(self._on_canvas_click)
        left_layout.addWidget(self.canvas, stretch=1)

        exposure_layout = QHBoxLayout()
        exposure_label = QLabel("Exposure (µs):", self)
        self._exposure_input = QLineEdit(self)
        self._exposure_input.setFixedWidth(100)
        self._exposure_input.setText(str(self._config.get("camera", {}).get("exposure_us", 200000)))
        
        apply_exposure_btn = QPushButton("Apply", self)
        apply_exposure_btn.setFixedWidth(80)
        apply_exposure_btn.setFixedHeight(34)
        apply_exposure_btn.setStyleSheet(
            "QPushButton { background-color: #374151; color: white; border: none; "
            "font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1f2937; }"
        )
        apply_exposure_btn.clicked.connect(self._on_apply_exposure)
        
        exposure_layout.addWidget(exposure_label)
        exposure_layout.addWidget(self._exposure_input)
        exposure_layout.addWidget(apply_exposure_btn)
        exposure_layout.addStretch()
        left_layout.addLayout(exposure_layout)

        reset_zoom_layout = QHBoxLayout()
        reset_zoom_btn = QPushButton("Reset Zoom", self)
        reset_zoom_btn.setFixedHeight(34)
        reset_zoom_btn.setFixedWidth(120)
        reset_zoom_btn.setStyleSheet(
            "QPushButton { background-color: #374151; color: white; border: none; "
            "font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1f2937; }"
        )
        reset_zoom_btn.clicked.connect(self.canvas.reset_zoom)
        reset_zoom_layout.addWidget(reset_zoom_btn)
        reset_zoom_layout.addStretch()
        left_layout.addLayout(reset_zoom_layout)
        
        main_layout.addLayout(left_layout, stretch=2)

        # Right Panel (Points Table + Fit/Undo/Apply)
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)

        right_layout.addWidget(QLabel("Calibration Points:", self))
        self.table = CalibrationPointsTable(self)
        self.table.point_deleted.connect(self._delete_point)
        right_layout.addWidget(self.table, stretch=1)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 12px; color: #4b5563; font-weight: bold;")
        right_layout.addWidget(self.status_label)

        # Control button block
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        run_fit_btn = QPushButton("Run Fit", self)
        run_fit_btn.setFixedHeight(34)
        run_fit_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; border: none; "
            "font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
        )
        run_fit_btn.clicked.connect(self._on_run_fit)
        btn_layout.addWidget(run_fit_btn)

        undo_btn = QPushButton("Undo Last", self)
        undo_btn.setFixedHeight(34)
        undo_btn.setStyleSheet(
            "QPushButton { background-color: #6b7280; color: white; border: none; "
            "font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #4b5563; }"
        )
        undo_btn.clicked.connect(self._on_undo)
        btn_layout.addWidget(undo_btn)

        apply_btn = QPushButton("Apply & Close", self)
        apply_btn.setFixedHeight(34)
        apply_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: white; border: none; "
            "font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #15803d; }"
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        right_layout.addLayout(btn_layout)
        main_layout.addLayout(right_layout, stretch=1)

        # Locate config.toml's directory and resolve the calibration_state_path
        base_dir = os.path.abspath(os.path.dirname(__file__))
        config_dir = base_dir
        for _ in range(5):
            if os.path.exists(os.path.join(config_dir, "config.toml")):
                break
            config_dir = os.path.dirname(config_dir)
        storage_cfg = self._config.get("storage", {})
        rel_path = storage_cfg.get("calibration_state_path", "data/calibration_state.json")
        self._state_path = os.path.join(config_dir, rel_path)

        # Load last state if exists
        self._load_state()

        # Update label initial status
        self.update_status_label()

        # Refresh timer driving _update_spectrum
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._update_spectrum)
        self.timer.start()

    def _on_apply_exposure(self) -> None:
        try:
            value = int(self._exposure_input.text())
            if "camera" not in self._config:
                self._config["camera"] = {}
            self._config["camera"]["exposure_us"] = value
            self._frame_source.set_exposure_us(value)
        except Exception:
            pass

    def _update_spectrum(self) -> None:
        try:
            if self._frame_source is None:
                raise ValueError("Frame source not configured")

            if hasattr(self._frame_source, "get_frame"):
                frame = self._frame_source.get_frame()
            else:
                frame = self._frame_source.capture_frame()

            if frame is None:
                raise ValueError("No frame captures")

            from spectroo.dsp.pipeline import to_greyscale
            if frame.ndim == 3:
                frame_2d = to_greyscale(frame)
            else:
                frame_2d = frame.astype(np.float32)

            optics = self._config.get("optics", {})
            dsp = self._config.get("dsp", {})
            center_y = optics.get("center_y", 100)
            band_half_height = optics.get("band_half_height", dsp.get("band_half_height", 25))

            # Apply tilt correction if active
            tilt_angle = optics.get("tilt_angle_deg", 0.0)
            if tilt_angle != 0.0:
                from spectroo.dsp.pipeline import apply_tilt_correction
                frame_2d = apply_tilt_correction(frame_2d, tilt_angle)

            intensities = extract_band(frame_2d, center_y, band_half_height)
            flip_spectrum = optics.get("flip_spectrum", False)
            intensities = apply_flip(intensities, flip_spectrum)

            # Dark subtraction — use shared helper; silently skip if file missing/corrupt
            from spectroo.dsp.corrections import load_dark_frame, subtract_dark
            dark_path = self._config.get("storage", {}).get("dark_frame_path", "")
            dark_frame = load_dark_frame(dark_path)
            if dark_frame is not None:
                if dark_frame.ndim == 2:
                    # 2-D dark saved by DarkFrameWorker — collapse to 1-D with same optics
                    from spectroo.dsp.pipeline import apply_tilt_correction as _tilt
                    dark_2d = _tilt(dark_frame, tilt_angle) if tilt_angle != 0.0 else dark_frame
                    dark_frame = apply_flip(
                        extract_band(dark_2d, center_y, band_half_height),
                        flip_spectrum,
                    )
                intensities = subtract_dark(intensities, dark_frame)

            # Baseline subtraction — gated on dsp.baseline_enabled (same config key as main pipeline)
            if dsp.get("baseline_enabled", True):
                from spectroo.dsp.filters import subtract_baseline
                method = dsp.get("baseline_method", "sg_only")
                window = dsp.get("baseline_window", 51)
                polyorder = dsp.get("baseline_polyorder", 2)
                intensities = subtract_baseline(intensities, method, window, polyorder)

            self._current_intensities = intensities
            self.canvas.set_spectrum(intensities)
            if self._fit_result is not None:
                n_pixels = len(intensities)
                pixel_indices = np.arange(n_pixels)
                w_fit = np.polyval(self._fit_result.coefficients, pixel_indices)
                self.canvas.set_fit_curve(w_fit)
            else:
                self.canvas.set_fit_curve(None)
        except Exception:
            mock_data = self._mock_spectrum()
            self._current_intensities = mock_data
            self.canvas.set_spectrum(mock_data)
            if self._fit_result is not None:
                n_pixels = len(mock_data)
                pixel_indices = np.arange(n_pixels)
                w_fit = np.polyval(self._fit_result.coefficients, pixel_indices)
                self.canvas.set_fit_curve(w_fit)
            else:
                self.canvas.set_fit_curve(None)

    def _mock_spectrum(self) -> np.ndarray:
        x = np.arange(512)
        p1 = 2000 * np.exp(-((x - 100) / 15) ** 2)
        p2 = 3000 * np.exp(-((x - 200) / 10) ** 2)
        p3 = 1500 * np.exp(-((x - 300) / 20) ** 2)
        p4 = 2500 * np.exp(-((x - 400) / 12) ** 2)
        noise = np.random.normal(0, 10, 512)
        intensity = p1 + p2 + p3 + p4 + noise + 100.0
        return np.clip(intensity, 0, 4095)

    def _save_state(self) -> None:
        import json
        import os
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            points_data = [
                {
                    "pixel": int(getattr(p, "pixel_index", getattr(p, "pixel", 0))),
                    "wavelength": float(getattr(p, "known_wavelength_nm", getattr(p, "wavelength", 0.0)))
                }
                for p in self._points
            ]
            fit_result_data = None
            fit_points_data = None
            if self._fit_result is not None:
                fit_result_data = {
                    "degree": int(self._fit_result.degree),
                    "rms_nm": float(self._fit_result.rms_nm),
                    "coefficients": [float(c) for c in self._fit_result.coefficients],
                    "residuals_nm": getattr(self._fit_result, "residuals_nm", None)
                }
                fitted_points = getattr(self._fit_result, "fitted_points", self._points)
                fit_points_data = [
                    {
                        "pixel": int(getattr(p, "pixel_index", getattr(p, "pixel", 0))),
                        "wavelength": float(getattr(p, "known_wavelength_nm", getattr(p, "wavelength", 0.0)))
                    }
                    for p in fitted_points
                ]
            state = {
                "points": points_data,
                "fit_result": fit_result_data,
                "fit_points": fit_points_data
            }
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            import logging
            logger = logging.getLogger("spectroo")
            logger.error(f"Failed to save calibration state: {e}")

    def _load_state(self) -> None:
        import json
        import os
        # Fall back to empty state
        self._points = []
        self._fit_result = None
        self.canvas.set_calibration_points([])
        self.table.clear_points()
        self.canvas.set_fit_curve(None)

        if not os.path.exists(self._state_path):
            return

        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Restore points
            points_data = state.get("points", [])
            for p in points_data:
                pt = CalibrationPoint(pixel_index=p["pixel"], known_wavelength_nm=p["wavelength"])
                pt.pixel = p["pixel"]
                pt.wavelength = p["wavelength"]
                self._points.append(pt)

            self.canvas.set_calibration_points(self._points)
            self.table.clear_points()
            for pt in self._points:
                self.table.add_point(pt)

            # Restore fit result
            fit_result_data = state.get("fit_result")
            fit_points_data = state.get("fit_points")

            if fit_result_data is not None:
                from spectroo.core.calibration import PolynomialCalibration
                fitted_points = []
                if fit_points_data is not None:
                    for p in fit_points_data:
                        pt = CalibrationPoint(pixel_index=p["pixel"], known_wavelength_nm=p["wavelength"])
                        pt.pixel = p["pixel"]
                        pt.wavelength = p["wavelength"]
                        fitted_points.append(pt)

                self._fit_result = PolynomialCalibration(
                    coefficients=fit_result_data["coefficients"],
                    degree=fit_result_data["degree"],
                    rms_nm=fit_result_data["rms_nm"]
                )
                self._fit_result.residuals_nm = fit_result_data.get("residuals_nm")
                self._fit_result.fitted_points = fitted_points

                n_pixels = len(self._current_intensities) if self._current_intensities is not None else 512
                pixel_indices = np.arange(n_pixels)
                w_fit = np.polyval(self._fit_result.coefficients, pixel_indices)
                self.canvas.set_fit_curve(w_fit)
        except Exception as e:
            import logging
            logger = logging.getLogger("spectroo")
            logger.error(f"Failed to load calibration state, falling back to empty: {e}")
            # Ensure state is clean
            self._points = []
            self._fit_result = None
            self.canvas.set_calibration_points([])
            self.table.clear_points()
            self.canvas.set_fit_curve(None)

    def _check_stale(self) -> bool:
        if self._fit_result is None:
            return True
        fitted_points = getattr(self._fit_result, "fitted_points", None)
        if fitted_points is None:
            return True
        if len(self._points) != len(fitted_points):
            return True
        for p1, p2 in zip(self._points, fitted_points):
            px1 = getattr(p1, "pixel_index", getattr(p1, "pixel", 0))
            wl1 = getattr(p1, "known_wavelength_nm", getattr(p1, "wavelength", 0.0))
            px2 = getattr(p2, "pixel_index", getattr(p2, "pixel", 0))
            wl2 = getattr(p2, "known_wavelength_nm", getattr(p2, "wavelength", 0.0))
            if px1 != px2 or not math.isclose(wl1, wl2, abs_tol=1e-5):
                return True
        return False

    def update_status_label(self) -> None:
        if self._fit_result is None:
            self.status_label.setText("Enter at least 2 mapping pairs and click Fit.")
            self.status_label.setStyleSheet("font-size: 12px; color: #4b5563; font-weight: bold;")
            return

        is_stale = self._check_stale()
        prefix = "Stale — pairs changed since last fit:\n" if is_stale else ""
        
        degree = getattr(self._fit_result, "degree", 0)
        rms = getattr(self._fit_result, "rms_nm", 0.0)
        coefs = getattr(self._fit_result, "coefficients", [])
        
        coefs_str = ", ".join(f"{c:.4e}" for c in coefs)
        
        status_text = (
            f"{prefix}Fit Succeeded!\n"
            f"Degree: {degree}\n"
            f"RMS: {rms:.4f} nm\n"
            f"Coefficients: [{coefs_str}]"
        )
        self.status_label.setText(status_text)
        
        if is_stale:
            self.status_label.setStyleSheet("font-size: 12px; color: #b91c1c; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("font-size: 12px; color: #16a34a; font-weight: bold;")

    def _on_canvas_click(self, pixel: int) -> None:
        value, ok = QInputDialog.getDouble(
            self,
            "Add Calibration Point",
            f"Enter known wavelength for pixel {pixel} (nm):",
            500.0,
            300.0,
            900.0,
            1
        )
        if ok:
            point = CalibrationPoint(pixel, value)
            point.pixel = pixel
            point.wavelength = value
            self._points.append(point)
            self.canvas.set_calibration_points(self._points)
            self.table.add_point(point)

            self._save_state()
            self.update_status_label()

    def _on_run_fit(self) -> None:
        try:
            # Query fit_calibration parameter signature dynamically for config/min_points compatibility
            sig = inspect.signature(fit_calibration)
            kwargs = {}
            if "config" in sig.parameters:
                kwargs["config"] = self._config
            else:
                cal_config = self._config.get("calibration", {})
                for param in ["degree_low", "degree_high", "degree_threshold_points", "min_points"]:
                    if param in sig.parameters and param in cal_config:
                        kwargs[param] = cal_config[param]

            result = fit_calibration(self._points, **kwargs)

            # Dynamically evaluate the wavelengths across the active spectrum width
            n_pixels = len(self._current_intensities) if self._current_intensities is not None else 512
            pixel_indices = np.arange(n_pixels)
            # Evaluate using polynomial coefficients
            w_fit = np.polyval(result.coefficients, pixel_indices)
            result.wavelengths = w_fit

            import copy
            result.fitted_points = copy.deepcopy(self._points)
            result.residuals_nm = [
                float(np.polyval(result.coefficients, getattr(p, "pixel_index", getattr(p, "pixel", 0))) - getattr(p, "known_wavelength_nm", getattr(p, "wavelength", 0.0)))
                for p in self._points
            ]

            self._fit_result = result
            self.canvas.set_fit_curve(result.wavelengths)

            self._save_state()
            self.update_status_label()
        except CalibrationError as e:
            QMessageBox.warning(self, "Calibration Warning", str(e))
        except Exception as e:
            QMessageBox.warning(self, "Calibration Error", f"Unexpected fitting failure: {e}")

    def _on_undo(self) -> None:
        if self._points:
            self._points.pop()
            self.canvas.set_calibration_points(self._points)
            self.table.remove_last()

            self._save_state()
            self.update_status_label()

    def _on_apply(self) -> None:
        if self._fit_result is None:
            QMessageBox.warning(self, "No Fit Active", "A valid fitting polynomial must be generated before applying.")
            return

        if self._check_stale():
            QMessageBox.warning(self, "Stale Fit Warning", "The current fit is stale (calibration points have changed since last fit). Please run fit again.")
            return

        # Reversed coefficients from high-to-low to low-to-high order
        coefs_low_to_high = list(self._fit_result.coefficients)
        degree = int(self._fit_result.degree)
        n_points = len(self._points)

        # Locate config.toml dynamically by ascending directory structure
        import os
        base_dir = os.path.abspath(os.path.dirname(__file__))
        config_path = "config.toml"
        for _ in range(5):
            if os.path.exists(os.path.join(base_dir, "config.toml")):
                config_path = os.path.join(base_dir, "config.toml")
                break
            base_dir = os.path.dirname(base_dir)

        try:
            # Try parsing with tomli_w if available, otherwise manual fallback update
            try:
                import tomli_w
                import tomllib

                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                if "calibration" not in data:
                    data["calibration"] = {}
                data["calibration"]["coefficients"] = coefs_low_to_high
                data["calibration"]["degree"] = degree
                data["calibration"]["n_points"] = n_points

                with open(config_path, "wb") as f:
                    tomli_w.dump(data, f)
            except ImportError:
                # Manual replacement preserving structural comments
                with open(config_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                cal_idx = -1
                for i, line in enumerate(lines):
                    if line.strip().startswith("[calibration]"):
                        cal_idx = i
                        break

                coef_str = "[" + ", ".join(f"{c:.6e}" for c in coefs_low_to_high) + "]"
                new_lines_section = [
                    f"coefficients = {coef_str}\n",
                    f"degree = {degree}\n",
                    f"n_points = {n_points}\n"
                ]

                if cal_idx != -1:
                    end_idx = len(lines)
                    for i in range(cal_idx + 1, len(lines)):
                        if lines[i].strip().startswith("[") and not lines[i].strip().startswith("[calibration]"):
                            end_idx = i
                            break
                    section_lines = lines[cal_idx+1:end_idx]
                    filtered_lines = []
                    for line in section_lines:
                        is_replace = False
                        if "=" in line:
                            key = line.split("=")[0].strip()
                            if key in ["coefficients", "degree", "n_points"]:
                                is_replace = True
                        if not is_replace:
                            filtered_lines.append(line)
                    filtered_lines.extend(new_lines_section)
                    new_lines = lines[:cal_idx+1] + filtered_lines + lines[end_idx:]
                else:
                    new_lines = lines + ["\n[calibration]\n"] + new_lines_section

                with open(config_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

            # Update config dict in memory
            if "calibration" not in self._config:
                self._config["calibration"] = {}
            self._config["calibration"]["coefficients"] = coefs_low_to_high
            self._config["calibration"]["degree"] = degree
            self._config["calibration"]["n_points"] = n_points

            self.calibration_applied.emit()
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Save Failure", f"Failed to save coefficients to config: {e}")

    def _delete_point(self, pixel: int) -> None:
        self._points = [p for p in self._points if getattr(p, "pixel_index", getattr(p, "pixel", -1)) != pixel]
        self.canvas.set_calibration_points(self._points)

        # Re-render the points table
        self.table.clear_points()
        for pt in self._points:
            self.table.add_point(pt)

        self._save_state()
        self.update_status_label()

    def accept(self) -> None:
        self.timer.stop()
        super().accept()

    def reject(self) -> None:
        self.timer.stop()
        super().reject()
