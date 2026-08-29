"""Explicit, side-effect-free configuration for GMV Core."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from gmv_core.errors import ConfigurationError

GMV_HOME_ENV = "GMV_HOME"


@dataclass(frozen=True, slots=True)
class GMVConfig:
    """Runtime configuration rooted at an explicitly selected GMV home."""

    home: Path

    @classmethod
    def from_home(cls, home: str | os.PathLike[str]) -> GMVConfig:
        """Build configuration without reading environment or filesystem state."""
        path = Path(home)
        if not str(path):
            raise ConfigurationError("GMV home must not be empty")
        return cls(home=path)


def load_config(
    home: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> GMVConfig:
    """Resolve configuration when called, preferring an injected home."""
    if home is not None:
        return GMVConfig.from_home(home)

    environment = os.environ if environ is None else environ
    configured_home = environment.get(GMV_HOME_ENV)
    if configured_home:
        return GMVConfig.from_home(configured_home)

    user_home = environment.get("HOME")
    if not user_home:
        raise ConfigurationError(
            "GMV home is undefined; pass home or set GMV_HOME or HOME"
        )
    return GMVConfig.from_home(Path(user_home) / ".gmv_core")
