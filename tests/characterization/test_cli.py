"""Characterize representative behavior of the current Bash CLI."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from tests.characterization.conftest import CLI

ROOT = Path(__file__).resolve().parents[2]
OBJECT_SERVICE = ROOT / "10_API" / "object_service.py"
SERVICE_SERVICE = ROOT / "10_API" / "service_service.py"
SEARCH_SERVICE = ROOT / "10_API" / "search_service.py"


def _run_cli(cli_environment: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), *arguments],
        env=cli_environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_object_service(
    cli_environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    # 11_CLI/gmv's `object` subcommand resolves its script via $HOME, which
    # breaks under HOME-isolated tests; invoke the script directly instead
    # (pre-existing CLI defect, out of scope for this slice).
    return subprocess.run(
        [sys.executable, str(OBJECT_SERVICE), *arguments],
        env=cli_environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_service_service(
    cli_environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    # Same pre-existing $HOME CLI defect as _run_object_service; invoke the
    # script directly instead of via 11_CLI/gmv's `service` subcommand.
    return subprocess.run(
        [sys.executable, str(SERVICE_SERVICE), *arguments],
        env=cli_environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_search_service(
    cli_environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    # Same pre-existing $HOME CLI defect as _run_object_service; invoke the
    # script directly instead of via 11_CLI/gmv's `search` subcommand.
    return subprocess.run(
        [sys.executable, str(SEARCH_SERVICE), *arguments],
        env=cli_environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_status_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_cli(
        cli_environment,
        "status",
        "--json",
        "--now",
        "2026-07-06T12:00:00+00:00",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert result.stderr == ""
    assert payload["state"] == "failed"
    assert payload["observed_at"] == "2026-07-06T12:00:00+00:00"
    assert "SYSTEM READY" not in result.stdout


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


def test_object_list_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_object_service(cli_environment, "list")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "PLG-000001|Plugin|Fixture Plugin|active\n"
        "RES-000001|Resource|fixture.txt|active\n"
        "SRV-000001|Service|Fixture Service|active\n"
        "SYS-000001|System|Fixture System|active\n"
    )


def test_object_count_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_object_service(cli_environment, "count")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "Plugin|1\nResource|1\nService|1\nSystem|1\n"
    )


def test_object_show_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_object_service(cli_environment, "show", "SRV-000001")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "OID: SRV-000001\n"
        "Type: Service\n"
        "Name: Fixture Service\n"
        "Status: active\n"
        "Created: 2026-01-01T00:00:00\n"
        "Updated: 2026-01-01T00:00:00\n"
    )


def test_object_show_missing_oid_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_object_service(cli_environment, "show", "SRV-000099")

    assert result.returncode == 1
    assert result.stdout == "Object not found\n"
    assert result.stderr == ""


def test_service_list_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_service_service(cli_environment, "list")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "SRV-000001|Fixture Service|active|2026-01-01T00:00:00|2026-01-01T00:00:00\n"
    )


def test_service_runs_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_service_service(cli_environment, "runs")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "engine|1||fixture_engine|2026-01-01T01:00:00|OK|1.0\n"
        "service|1|SRV-000001|Fixture Service|2026-01-01T01:00:00|OK|1.0\n"
    )


def test_service_show_output_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_service_service(cli_environment, "show", "SRV-000001")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "OID: SRV-000001\n"
        "Name: Fixture Service\n"
        "Status: active\n"
        "Created: 2026-01-01T00:00:00\n"
        "Updated: 2026-01-01T00:00:00\n"
    )


def test_service_show_missing_oid_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_service_service(cli_environment, "show", "SRV-000099")

    assert result.returncode == 1
    assert result.stdout == "Service not found\n"
    assert result.stderr == ""


def test_search_matches_across_object_and_resource_is_characterized(
    cli_environment: dict[str, str],
) -> None:
    result = _run_search_service(cli_environment, "fixture")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "object|PLG-000001|Fixture Plugin|name:Fixture Plugin\n"
        "object|RES-000001|fixture.txt|name:fixture.txt\n"
        "object|SRV-000001|Fixture Service|name:Fixture Service\n"
        "object|SYS-000001|Fixture System|name:Fixture System\n"
        "resource|RES-000001|fixture.txt|filename:fixture.txt\n"
    )


def test_search_matches_event_description_is_characterized(
    cli_environment: dict[str, str],
) -> None:
    result = _run_search_service(cli_environment, "synthetic")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "event|1|fixture_event|description:Synthetic event\n"


def test_search_matches_relation_type_is_characterized(
    cli_environment: dict[str, str],
) -> None:
    result = _run_search_service(cli_environment, "uses")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "relation|1|SYS-000001->RES-000001|relation_type:uses\n"


def test_search_no_match_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_search_service(cli_environment, "nomatchxyz")

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_search_missing_query_is_characterized(cli_environment: dict[str, str]) -> None:
    result = _run_search_service(cli_environment)

    assert result.returncode == 2
    assert result.stdout == "Usage: search_service.py <query>\n"
    assert result.stderr == ""
