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
