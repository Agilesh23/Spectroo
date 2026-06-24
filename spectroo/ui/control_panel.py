from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QFrame
from PyQt5.QtGui import QFont
import logging
from spectroo.ui.theme import CONTROL_PANEL_WIDTH

logger = logging.getLogger("spectroo")


class ControlPanel(QWidget):
    """
    Control panel widget for capture parameters and system controls.
    """
    mode_changed        = pyqtSignal(str)   # "single" | "live"
    start_requested     = pyqtSignal()
    stop_requested      = pyqtSignal()
    exposure_changed    = pyqtSignal(int)
    plot_mode_changed   = pyqtSignal(str)   # "color" | "plain"
    baseline_toggled    = pyqtSignal(bool)
    export_requested    = pyqtSignal()
    save_chart_requested = pyqtSignal()
    shutdown_requested  = pyqtSignal()      # NEW — not in v1
    history_toggled     = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(CONTROL_PANEL_WIDTH)
        self.setObjectName("ControlPanelRoot")

        # Stylesheet identical to v1
        self.setStyleSheet("""
    QWidget#ControlPanelRoot {
        background-color: #ffffff;
        border-left: 1px solid #dcdcdc;
    }
    QPushButton {
        border: 1px solid #cccccc;
        border-radius: 3px;
        padding: 5px;
        background-color: #fafafa;
        color: #333333;
        font-size: 11px;
    }
    QPushButton:hover {
        background-color: #f0f0f0;
        border-color: #b0b0b0;
    }
    QPushButton:pressed {
        background-color: #e5e5e5;
    }
    QPushButton:checked {
        background-color: #0066cc;
        color: #ffffff;
        border-color: #0055bb;
    }
    QLineEdit {
        border: 1px solid #cccccc;
        border-radius: 3px;
        padding: 4px;
        background-color: #ffffff;
        color: #333333;
        font-size: 11px;
    }
    QCheckBox {
        font-size: 11px;
        color: #333333;
    }
""")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(8)

        # 1. MODE (is_first=True)
        self._add_header("MODE", is_first=True)
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(4)
        self.single_btn = QPushButton("Single")
        self.single_btn.setCheckable(True)
        self.single_btn.setChecked(True)
        self.single_btn.clicked.connect(self._on_single_clicked)
        
        self.live_btn = QPushButton("Live")
        self.live_btn.setCheckable(True)
        self.live_btn.setChecked(False)
        self.live_btn.clicked.connect(self._on_live_clicked)
        
        mode_layout.addWidget(self.single_btn)
        mode_layout.addWidget(self.live_btn)
        self.layout.addLayout(mode_layout)

        # 2. ACQUISITION
        self._add_header("ACQUISITION")
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_requested.emit)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        
        self.layout.addWidget(self.start_btn)
        self.layout.addWidget(self.stop_btn)

        exposure_layout = QHBoxLayout()
        exposure_label = QLabel("Exposure (µs):")
        exposure_label.setStyleSheet("font-size: 11px; color: #555555;")
        self.exposure_input = QLineEdit("50000")
        self.exposure_input.setFixedWidth(80)
        self.exposure_input.editingFinished.connect(self._on_exposure_finished)
        exposure_layout.addWidget(exposure_label)
        exposure_layout.addWidget(self.exposure_input)
        self.layout.addLayout(exposure_layout)

        # 3. DISPLAY
        self._add_header("DISPLAY")
        self.plot_mode_btn = QPushButton("Colour Spectrum")
        self.plot_mode_btn.setCheckable(True)
        self.plot_mode_btn.setChecked(True)
        self.plot_mode_btn.clicked.connect(self._on_plot_mode_clicked)
        
        self.baseline_btn = QPushButton("Baseline Corr")
        self.baseline_btn.setCheckable(True)
        self.baseline_btn.setChecked(True)
        self.baseline_btn.clicked.connect(lambda checked: self.baseline_toggled.emit(checked))
        
        self.layout.addWidget(self.plot_mode_btn)
        self.layout.addWidget(self.baseline_btn)

        # 4. DATA
        self._add_header("DATA")
        self.export_btn = QPushButton("Export JSON")
        self.export_btn.clicked.connect(self.export_requested.emit)
        self.save_chart_btn = QPushButton("Save Chart")
        self.save_chart_btn.clicked.connect(self.save_chart_requested.emit)
        
        self.layout.addWidget(self.export_btn)
        self.layout.addWidget(self.save_chart_btn)

        # 5. SYSTEM
        self._add_header("SYSTEM")
        self.history_btn = QPushButton("History")
        self.history_btn.clicked.connect(self._on_history_clicked)
        self.layout.addWidget(self.history_btn)
        self.shutdown_btn = QPushButton("Shutdown")
        self.shutdown_btn.clicked.connect(self.shutdown_requested.emit)
        self.layout.addWidget(self.shutdown_btn)

        # Bottom Stretch
        self.layout.addStretch()

    def _add_header(self, title: str, is_first: bool = False) -> None:
        """
        Internal helper to add section headers with optional line separators.
        """
        if not is_first:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setFrameShadow(QFrame.Sunken)
            sep.setStyleSheet("color: #eeeeee;")
            self.layout.addWidget(sep)
        
        label = QLabel(title)
        label.setFont(QFont("Arial", 8, QFont.Bold))
        label.setStyleSheet("color: #666666; padding-bottom: 2px;")
        self.layout.addWidget(label)

    def _on_single_clicked(self) -> None:
        logger.info("Button clicked: Mode Single | Mode: single | Exposure: %s", self.exposure_input.text())
        self.set_mode("single")
        self.mode_changed.emit("single")

    def _on_live_clicked(self) -> None:
        logger.info("Button clicked: Mode Live | Mode: live | Exposure: %s", self.exposure_input.text())
        self.set_mode("live")
        self.mode_changed.emit("live")

    def _on_exposure_finished(self) -> None:
        try:
            val = int(self.exposure_input.text())
            if val > 0:
                self.exposure_changed.emit(val)
        except ValueError:
            pass

    def _on_plot_mode_clicked(self) -> None:
        checked = self.plot_mode_btn.isChecked()
        logger.info("Button clicked: Colour Spectrum toggle | Checked: %s", checked)
        if checked:
            self.plot_mode_btn.setText("Colour Spectrum")
            self.plot_mode_changed.emit("color")
        else:
            self.plot_mode_btn.setText("Plain Spectrum")
            self.plot_mode_changed.emit("plain")

    def _on_history_clicked(self) -> None:
        logger.info("Button clicked: History")
        self.history_toggled.emit()

    def set_mode(self, mode: str) -> None:
        if mode == "single":
            self.single_btn.setChecked(True)
            self.live_btn.setChecked(False)
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
        elif mode == "live":
            self.single_btn.setChecked(False)
            self.live_btn.setChecked(True)
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
