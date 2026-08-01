"""SQLite schema + queries."""

import json
import os
import sqlite3
from spectroo.core.exceptions import DiskFullError, StorageUnavailableError
from spectroo.core.models import HistoryRecord, Peak


def init_db(db_path: str) -> None:
    """Create parent directory if missing, create the history table if missing.

    Wrap all sqlite3.Error in StorageUnavailableError.
    """
    try:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    exposure_us INTEGER NOT NULL,
                    pixel_indices TEXT NOT NULL,
                    intensity TEXT NOT NULL,
                    wavelengths TEXT,
                    peaks TEXT NOT NULL,
                    png_path TEXT NOT NULL,
                    calibration_rms_at_capture REAL,
                    pinned INTEGER DEFAULT 0
                )
            """
            )
            # Migration check: if table exists but doesn't have pinned column, add it
            cursor.execute("PRAGMA table_info(history)")
            columns = [col[1] for col in cursor.fetchall()]
            if columns and "pinned" not in columns:
                cursor.execute("ALTER TABLE history ADD COLUMN pinned INTEGER DEFAULT 0")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise StorageUnavailableError(
            f"Failed to initialize SQLite database at {db_path}: {e}"
        ) from e
    except Exception as e:
        raise StorageUnavailableError(
            f"An unexpected error occurred during database initialization: {e}"
        ) from e


def save_record(
    db_path: str, record: HistoryRecord, max_entries: int = 500
) -> int:
    """Insert the record (serialize array/peak fields to JSON).

    If total unpinned row count exceeds max_entries, delete the oldest unpinned rows.
    Return new row id.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        pixel_indices_json = json.dumps(record.pixel_indices)
        intensity_json = json.dumps(record.intensity)
        wavelengths_json = (
            json.dumps(record.wavelengths)
            if record.wavelengths is not None
            else None
        )

        peaks_list = [
            {
                "pixel_index": p.pixel_index,
                "wavelength_nm": p.wavelength_nm,
                "intensity": p.intensity,
                "prominence": p.prominence,
            }
            for p in record.peaks
        ]
        peaks_json = json.dumps(peaks_list)

        cursor.execute(
            """
            INSERT INTO history (
                timestamp, exposure_us, pixel_indices, intensity, wavelengths,
                peaks, png_path, calibration_rms_at_capture, pinned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                record.timestamp,
                record.exposure_us,
                pixel_indices_json,
                intensity_json,
                wavelengths_json,
                peaks_json,
                record.png_path,
                record.calibration_rms_at_capture,
                1 if record.pinned else 0,
            ),
        )
        new_id = cursor.lastrowid

        # Enforce FIFO limits: keep at most max_entries unpinned entries
        cursor.execute("SELECT id FROM history WHERE pinned = 0 ORDER BY id ASC")
        unpinned_ids = [row[0] for row in cursor.fetchall()]
        if len(unpinned_ids) > max_entries:
            prune_count = len(unpinned_ids) - max_entries
            to_delete = unpinned_ids[:prune_count]
            cursor.executemany("DELETE FROM history WHERE id = ?", [(tid,) for tid in to_delete])

        conn.commit()
        return new_id
    except sqlite3.OperationalError as e:
        err_msg = str(e).lower()
        if "disk" in err_msg and "full" in err_msg:
            raise DiskFullError(
                f"Failed to write to database: Disk is full."
            ) from e
        raise StorageUnavailableError(
            f"Database operational error: {e}"
        ) from e
    except sqlite3.Error as e:
        raise StorageUnavailableError(f"Database error: {e}") from e
    finally:
        if conn:
            conn.close()


def get_record(db_path: str, record_id: int) -> HistoryRecord | None:
    """Return None if no matching row.

    Deserialize JSON fields back to lists and Peak objects.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, exposure_us, pixel_indices, intensity,
                   wavelengths, peaks, png_path, calibration_rms_at_capture, pinned
              FROM history WHERE id = ?
        """,
            (record_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        (
            r_id,
            timestamp,
            exposure_us,
            pixel_indices_json,
            intensity_json,
            wavelengths_json,
            peaks_json,
            png_path,
            calibration_rms,
            pinned_val,
        ) = row

        pixel_indices = json.loads(pixel_indices_json)
        intensity = json.loads(intensity_json)
        wavelengths = (
            json.loads(wavelengths_json)
            if wavelengths_json is not None
            else None
        )

        peaks_raw = json.loads(peaks_json)
        peaks = [
            Peak(
                pixel_index=p["pixel_index"],
                wavelength_nm=p["wavelength_nm"],
                intensity=p["intensity"],
                prominence=p["prominence"],
            )
            for p in peaks_raw
        ]

        return HistoryRecord(
            id=r_id,
            timestamp=timestamp,
            exposure_us=exposure_us,
            pixel_indices=pixel_indices,
            intensity=intensity,
            wavelengths=wavelengths,
            peaks=peaks,
            png_path=png_path,
            calibration_rms_at_capture=calibration_rms,
            pinned=bool(pinned_val) if pinned_val is not None else False,
        )
    except sqlite3.Error as e:
        raise StorageUnavailableError(f"Database query error: {e}") from e
    finally:
        if conn:
            conn.close()


def get_all_records(db_path: str) -> list[HistoryRecord]:
    """Retrieve all history records from the database, sorted by id DESC."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, exposure_us, pixel_indices, intensity,
                   wavelengths, peaks, png_path, calibration_rms_at_capture, pinned
              FROM history ORDER BY id DESC
        """
        )
        rows = cursor.fetchall()
        records = []
        for row in rows:
            (
                r_id,
                timestamp,
                exposure_us,
                pixel_indices_json,
                intensity_json,
                wavelengths_json,
                peaks_json,
                png_path,
                calibration_rms,
                pinned_val,
            ) = row

            pixel_indices = json.loads(pixel_indices_json)
            intensity = json.loads(intensity_json)
            wavelengths = (
                json.loads(wavelengths_json)
                if wavelengths_json is not None
                else None
            )

            peaks_raw = json.loads(peaks_json)
            peaks = [
                Peak(
                    pixel_index=p["pixel_index"],
                    wavelength_nm=p["wavelength_nm"],
                    intensity=p["intensity"],
                    prominence=p["prominence"],
                )
                for p in peaks_raw
            ]

            records.append(
                HistoryRecord(
                    id=r_id,
                    timestamp=timestamp,
                    exposure_us=exposure_us,
                    pixel_indices=pixel_indices,
                    intensity=intensity,
                    wavelengths=wavelengths,
                    peaks=peaks,
                    png_path=png_path,
                    calibration_rms_at_capture=calibration_rms,
                    pinned=bool(pinned_val) if pinned_val is not None else False,
                )
            )
        return records
    except sqlite3.Error as e:
        raise StorageUnavailableError(f"Database query error: {e}") from e
    finally:
        if conn:
            conn.close()


def delete_record(db_path: str, record_id: int) -> None:
    """Delete a record from history."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE id = ?", (record_id,))
        conn.commit()
    except sqlite3.Error as e:
        raise StorageUnavailableError(f"Database delete error: {e}") from e
    finally:
        if conn:
            conn.close()


def set_pinned_status(db_path: str, record_id: int, pinned: bool) -> None:
    """Set the pinned status of a record."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE history SET pinned = ? WHERE id = ?", (1 if pinned else 0, record_id))
        conn.commit()
    except sqlite3.Error as e:
        raise StorageUnavailableError(f"Database update error: {e}") from e
    finally:
        if conn:
            conn.close()


