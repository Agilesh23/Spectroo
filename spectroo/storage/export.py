"""On-demand CSV / JSON / PNG generation."""

import csv
import json
import os
import sys
import numpy as np

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QRectF

from spectroo.core.models import Spectrum, HistoryRecord
from spectroo.ui.plot_widget import SpectrumPlotWidget

try:
    from spectroo.core.exceptions import ExportError
except ImportError:
    from spectroo.core.exceptions import SpectrooError
    class ExportError(SpectrooError):
        """Raised when document or image export fails."""
        pass


def _set_spectrum_compat(self, obj):
    """Compatibility wrapper to map a Spectrum or HistoryRecord onto SpectrumPlotWidget."""
    wavelengths = obj.wavelengths
    intensities = getattr(obj, "intensity", None)
    if intensities is None:
        intensities = getattr(obj, "intensities", None)
    if intensities is None:
        # Fallback to HistoryRecord lists
        intensities = getattr(obj, "intensity", None)

    peaks_indices = []
    peaks_list = getattr(obj, "peaks", [])
    if peaks_list:
        for p in peaks_list:
            if hasattr(p, "pixel_index"):
                peaks_indices.append(p.pixel_index)
            elif isinstance(p, int):
                peaks_indices.append(p)
            elif isinstance(p, float):
                if wavelengths is not None:
                    idx = (np.abs(np.array(wavelengths) - p)).argmin()
                    peaks_indices.append(int(idx))

    self.set_data(wavelengths, intensities, peaks_indices)


# Dynamically attach the set_spectrum compatibility method
SpectrumPlotWidget.set_spectrum = _set_spectrum_compat


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


def generate_thumbnail_png(spectrum: Spectrum, path: str) -> None:
    """Cheap thumbnail written at save-time. Small fixed size (400x200 px)."""
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        widget = SpectrumPlotWidget()
        widget.margin_left = 0
        widget.margin_right = 0
        widget.margin_top = 0
        widget.margin_bottom = 0
        widget.grid_color = QColor(0, 0, 0, 0)
        widget.axis_color = QColor(0, 0, 0, 0)
        widget.text_color = QColor(0, 0, 0, 0)
        widget.peaks_visible = False

        widget.resize(400, 200)
        widget.set_spectrum(spectrum)

        pixmap = QPixmap(400, 200)
        pixmap.fill(Qt.white)
        painter = QPainter(pixmap)
        widget.render(painter)
        painter.end()

        success = pixmap.save(path, "PNG")
        if not success:
            raise ExportError(f"Failed to save PNG thumbnail to {path}")
    except Exception as e:
        if isinstance(e, ExportError):
            raise e
        raise ExportError(f"Error generating thumbnail PNG: {e}") from e


def export_png(
    record: HistoryRecord,
    path: str,
    png_annotation_cap: int = 5,
    png_label_decimals: int = 1,
) -> None:
    """Annotated full-size export (900x400 px), rendered on demand."""
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        widget = SpectrumPlotWidget()
        widget.resize(900, 400)
        widget.set_spectrum(record)

        pixmap = QPixmap(900, 400)
        pixmap.fill(Qt.white)
        painter = QPainter(pixmap)
        widget.render(painter)

        # Title/metadata overlays
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.setPen(QColor("#333333"))

        label = getattr(record, "label", "") or "Spectrum"
        painter.drawText(QRectF(65, 5, 400, 20), Qt.AlignLeft | Qt.AlignVCenter, label)

        formatted_ts = ""
        if record.timestamp:
            try:
                formatted_ts = record.timestamp[:19].replace("T", " ")
            except Exception:
                formatted_ts = record.timestamp
        painter.drawText(QRectF(900 - 35 - 300, 5, 300, 20), Qt.AlignRight | Qt.AlignVCenter, formatted_ts)

        painter.end()

        success = pixmap.save(path, "PNG")
        if not success:
            raise ExportError(f"Failed to save exported PNG to {path}")
    except Exception as e:
        if isinstance(e, ExportError):
            raise e
        raise ExportError(f"Error exporting PNG: {e}") from e
