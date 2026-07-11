"""Configuration file loader for Spectroo v3."""

import tomllib
from spectroo.core.exceptions import ConfigError


def load_config(path: str = "config.toml") -> dict:
    """Load and parse config.toml via stdlib tomllib.

    Raises:
        ConfigError: If the file is missing, unreadable, or fails to parse.
    """
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"Configuration file not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Configuration file at {path} is not valid TOML: {e}") from e
    except Exception as e:
        raise ConfigError(f"Error reading configuration file at {path}: {e}") from e


def write_calibration_to_config(config_path: str, coefficients: list[float], degree: int, n_points: int) -> None:
    """Write the calibration parameters back to the config.toml file using tomli_w."""
    import tomli_w
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
            
        if "calibration" not in data:
            data["calibration"] = {}
            
        data["calibration"]["coefficients"] = coefficients
        data["calibration"]["degree"] = degree
        data["calibration"]["n_points"] = n_points

        with open(config_path, "wb") as f:
            tomli_w.dump(data, f)
    except Exception as e:
        raise RuntimeError(f"Failed to write calibration config back to disk: {e}")

