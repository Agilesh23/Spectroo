import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import csv
import json
import pytest
from spectroo.core.exceptions import StorageUnavailableError
from spectroo.core.models import HistoryRecord, Peak
from spectroo.storage.db import (
    init_db,
    save_record,
    get_record,
    get_all_records,
    delete_record,
    set_pinned_status,
)
from spectroo.storage.export import (
    export_csv,
    export_json,
)


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_spectroo.db"
    init_db(str(db_file))
    return str(db_file)


def make_dummy_record(
    timestamp="2026-06-22T12:00:00Z", exposure_us=200000, png_path="dummy.png"
):
    return HistoryRecord(
        id=None,
        timestamp=timestamp,
        exposure_us=exposure_us,
        pixel_indices=[0, 1, 2],
        intensity=[10.5, 20.0, 5.2],
        wavelengths=[400.0, 410.0, 420.0],
        peaks=[
            Peak(
                pixel_index=1,
                wavelength_nm=410.0,
                intensity=20.0,
                prominence=9.5,
            )
        ],
        png_path=png_path,
        calibration_rms_at_capture=0.15,
    )


# 1. test_init_db_creates_empty: init fresh db, check empty history table
def test_init_db_creates_empty(temp_db):
    import sqlite3
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM history")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 0



# 2. test_save_and_get_record: save returns an int id; get_record(id) returns matching record
def test_save_and_get_record(temp_db):
    rec = make_dummy_record()
    rec_id = save_record(temp_db, rec)
    assert isinstance(rec_id, int)

    loaded = get_record(temp_db, rec_id)
    assert loaded is not None
    assert loaded.id == rec_id
    assert loaded.timestamp == rec.timestamp
    assert loaded.exposure_us == rec.exposure_us
    assert loaded.pixel_indices == rec.pixel_indices
    assert loaded.intensity == rec.intensity
    assert loaded.wavelengths == rec.wavelengths
    assert loaded.png_path == rec.png_path
    assert (
        loaded.calibration_rms_at_capture == rec.calibration_rms_at_capture
    )

    assert len(loaded.peaks) == 1
    assert loaded.peaks[0].pixel_index == 1
    assert loaded.peaks[0].wavelength_nm == 410.0
    assert loaded.peaks[0].intensity == 20.0
    assert loaded.peaks[0].prominence == 9.5


# 3. test_get_record_missing_returns_none
def test_get_record_missing_returns_none(temp_db):
    assert get_record(temp_db, 999) is None


# 5. test_fifo_cap_prunes_oldest
def test_fifo_cap_prunes_oldest(temp_db):
    rec1 = make_dummy_record(timestamp="2026-06-22T12:00:01Z")
    rec2 = make_dummy_record(timestamp="2026-06-22T12:00:02Z")
    rec3 = make_dummy_record(timestamp="2026-06-22T12:00:03Z")

    id1 = save_record(temp_db, rec1, max_entries=2)
    id2 = save_record(temp_db, rec2, max_entries=2)
    id3 = save_record(temp_db, rec3, max_entries=2)

    # Assert id1 is deleted (FIFO prunes the oldest)
    assert get_record(temp_db, id1) is None
    # Assert newer records are still present
    assert get_record(temp_db, id2) is not None
    assert get_record(temp_db, id3) is not None



# 7. test_save_record_invalid_path_raises_storage_unavailable
def test_save_record_invalid_path_raises_storage_unavailable(tmp_path):
    # Pass directory path as db_path
    invalid_path = str(tmp_path)
    rec = make_dummy_record()
    with pytest.raises(StorageUnavailableError):
        save_record(invalid_path, rec)


# 8. test_export_csv
def test_export_csv(tmp_path):
    rec = make_dummy_record()
    csv_file = tmp_path / "export.csv"
    export_csv(rec, str(csv_file))

    assert csv_file.exists()
    with open(csv_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    assert len(rows) == 4  # Header + 3 data rows
    assert rows[0] == ["pixel_index", "intensity", "wavelength_nm"]
    assert rows[1][0] == "0"
    assert float(rows[1][1]) == pytest.approx(10.5)
    assert float(rows[1][2]) == pytest.approx(400.0)


# 9. test_export_json
def test_export_json(tmp_path):
    rec = make_dummy_record()
    json_file = tmp_path / "export.json"
    export_json(rec, str(json_file))

    assert json_file.exists()
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "id" not in data
    assert "png_path" not in data
    assert data["timestamp"] == rec.timestamp
    assert data["exposure_us"] == rec.exposure_us
    assert data["pixel_indices"] == rec.pixel_indices
    assert data["intensity"] == rec.intensity
    assert data["wavelengths"] == rec.wavelengths
    assert len(data["peaks"]) == 1
    assert data["peaks"][0]["pixel_index"] == 1
    assert data["peaks"][0]["wavelength_nm"] == pytest.approx(410.0)
    assert data["peaks"][0]["intensity"] == pytest.approx(20.0)
    assert data["peaks"][0]["prominence"] == pytest.approx(9.5)
    assert data["calibration_rms_at_capture"] == pytest.approx(0.15)


def test_fifo_cap_pinned_not_evicted(temp_db):
    # Save a pinned record
    rec_pinned = make_dummy_record(timestamp="2026-06-22T12:00:00Z")
    rec_pinned.pinned = True
    pinned_id = save_record(temp_db, rec_pinned, max_entries=20)

    # Save 20 unpinned records
    unpinned_ids = []
    for i in range(20):
        rec = make_dummy_record(timestamp=f"2026-06-22T12:01:{i:02d}Z")
        unpinned_ids.append(save_record(temp_db, rec, max_entries=20))

    # Verify all are in the DB
    assert get_record(temp_db, pinned_id) is not None
    for uid in unpinned_ids:
        assert get_record(temp_db, uid) is not None

    # Save a 21st unpinned record (should trigger eviction of oldest unpinned, i.e., unpinned_ids[0])
    rec21 = make_dummy_record(timestamp="2026-06-22T12:02:00Z")
    id21 = save_record(temp_db, rec21, max_entries=20)

    # The pinned record should STILL be present!
    assert get_record(temp_db, pinned_id) is not None
    # The oldest unpinned record should be deleted!
    assert get_record(temp_db, unpinned_ids[0]) is None
    # The 2nd unpinned record and the 21st unpinned record should be present!
    assert get_record(temp_db, unpinned_ids[1]) is not None
    assert get_record(temp_db, id21) is not None


def test_get_all_records_retrieves_sorted(temp_db):
    rec1 = make_dummy_record(timestamp="2026-06-22T12:00:01Z")
    rec2 = make_dummy_record(timestamp="2026-06-22T12:00:02Z")
    
    id1 = save_record(temp_db, rec1)
    id2 = save_record(temp_db, rec2)
    
    all_recs = get_all_records(temp_db)
    assert len(all_recs) == 2
    # Should be sorted by ID DESC
    assert all_recs[0].id == id2
    assert all_recs[1].id == id1


def test_delete_record(temp_db):
    rec = make_dummy_record()
    rec_id = save_record(temp_db, rec)
    assert get_record(temp_db, rec_id) is not None
    
    delete_record(temp_db, rec_id)
    assert get_record(temp_db, rec_id) is None


def test_set_pinned_status(temp_db):
    rec = make_dummy_record()
    rec_id = save_record(temp_db, rec)
    
    loaded = get_record(temp_db, rec_id)
    assert loaded.pinned is False
    
    set_pinned_status(temp_db, rec_id, True)
    loaded = get_record(temp_db, rec_id)
    assert loaded.pinned is True
    
    set_pinned_status(temp_db, rec_id, False)
    loaded = get_record(temp_db, rec_id)
    assert loaded.pinned is False
