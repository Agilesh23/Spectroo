import os
import sys
import glob
import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("spectroo.boot")


def detect_boot_mode() -> str:
    """
    Returns "desktop" if a display is detected, "web" otherwise.
    Detection logic (in order):
    1. Check for DSI display: read /sys/bus/platform/drivers/vc4_dsi/
       — if the directory exists and is non-empty, return "desktop"
    2. Check for HDMI: iterate /sys/class/drm/card*-HDMI-*/status
       — if any file contains the word "connected", return "desktop"
    3. Fall back to "web"
    Log the decision at INFO level using Python's logging module.
    Logger name: "spectroo.boot"
    """
    # 1. Check for DSI display
    dsi_dir = "/sys/bus/platform/drivers/vc4_dsi/"
    if os.path.isdir(dsi_dir):
        try:
            if os.listdir(dsi_dir):
                logger.info("Boot mode: desktop")
                return "desktop"
        except Exception:
            pass

    # 2. Check for HDMI status
    hdmi_files = glob.glob("/sys/class/drm/card*-HDMI-*/status")
    for path in hdmi_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                if "connected" in content:
                    logger.info("Boot mode: desktop")
                    return "desktop"
        except Exception:
            pass

    # 3. Fallback to web
    logger.info("Boot mode: web")
    return "web"


def setup_logging(log_path: str) -> None:
    """
    Configures the root Spectroo logger.
    - RotatingFileHandler at log_path, maxBytes=5*1024*1024, backupCount=3
    - StreamHandler to stderr
    - Format: "%(asctime)s %(levelname)s %(name)s — %(message)s"
    - Level: logging.INFO
    Logger name configured: "spectroo"  (parent of all spectroo.* loggers)
    """
    parent_dir = os.path.dirname(os.path.abspath(log_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    spectroo_logger = logging.getLogger("spectroo")
    spectroo_logger.setLevel(logging.INFO)

    # Clear any existing handlers to prevent duplicates in testing
    spectroo_logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")

    # File handler
    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(formatter)
    spectroo_logger.addHandler(file_handler)

    # Stream handler
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    spectroo_logger.addHandler(stream_handler)
