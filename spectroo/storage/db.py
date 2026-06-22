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
                    calibration_rms_at_capture REAL
                )
            """
            )
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

    If total row count exceeds max_entries, delete oldest rows. Return new row id.
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
                peaks, png_path, calibration_rms_at_capture
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        new_id = cursor.lastrowid

        # Enforce FIFO limits
        cursor.execute("SELECT COUNT(*) FROM history")
        count = cursor.fetchone()[0]
        if count > max_entries:
            prune_count = count - max_entries
            cursor.execute(
                f"DELETE FROM history WHERE id IN (SELECT id FROM history ORDER BY id ASC LIMIT ?)",
                (prune_count,),
            )

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
                   wavelengths, peaks, png_path, calibration_rms_at_capture
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
        )
    except sqlite3.Error as e:
        raise StorageUnavailableError(f"Database query error: {e}") from e
    finally:
        if conn:
            conn.close()


def list_records(
    db_path: str, limit: int | None = None, offset: int = 0
) -> list[HistoryRecord]:
    """Order by id DESC (newest first).

    Apply LIMIT/OFFSET if limit is not None.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = """
            SELECT id, timestamp, exposure_us, pixel_indices, intensity,
                   wavelengths, peaks, png_path, calibration_rms_at_capture
              FROM history ORDER BY id DESC
        """
        params = []
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cursor.execute(query, params)
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
                )
            )
        return records
    except sqlite3.Error as e:
        raise StorageUnavailableError(f"Database list error: {e}") from e
    finally:
        if conn:
            conn.close()


def delete_record(db_path: str, record_id: int) -> bool:
    """Return True if a row was deleted, False if no matching id existed."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE id = ?", (record_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        return rows_affected > 0
    except sqlite3.Error as e:
        raise StorageUnavailableError(f"Database delete error: {e}") from e
    finally:
        if conn:
            conn.close()
