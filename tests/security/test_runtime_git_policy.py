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
    assert POLICY.is_protected_path("runs/GMV-TEST/events.jsonl")
    assert POLICY.is_protected_path(".DS_Store")
    assert not POLICY.is_protected_path("tests/fixtures/current_schema.sql")


def test_secret_and_private_path_fixtures_are_rejected() -> None:
    secret = POLICY.scan_text("password=super-secret-value", "fixture")  # gmv-policy-test-fixture
    private_path = POLICY.scan_text("source=/Users/person/private/file", "fixture")  # gmv-policy-test-fixture
    markdown_path = POLICY.scan_text("path: `/Users/person/private/file`", "fixture")  # gmv-policy-test-fixture

    assert [finding.kind for finding in secret] == ["credential_assignment"]
    assert [finding.kind for finding in private_path] == ["personal_absolute_path"]
    assert [finding.kind for finding in markdown_path] == ["personal_absolute_path"]


def test_redacted_and_relative_values_are_allowed() -> None:
    text = "password=[REDACTED]\nsource=tests/fixtures/current_schema.sql"
    assert POLICY.scan_text(text, "fixture") == []


def test_secret_read_from_env_or_file_is_not_a_literal_credential() -> None:
    """The regex can't require a string literal (the value may be unquoted), so a
    call like `token = os.environ.get("X")` or `token = path.read_text(...)` used to
    match too: the value pattern just stops at the "(" of the call. Both are the
    correct, secure way to obtain a secret (never hardcoded) — real false positives
    found in adapter_notion.py:195 and notion_extract.py:202 on 2026-08-29/30."""
    env_lookup = POLICY.scan_text('token = os.environ.get("NOTION_TOKEN")', "fixture")  # gmv-policy-test-fixture
    file_read = POLICY.scan_text("token = token_path.read_text(encoding='utf-8').strip()", "fixture")  # gmv-policy-test-fixture
    assert env_lookup == []
    assert file_read == []


def test_second_literal_secret_on_a_line_is_still_caught_after_a_safe_call() -> None:
    """Regression found by gmv-code-reviewer: using `pattern.search()` (first match
    only) meant a line with a safe call FOLLOWED BY a real literal assignment of the
    same kind (illustrative example only, not a real secret — gmv-policy-test-fixture)
    — cleared the whole line as soon as the first (call-shaped) match was dismissed,
    never looking at the second, real one. Must use finditer and only skip the
    call-shaped match, not bail out of the whole line."""
    findings = POLICY.scan_text('token = os.environ.get("X"); password = "literal-hardcoded-pw"', "fixture")  # gmv-policy-test-fixture
    assert [finding.kind for finding in findings] == ["credential_assignment"]


def test_hardcoded_fallback_argument_inside_a_safe_looking_call_is_still_caught() -> None:
    """Second regression found by gmv-code-reviewer: a call-shaped match was
    whitelisted unconditionally, but `get(key, "hardcoded-fallback")` embeds a real
    literal secret as the call's *own* second argument — that shape must still be
    flagged. A genuine single-argument lookup (one quoted string inside the call)
    must still be allowed through (illustrative examples only — gmv-policy-test-fixture)."""
    fallback_literal = POLICY.scan_text('token = os.environ.get("API_TOKEN", "literal-hardcoded-fallback-9x7z")', "fixture")  # gmv-policy-test-fixture
    plain_lookup = POLICY.scan_text('token = os.environ.get("API_TOKEN")', "fixture")  # gmv-policy-test-fixture
    assert [finding.kind for finding in fallback_literal] == ["credential_assignment"]
    assert plain_lookup == []


def test_tracked_protected_path_is_reported_before_content(tmp_path: Path) -> None:
    findings = POLICY.audit_tracked_files(tmp_path, ["04_LOGS/private.log"])
    assert findings == [POLICY.Finding("protected_runtime_path", "04_LOGS/private.log", None)]


def test_current_tracked_tree_passes_policy() -> None:
    findings = POLICY.audit_tracked_files(ROOT, POLICY.tracked_files(ROOT))
    assert findings == []
