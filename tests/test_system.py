import sys
import os
import logging
import subprocess
from unittest.mock import patch, MagicMock, mock_open
import pytest


from spectroo.system.boot_detect import detect_boot_mode, setup_logging
from spectroo.system.shutdown import request_shutdown
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import main as main_module


# 1. test_detect_boot_mode_returns_string
def test_detect_boot_mode_returns_string():
    mode = detect_boot_mode()
    assert mode in ("desktop", "web")


# 2. test_detect_boot_mode_web_on_windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only behaviour")
def test_detect_boot_mode_web_on_windows():
    assert detect_boot_mode() == "web"


# 3. test_setup_logging_creates_handler
def test_setup_logging_creates_handler(tmp_path):
    log_file = tmp_path / "spectroo.log"
    try:
        setup_logging(str(log_file))
        logger = logging.getLogger("spectroo")
        assert len(logger.handlers) > 0
    finally:
        # Clean up handlers to avoid polluting other tests
        logger = logging.getLogger("spectroo")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)


# 4. test_setup_logging_creates_log_dir
def test_setup_logging_creates_log_dir(tmp_path):
    nested_dir = tmp_path / "logs" / "nested"
    log_file = nested_dir / "spectroo.log"
    try:
        setup_logging(str(log_file))
        assert nested_dir.exists()
        # Verify log file is writable
        logger = logging.getLogger("spectroo")
        logger.info("Test log entry")
        assert log_file.exists()
        with open(log_file, "r") as f:
            content = f.read()
            assert "Test log entry" in content
    finally:
        logger = logging.getLogger("spectroo")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)


# 5. test_request_shutdown_does_not_raise
@patch("subprocess.run")
def test_request_shutdown_does_not_raise(mock_run):
    try:
        request_shutdown()
    except Exception as e:
        pytest.fail(f"request_shutdown raised an exception: {e}")
    mock_run.assert_called_once_with(["sudo", "shutdown", "-h", "now"], check=True)


# 6. test_request_shutdown_logs_on_failure
@patch("subprocess.run", side_effect=OSError("Mock failure"))
def test_request_shutdown_logs_on_failure(mock_run):
    try:
        request_shutdown()
    except Exception as e:
        pytest.fail(f"request_shutdown allowed an exception to propagate: {e}")
    mock_run.assert_called_once()


# 7. test_main_imports_cleanly
def test_main_imports_cleanly():
    assert hasattr(main_module, "main")
    assert callable(main_module.main)


# 8. test_run_desktop_and_run_web_exist
def test_run_desktop_and_run_web_exist():
    assert hasattr(main_module, "run_desktop")
    assert callable(main_module.run_desktop)
    assert hasattr(main_module, "run_web")
    assert callable(main_module.run_web)


# 9. test_get_cpu_temp_sysfs_success
@patch("os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data="45200\n")
def test_get_cpu_temp_sysfs_success(mock_file, mock_exists):
    from spectroo.system.temp import get_cpu_temp_c
    temp = get_cpu_temp_c(bypass_cache=True)
    assert temp == 45.2
    mock_exists.assert_called_once_with("/sys/class/thermal/thermal_zone0/temp")
    mock_file.assert_called_once_with("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8")


# 10. test_get_cpu_temp_sysfs_missing_falls_to_vcgencmd
@patch("os.path.exists", return_value=False)
@patch("subprocess.run")
def test_get_cpu_temp_sysfs_missing_falls_to_vcgencmd(mock_run, mock_exists):
    from spectroo.system.temp import get_cpu_temp_c
    mock_completed = MagicMock()
    mock_completed.returncode = 0
    mock_completed.stdout = "temp=48.5'C\n"
    mock_run.return_value = mock_completed

    temp = get_cpu_temp_c(bypass_cache=True)
    assert temp == 48.5
    mock_exists.assert_called_once()
    mock_run.assert_called_once_with(["vcgencmd", "measure_temp"], capture_output=True, text=True, check=True)


# 11. test_get_cpu_temp_sysfs_oserror_falls_to_vcgencmd
@patch("os.path.exists", return_value=True)
@patch("builtins.open", side_effect=OSError("Read error"))
@patch("subprocess.run")
def test_get_cpu_temp_sysfs_oserror_falls_to_vcgencmd(mock_run, mock_file, mock_exists):
    from spectroo.system.temp import get_cpu_temp_c
    mock_completed = MagicMock()
    mock_completed.returncode = 0
    mock_completed.stdout = "temp=52.1'C\n"
    mock_run.return_value = mock_completed

    temp = get_cpu_temp_c(bypass_cache=True)
    assert temp == 52.1
    mock_exists.assert_called_once()
    mock_run.assert_called_once_with(["vcgencmd", "measure_temp"], capture_output=True, text=True, check=True)


# 12. test_get_cpu_temp_both_fail
@patch("os.path.exists", return_value=False)
@patch("subprocess.run", side_effect=FileNotFoundError)
def test_get_cpu_temp_both_fail(mock_run, mock_exists):
    from spectroo.system.temp import get_cpu_temp_c
    temp = get_cpu_temp_c(bypass_cache=True)
    assert temp is None


# 13. test_get_cpu_temp_vcgencmd_malformed
@patch("os.path.exists", return_value=False)
@patch("subprocess.run")
def test_get_cpu_temp_vcgencmd_malformed(mock_run, mock_exists):
    from spectroo.system.temp import get_cpu_temp_c
    mock_completed = MagicMock()
    mock_completed.returncode = 0
    mock_completed.stdout = "malformed output 12345\n"
    mock_run.return_value = mock_completed

    temp = get_cpu_temp_c(bypass_cache=True)
    assert temp is None

