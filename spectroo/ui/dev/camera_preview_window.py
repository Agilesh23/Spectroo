"""Live raw camera preview window for dev mode."""
import numpy as np
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QSpinBox
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap


class CameraPreviewWindow(QDialog):
    def __init__(self, config: dict, frame_source, parent=None):
        super().__init__(parent)
        self._config = config
        self._frame_source = frame_source
        self.setWindowTitle("Spectroo — Live Camera Feed")
        self.setMinimumSize(800, 300)
        self.setStyleSheet("background-color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet("background-color: #e5e7eb;")
        self._image_label.setMinimumHeight(220)
        layout.addWidget(self._image_label, stretch=1)

        controls = QHBoxLayout()
        exp_label = QLabel("Exposure (µs):", self)
        exp_label.setStyleSheet("color: #111111; font-size: 12px;")
        self._exp_spin = QSpinBox(self)
        self._exp_spin.setRange(110, 3066979)
        self._exp_spin.setSingleStep(10000)
        self._exp_spin.setValue(config.get("camera", {}).get("exposure_us", 200000))
        
        apply_exp_btn = QPushButton("Apply", self)
        apply_exp_btn.setFixedHeight(34)
        apply_exp_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; border: none; "
            "font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
        )
        apply_exp_btn.clicked.connect(self._on_apply_exposure)
        
        controls.addWidget(exp_label)
        controls.addWidget(self._exp_spin)
        controls.addWidget(apply_exp_btn)
        controls.addStretch()

        close_btn = QPushButton("Close", self)
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(
            "QPushButton { background-color: #374151; color: white; border: none; "
            "font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1f2937; }"
        )
        close_btn.clicked.connect(self.reject)
        controls.addWidget(close_btn)
        layout.addLayout(controls)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._update_frame)
        self._timer.start()

    def _on_apply_exposure(self):
        value = self._exp_spin.value()
        if "camera" not in self._config:
            self._config["camera"] = {}
        self._config["camera"]["exposure_us"] = value
        try:
            self._frame_source.set_exposure_us(value)
        except Exception:
            pass

    def _update_frame(self):
        try:
            if hasattr(self._frame_source, "get_frame"):
                frame = self._frame_source.get_frame()
            else:
                frame = self._frame_source.capture_frame()
            if frame is None:
                return
            if frame.ndim == 3:
                h, w, _ = frame.shape
                rgb = frame.astype(np.uint8)
                qimg = QImage(rgb.tobytes(), w, h, 3 * w, QImage.Format_RGB888)
            else:
                h, w = frame.shape
                norm = ((frame - frame.min()) / max(frame.max() - frame.min(), 1) * 255).astype(np.uint8)
                qimg = QImage(norm.tobytes(), w, h, w, QImage.Format_Grayscale8)
            pix = QPixmap.fromImage(qimg).scaled(
                self._image_label.width(), self._image_label.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self._image_label.setPixmap(pix)
        except Exception:
            pass

    def accept(self):
        self._timer.stop()
        super().accept()

    def reject(self):
        self._timer.stop()
        super().reject()
