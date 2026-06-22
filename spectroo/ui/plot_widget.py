import math
import numpy as np
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QPolygonF, QFont, QLinearGradient


def wavelength_to_rgb(wavelength: float) -> tuple[float, float, float]:
    """
    Convert a wavelength in nm to an (R, G, B) tuple in the range [0.0, 1.0].
    Based on Bruton's algorithm with intensity fading at spectral extremes.
    """
    w = float(wavelength)
    if 380.0 <= w < 440.0:
        r = -(w - 440.0) / (440.0 - 380.0)
        g = 0.0
        b = 1.0
    elif 440.0 <= w < 490.0:
        r = 0.0
        g = (w - 440.0) / (490.0 - 440.0)
        b = 1.0
    elif 490.0 <= w < 510.0:
        r = 0.0
        g = 1.0
        b = -(w - 510.0) / (510.0 - 490.0)
    elif 510.0 <= w < 580.0:
        r = (w - 510.0) / (580.0 - 510.0)
        g = 1.0
        b = 0.0
    elif 580.0 <= w < 645.0:
        r = 1.0
        g = -(w - 645.0) / (645.0 - 580.0)
        b = 0.0
    elif 645.0 <= w <= 780.0:
        r = 1.0
        g = 0.0
        b = 0.0
    else:
        r = 0.0
        g = 0.0
        b = 0.0

    # Intensity factor (fades near the limit of human vision)
    if 380.0 <= w < 420.0:
        factor = 0.3 + 0.7 * (w - 380.0) / (420.0 - 380.0)
    elif 420.0 <= w < 700.0:
        factor = 1.0
    elif 700.0 <= w <= 780.0:
        factor = 0.3 + 0.7 * (780.0 - w) / (780.0 - 700.0)
    else:
        factor = 0.0

    # Standard gamma correction factor
    gamma = 0.8
    r_adj = (r * factor) ** gamma if r > 0.0 else 0.0
    g_adj = (g * factor) ** gamma if g > 0.0 else 0.0
    b_adj = (b * factor) ** gamma if b > 0.0 else 0.0

    return r_adj, g_adj, b_adj


class SpectrumPlotWidget(QWidget):
    """
    Custom widget for rendering the intensity spectrum curve using QPainter.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Colors — exact hex values, no substitutions
        self.bg_color = QColor("#ffffff")
        self.grid_color = QColor("#eeeeee")
        self.axis_color = QColor("#555555")
        self.text_color = QColor("#333333")
        self.curve_color = QColor("#444444")
        self.peak_line_color = QColor("#ff4444")
        self.inspect_line_color = QColor("#666666")

        # Data
        self.wavelengths: np.ndarray | None = None
        self.intensities: np.ndarray | None = None
        self.peaks: list[int] = []
        self.peaks_visible: bool = True

        # Display mode
        self.fill_mode: str = "color"   # "color" | "plain"
        self.inspect_x: float | None = None
        self.inspect_idx: int | None = None

        # Plot margins — exact values, no substitutions
        self.margin_left   = 65
        self.margin_right  = 35
        self.margin_top    = 35
        self.margin_bottom = 50

        # Zoom/pan state
        self.zoom_xmin: float | None = None
        self.zoom_xmax: float | None = None
        self._pan_active: bool = False
        self._pan_start_x: int | None = None
        self._pan_start_zoom: tuple | None = None

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_data(self, wavelengths, intensities, peaks) -> None:
        if wavelengths is None or intensities is None:
            return
        if len(wavelengths) == 0 or len(intensities) == 0:
            return
        self.wavelengths = np.array(wavelengths)
        self.intensities = np.array(intensities)
        self.peaks = list(peaks)
        self.update()

    def set_fill_mode(self, mode: str) -> None:
        if mode in ("color", "plain"):
            self.fill_mode = mode
            self.update()

    def set_peaks_visible(self, visible: bool) -> None:
        self.peaks_visible = visible
        self.update()

    def _get_zoom_range(self) -> tuple[float, float]:
        if self.wavelengths is None:
            return (0.0, 2591.0)
        xmin = self.zoom_xmin if self.zoom_xmin is not None else float(self.wavelengths[0])
        xmax = self.zoom_xmax if self.zoom_xmax is not None else float(self.wavelengths[-1])
        return (xmin, xmax)

    def wheelEvent(self, event) -> None:
        if self.wavelengths is None:
            return
        delta = event.angleDelta().y()
        factor = 0.8 if delta > 0 else 1.25
        xmin, xmax = self._get_zoom_range()
        plot_w = self.width() - self.margin_left - self.margin_right
        if plot_w <= 0:
            return
        mouse_x = event.x() - self.margin_left
        t = max(0.0, min(1.0, mouse_x / plot_w))
        center = xmin + t * (xmax - xmin)
        new_half = (xmax - xmin) * factor / 2
        full_min = float(self.wavelengths[0])
        full_max = float(self.wavelengths[-1])
        new_min = max(full_min, center - new_half)
        new_max = min(full_max, center + new_half)
        if new_max - new_min < 5:
            return
        if new_min <= full_min and new_max >= full_max:
            self.zoom_xmin = None
            self.zoom_xmax = None
        else:
            self.zoom_xmin = new_min
            self.zoom_xmax = new_max
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.wavelengths is None:
            return
        if self._pan_active and self._pan_start_zoom is not None:
            dx = event.x() - self._pan_start_x
            xmin0, xmax0 = self._pan_start_zoom
            plot_w = self.width() - self.margin_left - self.margin_right
            data_per_px = (xmax0 - xmin0) / plot_w if plot_w > 0 else 1
            shift = -dx * data_per_px
            full_min = float(self.wavelengths[0])
            full_max = float(self.wavelengths[-1])
            rng = xmax0 - xmin0
            new_min = max(full_min, xmin0 + shift)
            new_max = new_min + rng
            if new_max > full_max:
                new_max = full_max
                new_min = new_max - rng
            self.zoom_xmin = new_min
            self.zoom_xmax = new_max
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._pan_active = False

    def mouseDoubleClickEvent(self, event) -> None:
        self.zoom_xmin = None
        self.zoom_xmax = None
        self.update()

    def mousePressEvent(self, event) -> None:
        if self.wavelengths is None or len(self.wavelengths) == 0:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.RightButton:
            self.zoom_xmin = None
            self.zoom_xmax = None
            self.update()
            return

        is_pan_click = (event.button() == Qt.MidButton) or (
            event.button() == Qt.LeftButton and bool(event.modifiers() & Qt.ControlModifier)
        )
        if is_pan_click:
            self._pan_active = True
            self._pan_start_x = event.x()
            self._pan_start_zoom = self._get_zoom_range()
            return

        if event.button() == Qt.LeftButton:
            x_start = self.margin_left
            plot_w = self.width() - self.margin_left - self.margin_right
            if plot_w <= 0:
                return

            click_x = event.x()
            if click_x < x_start:
                click_x = x_start
            elif click_x > x_start + plot_w:
                click_x = x_start + plot_w

            xmin, xmax = self._get_zoom_range()
            frac = (click_x - x_start) / float(plot_w)
            target = xmin + frac * (xmax - xmin)

            idx = np.abs(self.wavelengths - target).argmin()

            self.inspect_idx = int(idx)
            self.inspect_x = float(self.wavelengths[idx])
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 1. Fill entire rect with self.bg_color
        painter.fillRect(self.rect(), self.bg_color)

        # 2. Compute margins and sizes
        x_start = self.margin_left
        x_end = self.width() - self.margin_right
        y_start = self.margin_top
        y_end = self.height() - self.margin_bottom
        plot_w = x_end - x_start
        plot_h = y_end - y_start

        if plot_w <= 0 or plot_h <= 0:
            return

        # 3. Draw Y axis label
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.setPen(QPen(self.text_color, 1))
        painter.save()
        painter.translate(x_start - 48, y_start + plot_h / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-100, -10, 200, 20), Qt.AlignCenter, "Intensity (Counts)")
        painter.restore()

        # 4. Draw X axis label
        has_data = self.wavelengths is not None and self.intensities is not None
        x_label = "Wavelength (nm)"
        if has_data:
            if (self.wavelengths[-1] - self.wavelengths[0]) < 200:
                x_label = "Pixel"
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.setPen(QPen(self.text_color, 1))
        painter.drawText(QRectF(x_start, y_end + 28, plot_w, 20), Qt.AlignCenter, x_label)

        # 5. If no data
        if not has_data:
            painter.setPen(QPen(self.axis_color, 1))
            painter.drawRect(x_start, y_start, plot_w, plot_h)
            painter.setFont(QFont("Arial", 11))
            painter.drawText(QRectF(x_start, y_start, plot_w, plot_h), Qt.AlignCenter, "Awaiting Frame Data...")
            return

        # 6. Compute range and ticks
        x_min, x_max = self._get_zoom_range()
        y_min = 0.0
        y_max = max(1.0, float(np.max(self.intensities)))
        y_limit = y_max * 1.15

        # 7. Detect calibration
        is_calibrated = (self.wavelengths[-1] - self.wavelengths[0]) > 200

        # 8. Adaptive X ticks
        range_x = x_max - x_min
        if range_x > 0:
            raw_step = range_x / 6.0
            exponent = math.floor(math.log10(raw_step))
            fraction = raw_step / (10 ** exponent)
            if fraction < 1.5:
                nice_fraction = 1.0
            elif fraction < 3.0:
                nice_fraction = 2.0
            elif fraction < 7.0:
                nice_fraction = 5.0
            else:
                nice_fraction = 10.0
            step = nice_fraction * (10 ** exponent)
        else:
            step = 1.0

        x_ticks = []
        start_tick = math.ceil(x_min / step) * step
        while start_tick <= x_max:
            x_ticks.append(start_tick)
            start_tick += step

        y_ticks = [i * (y_limit / 4.0) for i in range(5)]

        # 9. Draw ticks and grids
        painter.setFont(QFont("Arial", 8))

        # Horizontal grid + Y label
        for y_val in y_ticks:
            py = y_end - (y_val / y_limit) * plot_h
            painter.setPen(QPen(self.grid_color, 1, Qt.SolidLine))
            painter.drawLine(QPointF(x_start, py), QPointF(x_end, py))
            painter.setPen(QPen(self.axis_color, 1))
            painter.drawLine(QPointF(x_start - 5, py), QPointF(x_start, py))
            painter.setPen(QPen(self.text_color, 1))
            painter.drawText(QRectF(x_start - 55, py - 10, 48, 20), Qt.AlignRight | Qt.AlignVCenter, f"{int(round(y_val))}")

        # Vertical grid + X label
        for x_val in x_ticks:
            if x_max == x_min:
                continue
            px = x_start + (x_val - x_min) / (x_max - x_min) * plot_w
            if px < x_start or px > x_end:
                continue
            painter.setPen(QPen(self.grid_color, 1, Qt.SolidLine))
            painter.drawLine(QPointF(px, y_start), QPointF(px, y_end))
            painter.setPen(QPen(self.axis_color, 1))
            painter.drawLine(QPointF(px, y_end), QPointF(px, y_end + 5))
            painter.setPen(QPen(self.text_color, 1))
            painter.drawText(QRectF(px - 30, y_end + 8, 60, 20), Qt.AlignCenter, f"{int(round(x_val))}")

        # 10. Draw axis border rect
        painter.setPen(QPen(self.axis_color, 1))
        painter.drawRect(x_start, y_start, plot_w, plot_h)

        # 11. Compute sub-range
        indices = np.where((self.wavelengths >= x_min) & (self.wavelengths <= x_max))[0]
        if len(indices) > 0:
            start_idx = max(0, indices[0] - 1)
            end_idx = min(len(self.wavelengths) - 1, indices[-1] + 1)
        else:
            start_idx = 0
            end_idx = len(self.wavelengths) - 1

        sub_wl = self.wavelengths[start_idx:end_idx + 1]
        sub_int = self.intensities[start_idx:end_idx + 1]

        if x_max != x_min:
            px_arr = x_start + (sub_wl - x_min) / (x_max - x_min) * plot_w
        else:
            px_arr = np.full_like(sub_wl, x_start)
        py_arr = y_end - (sub_int / y_limit) * plot_h
        points = QPolygonF([QPointF(x, y) for x, y in zip(px_arr, py_arr)])

        # 12. Clip Rect
        painter.save()
        painter.setClipRect(x_start, y_start, plot_w, plot_h)

        # 13. Build fill polygon
        fill_px = np.concatenate(([px_arr[0]], px_arr, [px_arr[-1]]))
        fill_py = np.concatenate(([y_end], py_arr, [y_end]))
        fill_path = QPolygonF([QPointF(x, y) for x, y in zip(fill_px, fill_py)])

        # 14. Fill curve
        if self.fill_mode == "color":
            grad = QLinearGradient(x_start, 0, x_end, 0)
            num_stops = 60
            full_xmax = float(self.wavelengths[-1])
            for stop_i in range(num_stops + 1):
                t = stop_i / float(num_stops)
                stop_val = x_min + t * (x_max - x_min)
                if is_calibrated:
                    wl = stop_val
                else:
                    if full_xmax > 0:
                        wl = 380.0 + (stop_val / full_xmax) * (780.0 - 380.0)
                    else:
                        wl = 380.0
                r, g, b = wavelength_to_rgb(wl)
                grad.setColorAt(t, QColor(int(r * 255), int(g * 255), int(b * 255)))
            painter.setBrush(QBrush(grad))
        else:
            painter.setBrush(QBrush(QColor("#f0f0f0")))

        painter.setPen(Qt.NoPen)
        painter.drawPolygon(fill_path)

        # 15. Draw curve line
        painter.setPen(QPen(self.curve_color, 2, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(points)

        # 16. Draw peak indicators
        if self.peaks_visible:
            painter.setFont(QFont("Arial", 8))
            for idx in self.peaks:
                if idx < 0 or idx >= len(self.wavelengths):
                    continue
                pk_x = self.wavelengths[idx]
                if pk_x < x_min or pk_x > x_max:
                    continue
                pk_y = self.intensities[idx]
                if x_max != x_min:
                    px = x_start + (pk_x - x_min) / (x_max - x_min) * plot_w
                else:
                    px = x_start
                py = y_end - (pk_y / y_limit) * plot_h

                painter.setPen(QPen(self.peak_line_color, 1, Qt.DashLine))
                painter.drawLine(QPointF(px, y_end), QPointF(px, py))

                painter.setPen(QPen(self.text_color, 1))
                label = f"{int(round(pk_x))} nm" if is_calibrated else f"Px {pk_x}"
                painter.drawText(QRectF(px - 40, py - 20, 80, 15), Qt.AlignCenter, label)

        # 17. Draw inspect overlay
        if self.inspect_x is not None and self.inspect_idx is not None:
            idx = self.inspect_idx
            if 0 <= idx < len(self.wavelengths):
                inspect_w = self.inspect_x
                if x_min <= inspect_w <= x_max:
                    inspect_y = self.intensities[idx]
                    if x_max != x_min:
                        px = x_start + (inspect_w - x_min) / (x_max - x_min) * plot_w
                    else:
                        px = x_start
                    py = y_end - (inspect_y / y_limit) * plot_h

                    painter.setPen(QPen(self.inspect_line_color, 1.5, Qt.DashLine))
                    painter.drawLine(QPointF(px, y_start), QPointF(px, y_end))

                    card_w = 105
                    card_h = 52
                    card_x = px + 10
                    card_y = py - 60

                    if card_x + card_w > x_end:
                        card_x = px - 115
                    if card_y < y_start:
                        card_y = py + 10

                    card_rect = QRectF(card_x, card_y, card_w, card_h)

                    painter.setPen(QPen(QColor("#cccccc"), 1))
                    painter.setBrush(QBrush(QColor("#ffffff")))
                    painter.drawRoundedRect(card_rect, 4, 4)

                    painter.setFont(QFont("Arial", 8))
                    painter.setPen(QPen(self.text_color, 1))
                    tooltip_str = (
                        f"{inspect_w:.1f} nm\n{inspect_y:.1f} cts\nPx {idx}"
                        if is_calibrated
                        else f"Px {idx}\n{inspect_y:.1f} cts"
                    )
                    painter.drawText(card_rect, Qt.AlignCenter, tooltip_str)

        # 18. Restore
        painter.restore()
