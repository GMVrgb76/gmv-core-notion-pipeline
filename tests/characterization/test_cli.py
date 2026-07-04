"""Characterize representative behavior of the current Bash CLI."""

from __future__ import annotations

import subprocess
import textwrap

from tests.characterization.conftest import CLI


def _run_cli(cli_environment: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), *arguments],
        env=cli_environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_status_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_cli(cli_environment, "status")

    expected = textwrap.dedent(
        """
        ==================================================
                       GMV OS STATUS
        ==================================================

        SERVICES

        LAST ENGINE RUNS
        1|fixture_engine|2026-01-01T01:00:00|OK

        REGISTERED SERVICES
        SRV-000001|Fixture Service|active

        REGISTERED PLUGINS
        PLG-000001|Fixture Plugin|0.0|active

        OBJECT COUNTS
        Plugin|1
        Resource|1
        Service|1
        System|1

        ==================================================
        SYSTEM READY
        ==================================================
        """
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == expected


def test_doctor_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_cli(cli_environment, "doctor")

    expected = textwrap.dedent(
        """
        ==================================================
                       GMV DOCTOR
        ==================================================

        [1] DATABASE
        ok

        [2] OBJECT COUNTS
        Plugin|1
        Resource|1
        Service|1
        System|1

        [3] REGISTERED SERVICES
        Fixture Service|active

        [4] REGISTERED PLUGINS
        Fixture Plugin|active

        [5] DATABASE VIEWS
        import_queue_view
        plugin_registry_view
        plugin_services_view
        relation_view
        resource_view
        service_registry_view
        timeline_view

        [6] LAST ENGINE RUNS
        fixture_engine|2026-01-01T01:00:00|OK

        [7] LAUNCHAGENTS

        [8] ORPHAN SERVICE RUNS
        0

        [9] ORPHAN EVENTS
        0

        [10] PENDING PLUGINS

        ==================================================
        GMV DOCTOR COMPLETED
        ==================================================
        """
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == expected


def test_missing_argument_exit_contract(cli_environment: dict[str, str]) -> None:
    result = _run_cli(cli_environment, "object", "show")

    assert result.returncode == 2
    assert result.stdout == "Usage: gmv object show <OID>\n"
    assert result.stderr == ""
