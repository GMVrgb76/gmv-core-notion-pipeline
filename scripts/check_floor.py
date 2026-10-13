#!/usr/bin/env python3
"""Diff-scoped quality floor: reject new suppressions, new test skips, new
silent `except: pass` handlers and a net drop in the number of tests."""

from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOW_MARKER = re.compile(r"gmv-floor-ok:\s*\S")
SUPPRESSIONS = re.compile(r"#\s*noqa\b|#\s*type:\s*ignore\b")
TEST_SKIPS = re.compile(
    r"pytest\.mark\.(?:skip|skipif|xfail)\b|pytest\.(?:skip|xfail)\(|unittest\.skip"
    r"|\bself\.skipTest\(|@skip(?:If|Unless)?\b"  # gmv-floor-ok: regex source text, not a real skip
)
TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+test_\w+")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    path: str
    line: int | None


@dataclass(slots=True)
class FileDiff:
    added: set[int]
    removed_tests: int = 0
    added_tests: int = 0


def parse_diff(diff_text: str) -> dict[str, FileDiff]:
    """Map each changed .py path to its added line numbers and test-def counts."""
    files: dict[str, FileDiff] = {}
    old_path: str | None = None
    current: FileDiff | None = None
    new_line = 0
    for raw in diff_text.splitlines():
        if raw.startswith("--- "):
            old_path = raw[4:].removeprefix("a/")
            current = None
        elif raw.startswith("+++ "):
            target = raw[4:]
            path = old_path if target == "/dev/null" else target.removeprefix("b/")
            current = None
            if path and path.endswith(".py"):
                current = files.setdefault(path, FileDiff(added=set()))
        elif current is None:
            continue
        elif (hunk := HUNK.match(raw)):
            new_line = int(hunk.group(1))
        elif raw.startswith("+"):
            current.added.add(new_line)
            current.added_tests += bool(TEST_DEF.match(raw[1:]))
            new_line += 1
        elif raw.startswith("-"):
            current.removed_tests += bool(TEST_DEF.match(raw[1:]))
    return files


def _is_silent_handler(handler: ast.ExceptHandler) -> bool:
    return all(
        isinstance(stmt, ast.Pass)
        or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis)
        for stmt in handler.body
    )


def scan_added(path: str, source: str, added: set[int]) -> list[Finding]:
    lines = source.splitlines()
    findings: list[Finding] = []
    for number in sorted(added):
        if not 1 <= number <= len(lines):
            continue
        line = lines[number - 1]
        if ALLOW_MARKER.search(line):
            continue
        if SUPPRESSIONS.search(line):
            findings.append(Finding("new_suppression", path, number))
        if TEST_SKIPS.search(line):
            findings.append(Finding("new_test_skip", path, number))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not _is_silent_handler(node):
            continue
        span = range(node.lineno, (node.end_lineno or node.lineno) + 1)
        if not added.intersection(span):
            continue
        if any(ALLOW_MARKER.search(lines[n - 1]) for n in span):
            continue
        findings.append(Finding("new_silent_except", path, node.lineno))
    return findings


def net_removed_tests(diffs: dict[str, FileDiff]) -> int:
    removed = sum(item.removed_tests for item in diffs.values())
    added = sum(item.added_tests for item in diffs.values())
    return max(0, removed - added)


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        print(f"FLOOR|WARN|unreadable file skipped: {path.name}", file=sys.stderr)
        return None


def _git(root: Path, *args: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("required command not found: git")
    result = subprocess.run(  # noqa: S603 - fixed Git argv, no shell; gmv-floor-ok: same pattern as check_runtime_git_policy.py
        [git, *args], cwd=root, check=True, capture_output=True
    )
    return result.stdout.decode("utf-8", errors="replace")


def resolve_base(root: Path, requested: str | None) -> str | None:
    if requested:
        return requested
    try:
        return _git(root, "merge-base", "HEAD", "origin/main").strip()
    except subprocess.CalledProcessError:
        return None


def audit(root: Path, base: str, allow_test_removal: bool) -> list[Finding]:
    diff = _git(root, "diff", "-U0", "-M", "--no-color", "--no-ext-diff",
                "--src-prefix=a/", "--dst-prefix=b/", base, "--", "*.py")
    diffs = parse_diff(diff)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", "*.py")
    for relative in (entry for entry in untracked.split("\0") if entry):
        text = read_text_or_none(root / relative)
        if text is not None:
            diffs[relative] = FileDiff(added=set(range(1, len(text.splitlines()) + 1)))
    findings: list[Finding] = []
    for relative, item in sorted(diffs.items()):
        path = root / relative
        if not path.is_file() or not item.added:
            continue
        text = read_text_or_none(path)
        if text is not None:
            findings.extend(scan_added(relative, text, item.added))
    if not allow_test_removal and net_removed_tests(diffs):
        findings.append(Finding("test_count_dropped", f"net -{net_removed_tests(diffs)} tests", None))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Git ref to diff against (default: merge-base with origin/main)")
    parser.add_argument("--allow-test-removal", action="store_true",
                        help="Do not fail on a net drop in the number of tests")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = resolve_base(root, args.base)
    if base is None:
        print("FLOOR|SKIP|no base ref (origin/main not available); fetch full history to enforce")
        return 0
    findings = audit(root, base, args.allow_test_removal)
    for finding in findings:
        location = finding.path if finding.line is None else f"{finding.path}:{finding.line}"
        print(f"FAIL|{finding.kind}|{location}")
    if findings:
        print(f"FLOOR|FAILED|findings={len(findings)}")
        return 1
    print("FLOOR|PASS|findings=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
