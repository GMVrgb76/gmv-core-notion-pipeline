"""Pure path derivation for the GMV Core directory contract."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from gmv_core.config import GMVConfig


@dataclass(frozen=True, slots=True)
class GMVPaths:
    """Known GMV paths derived without filesystem access or directory creation."""

    home: Path

    @classmethod
    def from_config(cls, config: GMVConfig) -> GMVPaths:
        return cls(home=config.home)

    @classmethod
    def from_home(cls, home: str | os.PathLike[str]) -> GMVPaths:
        return cls.from_config(GMVConfig.from_home(home))

    @property
    def config(self) -> Path:
        return self.home / "00_CONFIG"

    @property
    def runtime(self) -> Path:
        return self.home / "01_RUNTIME"

    @property
    def logs(self) -> Path:
        return self.home / "04_LOGS"

    @property
    def output(self) -> Path:
        return self.home / "05_OUTPUT"

    @property
    def imports(self) -> Path:
        return self.home / "07_IMPORT"

    @property
    def database_directory(self) -> Path:
        return self.home / "09_DATABASE"

    @property
    def database(self) -> Path:
        return self.database_directory / "GMV.db"
