"""
Spectroo v3 — main entry point.

Usage:
    python main.py                  # auto-detect boot mode
    python main.py --mode desktop   # force desktop
    python main.py --mode web       # force web
    python main.py --dev            # enable dev mode (future use)
"""

import argparse
import logging
import os
import sys

from spectroo.core.config import load_config
from spectroo.core.exceptions import SpectrooError
from spectroo.system.boot_detect import detect_boot_mode, setup_logging

logger = logging.getLogger("spectroo.main")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")
LOG_PATH = os.path.expanduser("~/spectroo/logs/spectroo.log")


def run_desktop(config: dict, dev: bool = False) -> None:
    """Launch the PyQt5 desktop application."""
    from PyQt5.QtWidgets import QApplication
    from spectroo.ui.main_window import SpectrooMainWindow
    app = QApplication(sys.argv)
    app.setApplicationName("Spectroo")
    window = SpectrooMainWindow(config, dev=dev)
    window.show()
    sys.exit(app.exec_())


def run_web(config: dict, dev: bool = False) -> None:
    """Launch the FastAPI web server."""
    import uvicorn
    from spectroo.web.app import create_app
    web_app = create_app(config)
    host = config.get("web", {}).get("host", "0.0.0.0")
    port = config.get("web", {}).get("port", 8000)
    logger.info(f"Starting web server on {host}:{port}")
    uvicorn.run(web_app, host=host, port=port, log_level="info")


def main() -> None:
    parser = argparse.ArgumentParser(description="Spectroo v3")
    parser.add_argument(
        "--mode",
        choices=["desktop", "web", "auto"],
        default="auto",
        help="Boot mode (default: auto-detect)",
    )
    parser.add_argument(
        "--dev",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable developer mode (use --no-dev to disable)",
    )
    args = parser.parse_args()

    # Set up logging before anything else
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    setup_logging(LOG_PATH)
    logger.info("Spectroo v3 starting")

    # Load config — fail fast on missing/malformed per §20
    try:
        config = load_config(CONFIG_PATH)
    except SpectrooError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Determine boot mode
    if args.mode == "auto":
        mode = detect_boot_mode()
    else:
        mode = args.mode
    logger.info(f"Boot mode: {mode}")

    if args.dev:
        logger.info("Developer mode enabled")

    # Branch
    if mode == "desktop":
        run_desktop(config, dev=args.dev)
    else:
        run_web(config, dev=args.dev)


if __name__ == "__main__":
    main()
