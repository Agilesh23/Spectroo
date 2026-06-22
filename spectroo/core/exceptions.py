"""Core custom exceptions for the Spectroo application."""

class SpectrooError(Exception):
    """Base exception class for all Spectroo-specific application errors."""
    pass


class ConfigError(SpectrooError):
    """Raised when config.toml is missing, unreadable, or malformed."""
    pass


class CameraNotFoundError(SpectrooError):
    """Raised when the camera sensor (e.g., OV5647) is not found or fails to initialize."""
    pass


class DarkFrameMissingError(SpectrooError):
    """Raised when dark subtraction is requested but no dark frame calibration exists."""
    pass


class CalibrationError(SpectrooError):
    """Raised when calibration fitting fails, e.g. when fewer than min_points are provided."""
    pass


class StorageUnavailableError(SpectrooError):
    """Raised when the SQLite database or file exports are inaccessible."""
    pass


class DiskFullError(SpectrooError):
    """Raised when writing to disk fails due to insufficient storage space (ENOSPC)."""
    pass


class DeviceBusyError(SpectrooError):
    """Raised when a client attempts to connect to a service that is already locked by another user."""
    pass
