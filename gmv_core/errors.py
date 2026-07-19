"""Typed errors shared by the GMV Core foundation."""


class GMVError(Exception):
    """Base class for expected GMV Core failures."""


class ConfigurationError(GMVError):
    """Raised when runtime configuration is absent or invalid."""


class DatabaseConfigurationError(GMVError):
    """Raised when a SQLite connection cannot enforce Core invariants."""


class PathValidationError(GMVError):
    """Raised when a path violates an explicit path contract."""


class MigrationError(GMVError):
    """Base class for migration failures."""


class MigrationStateError(MigrationError):
    """Raised when a database cannot safely accept the requested migration."""


class ValidationError(GMVError):
    """Base class for input contract violations."""


class CLIInputError(ValidationError):
    """Raised when a CLI argument violates its declared input contract."""

    exit_code = 2

    def __init__(self, argument: str, detail: str) -> None:
        self.argument = argument
        self.detail = detail
        super().__init__(f"invalid {argument}: {detail}")


class OIDValidationError(ValidationError):
    """Raised when an Object identifier violates the canonical OID contract."""


class OIDAllocationError(GMVError):
    """Raised when an OID cannot be allocated under the identity contract."""
