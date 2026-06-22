import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import pytest
from PyQt5.QtWidgets import QApplication, QListWidgetItem
from PyQt5.QtCore import Qt
from spectroo.ui.history_panel import HistoryPanel
from spectroo.storage.db import init_db


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def temp_db_config():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    init_db(path)
    
    config = {
        "camera": {"exposure_us": 50000, "n_frames": 4},
        "dsp": {"baseline_enabled": True},
        "storage": {
            "dark_frame_path": "dark_frame.npy",
        },
        "history": {
            "db_path": path,
            "max_entries": 500,
        },
        "calibration": {},
    }
    yield config
    
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def test_history_panel_constructs(temp_db_config):
    panel = HistoryPanel(temp_db_config)
    assert panel._expanded is False


def test_history_panel_initially_collapsed(temp_db_config):
    panel = HistoryPanel(temp_db_config)
    assert panel._list_container.isVisible() is False


def test_history_panel_toggle_expands(temp_db_config):
    panel = HistoryPanel(temp_db_config)
    panel.show()
    panel._on_toggle()
    assert panel._expanded is True
    assert panel._list_container.isVisible() is True


def test_history_panel_toggle_collapses(temp_db_config):
    panel = HistoryPanel(temp_db_config)
    panel._on_toggle()
    panel._on_toggle()
    assert panel._expanded is False
    assert panel._list_container.isVisible() is False


def test_history_panel_toggle_button_text_expanded(temp_db_config):
    panel = HistoryPanel(temp_db_config)
    panel._on_toggle()
    assert panel._toggle_btn.text() == "▼ History"


def test_history_panel_toggle_button_text_collapsed(temp_db_config):
    panel = HistoryPanel(temp_db_config)
    panel._on_toggle()
    panel._on_toggle()
    assert panel._toggle_btn.text() == "▶ History"


def test_history_panel_refresh_empty(temp_db_config):
    panel = HistoryPanel(temp_db_config)
    panel.refresh()
    assert panel._count_label.text() == "0 entries"
    assert panel._list.count() == 0


def test_history_panel_record_selected_signal(temp_db_config):
    panel = HistoryPanel(temp_db_config)
    
    emitted_ids = []
    panel.record_selected.connect(lambda r_id: emitted_ids.append(r_id))
    
    item = QListWidgetItem("2026-06-22  14:35")
    item.setData(Qt.UserRole, 42)
    
    panel._on_item_clicked(item)
    assert len(emitted_ids) == 1
    assert emitted_ids[0] == 42
