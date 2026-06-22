import os
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
    QPushButton, QLabel, QListWidget, QListWidgetItem
)


class HistoryPanel(QWidget):
    """
    Collapsible panel showing scrollable history entries.
    """
    record_selected = pyqtSignal(int)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._expanded = False

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Header Frame
        self._header_frame = QFrame(self)
        self._header_frame.setFixedHeight(32)
        self._header_frame.setStyleSheet("QFrame { background-color: #fafafa; border-top: 1px solid #dcdcdc; }")
        
        header_layout = QHBoxLayout(self._header_frame)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        self._toggle_btn = QPushButton("▶ History", self._header_frame)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setStyleSheet(
            "QPushButton { font-size: 11px; color: #555555; background: transparent; border: none; text-align: left; }"
            "QPushButton:hover { color: #333333; }"
        )
        self._toggle_btn.clicked.connect(self._on_toggle)

        self._count_label = QLabel("0 entries", self._header_frame)
        self._count_label.setStyleSheet("font-size: 10px; color: #888888;")

        header_layout.addWidget(self._toggle_btn)
        header_layout.addStretch()
        header_layout.addWidget(self._count_label)

        # List Container QWidget
        self._list_container = QWidget(self)
        self._list_container.setFixedHeight(220)
        self._list_container.setVisible(False)
        
        container_layout = QVBoxLayout(self._list_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self._list = QListWidget(self._list_container)
        self._list.setStyleSheet("""
QListWidget {
    border: none;
    background-color: #ffffff;
    font-size: 11px;
    color: #333333;
}
QListWidget::item {
    padding: 6px 12px;
    border-bottom: 1px solid #eeeeee;
}
QListWidget::item:selected {
    background-color: #e8f0fe;
    color: #333333;
}
QListWidget::item:hover {
    background-color: #f5f5f5;
}
""")
        self._list.itemClicked.connect(self._on_item_clicked)
        container_layout.addWidget(self._list)

        self.layout.addWidget(self._header_frame)
        self.layout.addWidget(self._list_container)

    def _on_toggle(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._list_container.setVisible(True)
            self._toggle_btn.setText("▼ History")
            self.refresh()
        else:
            self._list_container.setVisible(False)
            self._toggle_btn.setText("▶ History")

    def refresh(self) -> None:
        from spectroo.storage.db import list_records, init_db
        db_path = self.config.get("history", {}).get("db_path", "data/spectroo.db")
        try:
            init_db(db_path)
        except Exception:
            pass
        records = list_records(db_path)
        self._list.clear()
        
        for record in records:
            ts = record.timestamp[:16].replace("T", "  ")
            peak_wls = [p.wavelength_nm for p in record.peaks if p.wavelength_nm is not None]
            if peak_wls:
                peaks_str = "  |  " + ",  ".join(f"{p:.0f} nm" for p in peak_wls[:3])
            else:
                peaks_str = ""
            label = f"{ts}{peaks_str}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, record.id)
            self._list.addItem(item)
            
        self._count_label.setText(f"{len(records)} entries")

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        record_id = int(item.data(Qt.UserRole))
        self.record_selected.emit(record_id)

    def clear_selection(self) -> None:
        self._list.clearSelection()
