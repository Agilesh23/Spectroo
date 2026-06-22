# Spectroo v3 — UI palette and layout constants.
# All values extracted from the v1 reference implementation.
# Import these instead of hardcoding hex strings or pixel values anywhere in the UI.

from PyQt5.QtGui import QColor, QFont

# --- Color palette ---
COLOR_BG          = QColor("#ffffff")
COLOR_GRID        = QColor("#eeeeee")
COLOR_AXIS        = QColor("#555555")
COLOR_TEXT        = QColor("#333333")
COLOR_TEXT_DIM    = QColor("#666666")
COLOR_CURVE       = QColor("#444444")
COLOR_PEAK        = QColor("#ff4444")
COLOR_INSPECT     = QColor("#666666")
COLOR_BORDER      = QColor("#dcdcdc")
COLOR_BTN_BG      = QColor("#fafafa")
COLOR_BTN_BORDER  = QColor("#cccccc")
COLOR_BTN_HOVER   = QColor("#f0f0f0")
COLOR_BTN_PRESSED = QColor("#e5e5e5")
COLOR_BTN_ACTIVE  = QColor("#0066cc")
COLOR_BTN_ACTIVE_TEXT = QColor("#ffffff")
COLOR_BTN_ACTIVE_BORDER = QColor("#0055bb")
COLOR_PLAIN_FILL  = QColor("#f0f0f0")

# --- Layout constants ---
CONTROL_PANEL_WIDTH = 200   # px, fixed
STATUS_BAR_HEIGHT   = 28    # px, fixed
PLOT_MARGIN_LEFT    = 65
PLOT_MARGIN_RIGHT   = 35
PLOT_MARGIN_TOP     = 35
PLOT_MARGIN_BOTTOM  = 50

# --- Fonts ---
FONT_AXIS_LABEL = QFont("Arial", 10, QFont.Bold)
FONT_SECTION_HEADER = QFont("Arial", 8, QFont.Bold)
FONT_TICK  = QFont("Arial", 8)
FONT_BODY  = QFont("Arial", 11)
FONT_SMALL = QFont("Arial", 8)
