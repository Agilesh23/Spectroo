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
    list_records,
    delete_record,
)
from spectroo.storage.export import (
    export_csv,
    export_json,
    generate_thumbnail_png,
    export_png,
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


# 1. test_init_db_creates_empty: init fresh db, list_records returns []
def test_init_db_creates_empty(temp_db):
    records = list_records(temp_db)
    assert records == []


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


# 4. test_list_records_newest_first
def test_list_records_newest_first(temp_db):
    rec1 = make_dummy_record(timestamp="2026-06-22T12:00:01Z")
    rec2 = make_dummy_record(timestamp="2026-06-22T12:00:02Z")
    rec3 = make_dummy_record(timestamp="2026-06-22T12:00:03Z")

    id1 = save_record(temp_db, rec1)
    id2 = save_record(temp_db, rec2)
    id3 = save_record(temp_db, rec3)

    records = list_records(temp_db)
    assert len(records) == 3
    assert records[0].id == id3
    assert records[1].id == id2
    assert records[2].id == id1


# 5. test_fifo_cap_prunes_oldest
def test_fifo_cap_prunes_oldest(temp_db):
    rec1 = make_dummy_record(timestamp="2026-06-22T12:00:01Z")
    rec2 = make_dummy_record(timestamp="2026-06-22T12:00:02Z")
    rec3 = make_dummy_record(timestamp="2026-06-22T12:00:03Z")

    id1 = save_record(temp_db, rec1, max_entries=2)
    id2 = save_record(temp_db, rec2, max_entries=2)
    id3 = save_record(temp_db, rec3, max_entries=2)

    records = list_records(temp_db)
    assert len(records) == 2
    # Newest first
    assert records[0].id == id3
    assert records[1].id == id2

    # Assert id1 is deleted
    assert get_record(temp_db, id1) is None


# 6. test_delete_record
def test_delete_record(temp_db):
    rec = make_dummy_record()
    rec_id = save_record(temp_db, rec)

    assert delete_record(temp_db, rec_id) is True
    assert get_record(temp_db, rec_id) is None

    assert delete_record(temp_db, 999) is False


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


# 10. test_generate_thumbnail_png_creates_file
def test_generate_thumbnail_png_creates_file(tmp_path):
    from spectroo.core.models import Spectrum, Peak
    import numpy as np
    
    spec = Spectrum(
        pixel_indices=np.arange(100),
        intensity=np.ones(100) * 50.0,
        wavelengths=np.linspace(400, 700, 100),
        exposure_us=200000,
        peaks=[],
        calibration_rms_at_capture=None,
        timestamp="2026-06-22T12:00:00Z"
    )
    
    out_file = tmp_path / "thumb.png"
    generate_thumbnail_png(spec, str(out_file))
    
    assert out_file.exists()
    assert out_file.stat().st_size > 0


# 11. test_generate_thumbnail_png_correct_size
def test_generate_thumbnail_png_correct_size(tmp_path):
    from spectroo.core.models import Spectrum, Peak
    import numpy as np
    import struct
    
    spec = Spectrum(
        pixel_indices=np.arange(100),
        intensity=np.ones(100) * 50.0,
        wavelengths=np.linspace(400, 700, 100),
        exposure_us=200000,
        peaks=[],
        calibration_rms_at_capture=None,
        timestamp="2026-06-22T12:00:00Z"
    )
    
    out_file = tmp_path / "thumb_sz.png"
    generate_thumbnail_png(spec, str(out_file))
    
    with open(out_file, "rb") as f:
        data = f.read(24)
    width, height = struct.unpack(">II", data[16:24])
    
    assert width == 400
    assert height == 200


# 12. test_export_png_creates_file
def test_export_png_creates_file(tmp_path):
    rec = make_dummy_record()
    out_file = tmp_path / "export.png"
    export_png(rec, str(out_file))
    
    assert out_file.exists()
    assert out_file.stat().st_size > 0


# 13. test_export_png_correct_size
def test_export_png_correct_size(tmp_path):
    import struct
    rec = make_dummy_record()
    out_file = tmp_path / "export_sz.png"
    export_png(rec, str(out_file))
    
    with open(out_file, "rb") as f:
        data = f.read(24)
    width, height = struct.unpack(">II", data[16:24])
    
    assert width == 900
    assert height == 400


# 14. test_export_png_with_peaks
def test_export_png_with_peaks(tmp_path):
    from spectroo.core.models import Peak
    rec = make_dummy_record()
    # Ensure there are at least two Peak objects
    rec.peaks = [
        Peak(pixel_index=20, wavelength_nm=420.0, intensity=50.0, prominence=2.0),
        Peak(pixel_index=80, wavelength_nm=680.0, intensity=80.0, prominence=5.0)
    ]
    
    out_file = tmp_path / "export_peaks.png"
    export_png(rec, str(out_file))
    
    assert out_file.exists()
    assert out_file.stat().st_size > 0
