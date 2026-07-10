"""On-demand CSV / JSON generation."""

import csv
import json
from spectroo.core.models import HistoryRecord


def export_csv(record: HistoryRecord, output_path: str) -> None:
    """Write a CSV with header: pixel_index,intensity,wavelength_nm.

    wavelength_nm column is blank for each row if record.wavelengths is None.
    """
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["pixel_index", "intensity", "wavelength_nm"])

        for i, idx in enumerate(record.pixel_indices):
            intensity_val = record.intensity[i]
            wavelength_val = (
                record.wavelengths[i]
                if record.wavelengths is not None
                else ""
            )
            writer.writerow([idx, intensity_val, wavelength_val])


def export_json(record: HistoryRecord, output_path: str) -> None:
    """Write the full record as JSON.

    Includes: timestamp, exposure_us, pixel_indices, intensity, wavelengths,
    peaks (as list of dicts), and calibration_rms_at_capture. Excludes id/png_path.
    """
    data = {
        "timestamp": record.timestamp,
        "exposure_us": record.exposure_us,
        "pixel_indices": record.pixel_indices,
        "intensity": record.intensity,
        "wavelengths": record.wavelengths,
        "peaks": [
            {
                "pixel_index": p.pixel_index,
                "wavelength_nm": p.wavelength_nm,
                "intensity": p.intensity,
                "prominence": p.prominence,
            }
            for p in record.peaks
        ],
        "calibration_rms_at_capture": record.calibration_rms_at_capture,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
