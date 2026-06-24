from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from spectroo.ui.theme import STATUS_BAR_HEIGHT


class StatusBar(QWidget):
    """
    Custom clean white-themed Status Bar showing FPS, calibration status,
    dark frame status, and last 3 detected peak wavelengths.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(STATUS_BAR_HEIGHT)
        self.setStyleSheet("""
    QWidget {
        background-color: #ffffff;
        border-top: 1px solid #dcdcdc;
        color: #555555;
        font-family: Arial;
        font-size: 11px;
    }
    QLabel {
        border: none;
    }
""")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(25)

        self.fps_label = QLabel("FPS: 0.0", self)
        self.calib_label = QLabel("Calibration: Uncalibrated", self)
        self.dark_label = QLabel("Dark Frame: Not Loaded", self)
        self.peaks_label = QLabel("Peaks: None", self)
        self.message_label = QLabel("", self)
        self.message_label.setStyleSheet("color: #0066cc; font-weight: bold;")

        layout.addWidget(self.fps_label)
        layout.addWidget(self.calib_label)
        layout.addWidget(self.dark_label)
        layout.addWidget(self.peaks_label)
        layout.addStretch()
        layout.addWidget(self.message_label)

    def update_status(self, data: dict) -> None:
        """
        Update status bar label values dynamically.
        """
        if "fps" in data:
            self.fps_label.setText(f"FPS: {data['fps']:.1f}")

        is_calibrated = data.get("calibrated", False)
        if "calibrated" in data:
            status = "Calibrated" if is_calibrated else "Uncalibrated"
            self.calib_label.setText(f"Calibration: {status}")

        if "dark_loaded" in data:
            status = "Loaded" if data["dark_loaded"] else "Not Loaded"
            self.dark_label.setText(f"Dark Frame: {status}")

        if "peaks" in data:
            peaks = data["peaks"]
            if peaks:
                peak_strs = []
                for p in peaks[:3]:
                    if is_calibrated:
                        peak_strs.append(f"{p:.1f} nm")
                    else:
                        peak_strs.append(f"{int(round(p))} px")
                self.peaks_label.setText(f"Peaks: {', '.join(peak_strs)}")
            else:
                self.peaks_label.setText("Peaks: None")

        if "message" in data:
            self.message_label.setText(data["message"])

