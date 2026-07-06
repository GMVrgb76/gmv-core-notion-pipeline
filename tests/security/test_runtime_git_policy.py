"""Runtime-data Git policy classification and content fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_runtime_git_policy as POLICY  # noqa: E402


def test_runtime_paths_are_protected_and_fixtures_are_not() -> None:
    assert POLICY.is_protected_path("09_DATABASE/GMV.db")
    assert POLICY.is_protected_path("04_LOGS/service.log")
    assert POLICY.is_protected_path(".DS_Store")
    assert not POLICY.is_protected_path("tests/fixtures/current_schema.sql")


def test_secret_and_private_path_fixtures_are_rejected() -> None:
    secret = POLICY.scan_text("password=super-secret-value", "fixture")  # gmv-policy-test-fixture
    private_path = POLICY.scan_text("source=/Users/person/private/file", "fixture")  # gmv-policy-test-fixture

    assert [finding.kind for finding in secret] == ["credential_assignment"]
    assert [finding.kind for finding in private_path] == ["personal_absolute_path"]


def test_redacted_and_relative_values_are_allowed() -> None:
    text = "password=[REDACTED]\nsource=tests/fixtures/current_schema.sql"
    assert POLICY.scan_text(text, "fixture") == []


def test_tracked_protected_path_is_reported_before_content(tmp_path: Path) -> None:
    findings = POLICY.audit_tracked_files(tmp_path, ["04_LOGS/private.log"])
    assert findings == [POLICY.Finding("protected_runtime_path", "04_LOGS/private.log", None)]


def test_current_tracked_tree_passes_policy() -> None:
    findings = POLICY.audit_tracked_files(ROOT, POLICY.tracked_files(ROOT))
    assert findings == []
