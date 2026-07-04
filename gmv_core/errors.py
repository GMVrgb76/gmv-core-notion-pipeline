"""Typed errors shared by the GMV Core foundation."""


class GMVError(Exception):
    """Base class for expected GMV Core failures."""


class ConfigurationError(GMVError):
    """Raised when runtime configuration is absent or invalid."""


class PathValidationError(GMVError):
    """Raised when a path violates an explicit path contract."""
