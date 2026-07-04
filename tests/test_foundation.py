"""Acceptance tests scoped to the S001-03 foundation package."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from gmv_core.config import GMVConfig, load_config
from gmv_core.errors import ConfigurationError
from gmv_core.paths import GMVPaths


def test_injected_home_derives_paths_without_creating_them(tmp_path: Path) -> None:
    home = tmp_path / "injected-core"

    config = GMVConfig.from_home(home)
    paths = GMVPaths.from_config(config)

    assert config.home == home
    assert paths.database == home / "09_DATABASE" / "GMV.db"
    assert not home.exists()


def test_configuration_resolution_is_explicit(tmp_path: Path) -> None:
    configured = tmp_path / "configured-core"

    assert load_config(environ={"GMV_HOME": str(configured)}).home == configured
    assert load_config(environ={"HOME": str(tmp_path)}).home == tmp_path / ".gmv_core"

    with pytest.raises(ConfigurationError):
        load_config(environ={})


def test_imports_have_no_output_or_filesystem_side_effects(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.update(
        {
            "GMV_HOME": str(tmp_path / "injected-core"),
            "HOME": str(tmp_path),
            "PYTHONPATH": str(repository),
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import gmv_core; import gmv_core.config; import gmv_core.errors",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []
