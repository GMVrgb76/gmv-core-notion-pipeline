"""Quality floor: new suppressions, skips, silent excepts and test-count drops."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_floor as FLOOR  # noqa: E402  gmv-floor-ok: sys.path must be set first, same as test_runtime_git_policy.py

NOQA = "# " + "noqa: F401"
TYPE_IGNORE = "# type: " + "ignore"
SKIP = "@pytest.mark." + "skip"
OK_MARKER = "# gmv-floor-ok: " + "reviewed, see task"


def _source(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def _kinds(findings: list) -> list[str]:
    return [finding.kind for finding in findings]


def test_parse_diff_collects_added_lines_and_test_counts() -> None:
    diff = _source(
        "--- a/tests/test_a.py",
        "+++ b/tests/test_a.py",
        "@@ -3,0 +4,2 @@",
        "+def test_new(): pass",
        "+x = 1",
        "@@ -9 +10,0 @@",
        "-def test_gone(): pass",
        "--- a/README.md",
        "+++ b/README.md",
        "@@ -1 +1 @@",
        "+ignored",
    )
    parsed = FLOOR.parse_diff(diff)
    assert list(parsed) == ["tests/test_a.py"]
    assert parsed["tests/test_a.py"].added == {4, 5}
    assert (parsed["tests/test_a.py"].added_tests, parsed["tests/test_a.py"].removed_tests) == (1, 1)


def test_deleted_file_counts_removed_tests_against_old_path() -> None:
    diff = _source(
        "--- a/tests/test_b.py",
        "+++ /dev/null",
        "@@ -1,2 +0,0 @@",
        "-def test_one(): pass",
        "-def test_two(): pass",
    )
    parsed = FLOOR.parse_diff(diff)
    assert parsed["tests/test_b.py"].removed_tests == 2
    assert FLOOR.net_removed_tests(parsed) == 2


def test_net_removed_tests_ignores_renamed_or_replaced_tests() -> None:
    diff = _source(
        "--- a/tests/test_c.py",
        "+++ b/tests/test_c.py",
        "@@ -1 +1 @@",
        "-def test_old_name(): pass",
        "+def test_new_name(): pass",
    )
    assert FLOOR.net_removed_tests(FLOOR.parse_diff(diff)) == 0


def test_scan_added_flags_suppressions_and_skips_on_added_lines_only() -> None:
    source = _source(
        f"import os  {NOQA}",
        f"value = 1  {TYPE_IGNORE}",
        SKIP,
        "untouched = 1",
    )
    assert _kinds(FLOOR.scan_added("m.py", source, {1, 2, 3})) == [
        "new_suppression", "new_suppression", "new_test_skip",
    ]
    assert FLOOR.scan_added("m.py", source, {4}) == []
    assert FLOOR.scan_added("m.py", source, set()) == []


def test_scan_added_honors_marker_with_a_reason_only() -> None:
    with_reason = _source(f"import os  {NOQA}  {OK_MARKER}")
    empty_reason = _source(f"import os  {NOQA}  # gmv-floor-ok:")
    assert FLOOR.scan_added("m.py", with_reason, {1}) == []
    assert _kinds(FLOOR.scan_added("m.py", empty_reason, {1})) == ["new_suppression"]


def test_scan_added_flags_silent_excepts_but_not_handled_ones() -> None:
    source = _source(
        "try:",
        "    run()",
        "except ValueError:",
        "    pass",
        "try:",
        "    run()",
        "except KeyError:",
        "    ...",
        "try:",
        "    run()",
        "except OSError:",
        "    log()",
    )
    findings = FLOOR.scan_added("m.py", source, set(range(1, 13)))
    assert [(item.kind, item.line) for item in findings] == [
        ("new_silent_except", 3), ("new_silent_except", 7),
    ]


def test_silent_except_is_flagged_when_only_its_body_line_is_new() -> None:
    source = _source("try:", "    run()", "except ValueError:", "    pass")
    assert _kinds(FLOOR.scan_added("m.py", source, {4})) == ["new_silent_except"]
    assert FLOOR.scan_added("m.py", source, {1, 2}) == []


def test_silent_except_marker_on_any_handler_line_allows_it() -> None:
    source = _source("try:", "    run()", "except ValueError:", f"    pass  {OK_MARKER}")
    assert FLOOR.scan_added("m.py", source, {3, 4}) == []


def test_unparseable_source_still_reports_line_based_findings() -> None:
    source = _source("def broken(:", f"x = 1  {NOQA}")
    assert _kinds(FLOOR.scan_added("m.py", source, {1, 2})) == ["new_suppression"]


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    assert git is not None
    return subprocess.run([git, *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "floor-test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "floor-test@example.invalid")
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    (work / "app.py").write_text(_source(f"import os  {NOQA}", "VALUE = 1"))
    (work / "test_app.py").write_text(
        _source("def test_one():", "    assert True", "def test_two():", "    assert True")
    )
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    return work


def test_audit_passes_when_nothing_changed_or_only_old_debt_remains(repo: Path) -> None:
    assert FLOOR.audit(repo, "HEAD", allow_test_removal=False) == []
    (repo / "app.py").write_text(_source(f"import os  {NOQA}", "VALUE = 2"))
    assert FLOOR.audit(repo, "HEAD", allow_test_removal=False) == []


def test_audit_reports_new_suppression_new_silent_except_and_dropped_test(repo: Path) -> None:
    (repo / "app.py").write_text(
        _source(f"import os  {NOQA}", f"import sys  {NOQA}", "try:", "    pass", "except OSError:", "    pass")
    )
    (repo / "test_app.py").write_text(_source("def test_one():", "    assert True"))
    findings = FLOOR.audit(repo, "HEAD", allow_test_removal=False)
    assert sorted(_kinds(findings)) == ["new_silent_except", "new_suppression", "test_count_dropped"]
    assert _kinds(FLOOR.audit(repo, "HEAD", allow_test_removal=True)).count("test_count_dropped") == 0


def test_audit_scans_untracked_python_files(repo: Path) -> None:
    (repo / "fresh.py").write_text(_source("try:", "    pass", "except OSError:", "    pass"))
    findings = FLOOR.audit(repo, "HEAD", allow_test_removal=False)
    assert [(item.kind, item.path) for item in findings] == [("new_silent_except", "fresh.py")]


def test_resolve_base_uses_request_and_returns_none_without_origin_main(repo: Path) -> None:
    assert FLOOR.resolve_base(repo, "abc123") == "abc123"
    assert FLOOR.resolve_base(repo, None) is None


def test_audit_skips_non_utf8_files_and_still_reports_other_findings(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "app.py").write_bytes(b"VALUE = 2\n\xff\xfe\n")
    (repo / "legacy.py").write_bytes(b"x = 1\n\xff\n")
    (repo / "fresh.py").write_text(_source("try:", "    pass", "except OSError:", "    pass"))
    findings = FLOOR.audit(repo, "HEAD", allow_test_removal=False)
    assert [(item.kind, item.path) for item in findings] == [("new_silent_except", "fresh.py")]
    assert capsys.readouterr().err.count("FLOOR|WARN|unreadable file skipped") == 2
