import os
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QCheckBox
from PyQt5.QtGui import QFont, QTextCursor

class LogTailerThread(QThread):
    new_line = pyqtSignal(str)

    def __init__(self, log_path: str, parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self._running = True
        self.proc = None

    def run(self):
        import shutil
        import subprocess
        
        has_journalctl = False
        if shutil.which("journalctl"):
            try:
                res = subprocess.run(
                    ["journalctl", "-u", "spectroo.service", "-n", "1"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=1
                )
                if res.returncode == 0:
                    has_journalctl = True
            except Exception:
                pass

        if has_journalctl:
            self.proc = subprocess.Popen(
                ["journalctl", "-u", "spectroo.service", "-f", "-n", "100"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            try:
                while self._running:
                    line = self.proc.stdout.readline()
                    if not line:
                        break
                    self.new_line.emit(line)
            finally:
                if self.proc:
                    try:
                        self.proc.terminate()
                        self.proc.wait()
                    except Exception:
                        pass
                    self.proc = None
        else:
            expanded_path = os.path.expanduser(self.log_path)
            os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
            if not os.path.exists(expanded_path):
                with open(expanded_path, "w", encoding="utf-8") as f:
                    f.write("")

            try:
                with open(expanded_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines[-100:]:
                        self.new_line.emit(line)
            except Exception:
                pass

            import time
            try:
                with open(expanded_path, "r", encoding="utf-8") as f:
                    f.seek(0, os.SEEK_END)
                    while self._running:
                        line = f.readline()
                        if not line:
                            time.sleep(0.1)
                            continue
                        self.new_line.emit(line)
            except Exception:
                pass

    def stop(self):
        self._running = False
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass


class LogViewerWindow(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Spectroo — Live System Logs")
        self.setMinimumSize(800, 500)
        self.setStyleSheet("background-color: #f3f4f6;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header info
        header_layout = QHBoxLayout()
        title_label = QLabel("Live System & Pipeline Logs", self)
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setStyleSheet("color: #111827;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Text Viewport
        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Courier New", 10))
        self.text_area.setStyleSheet(
            "background-color: #1e1e1e; color: #e5e7eb; border: 1px solid #374151; border-radius: 6px; padding: 10px;"
        )
        layout.addWidget(self.text_area, stretch=1)

        # Bottom controls
        controls_layout = QHBoxLayout()
        self.autoscroll_cb = QCheckBox("Auto-Scroll", self)
        self.autoscroll_cb.setChecked(True)
        self.autoscroll_cb.setStyleSheet("font-size: 12px; color: #374151;")
        
        clear_btn = QPushButton("Clear", self)
        clear_btn.setFixedWidth(80)
        clear_btn.setStyleSheet(
            "QPushButton { background-color: #ffffff; border: 1px solid #d1d5db; border-radius: 6px; padding: 5px; color: #374151; font-size: 12px; }"
            "QPushButton:hover { background-color: #f9fafb; }"
        )
        clear_btn.clicked.connect(self.text_area.clear)

        close_btn = QPushButton("Close", self)
        close_btn.setFixedWidth(80)
        close_btn.setStyleSheet(
            "QPushButton { background-color: #374151; border: none; border-radius: 6px; padding: 5px; color: #ffffff; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1f2937; }"
        )
        close_btn.clicked.connect(self.accept)

        controls_layout.addWidget(self.autoscroll_cb)
        controls_layout.addStretch()
        controls_layout.addWidget(clear_btn)
        controls_layout.addWidget(close_btn)
        layout.addLayout(controls_layout)

        # Initialize thread
        log_path = "~/spectroo/logs/spectroo.log"
        self.thread = LogTailerThread(log_path, self)
        self.thread.new_line.connect(self._on_new_line)
        self.thread.start()

    def _on_new_line(self, line: str) -> None:
        self.text_area.insertPlainText(line)
        # Limit lines in buffer
        doc = self.text_area.document()
        if doc.blockCount() > 2000:
            cursor = QTextCursor(doc.findBlockByNumber(0))
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar() # remove the remaining newline
            
        if self.autoscroll_cb.isChecked():
            scrollbar = self.text_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event) -> None:
        self.thread.stop()
        self.thread.wait()
        event.accept()
