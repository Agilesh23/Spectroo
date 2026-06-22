import logging
import subprocess

logger = logging.getLogger("spectroo.system")


def request_shutdown() -> None:
    """
    Executes: sudo shutdown -h now
    Logs "Shutdown requested" at INFO level to logger "spectroo.system"
    before executing.
    Wraps subprocess.run in try/except — on failure logs the error
    at ERROR level but does not raise.
    """
    logger.info("Shutdown requested")
    try:
        subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
    except Exception as e:
        logger.error(f"Shutdown execution failed: {e}")
