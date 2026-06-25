import os
import re
import subprocess
import time
from typing import Optional

_last_temp: Optional[float] = None
_last_read_time: float = 0.0
_cache_duration: float = 2.0  # seconds
CPU_TEMP_WARN_THRESHOLD: float = 80.0


def is_cpu_temp_warning(temp: Optional[float]) -> bool:
    """
    Returns True if the temperature is equal to or greater than the warning threshold,
    False otherwise (or if temp is None).
    """
    if temp is None:
        return False
    return temp >= CPU_TEMP_WARN_THRESHOLD


def get_cpu_temp_c(bypass_cache: bool = False) -> Optional[float]:
    """
    Retrieves the CPU temperature in degrees Celsius.
    
    Tries reading from sysfs first (/sys/class/thermal/thermal_zone0/temp),
    then falls back to vcgencmd measure_temp. Returns None if both fail or
    the output is malformed.
    
    Includes a 2-second rate-limiting cache to avoid high CPU overhead
    during rapid polling/streaming.
    """
    global _last_temp, _last_read_time
    now = time.time()
    
    if not bypass_cache and _last_temp is not None and (now - _last_read_time) < _cache_duration:
        return _last_temp
        
    temp = _read_cpu_temp_uncached()
    _last_temp = temp
    _last_read_time = now
    return temp


def _read_cpu_temp_uncached() -> Optional[float]:
    # 1. Try reading /sys/class/thermal/thermal_zone0/temp
    try:
        temp_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(temp_path):
            with open(temp_path, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val:
                    return float(val) / 1000.0
    except (OSError, ValueError):
        pass

    # 2. Try vcgencmd measure_temp fallback
    try:
        res = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            check=True
        )
        # vcgencmd output typically looks like: temp=48.5'C
        match = re.search(r"temp=(\d+\.?\d*)'C", res.stdout)
        if match:
            return float(match.group(1))
    except Exception:
        pass

    return None
