#!/usr/bin/env python3
"""Reject protected runtime paths and high-confidence sensitive tracked content."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PROTECTED_PATHS = (
    PurePosixPath(".DS_Store"),
    PurePosixPath("02_INDEXES"),
    PurePosixPath("03_STATE"),
    PurePosixPath("04_LOGS"),
    PurePosixPath("05_OUTPUT"),
    PurePosixPath("06_CACHE"),
    PurePosixPath("07_IMPORT"),
    PurePosixPath("08_BACKUP_LOCAL"),
    PurePosixPath("09_DATABASE"),
    PurePosixPath("runs"),
)
FIXTURE_MARKER = "gmv-policy-test-fixture"
QUOTED_STRING = re.compile(r"""(['"])(?:(?!\1).)*\1""")
SENSITIVE_PATTERNS = (
    (
        "personal_absolute_path",
        re.compile(r"(?:^|[\s'\"=`])(?:/Users/[^/\s]+|/home/[^/\s]+)(?:/|\b)"),
    ),
    (
        "private_key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|token|secret|authorization)"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{8,}"
        ),
    ),
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    path: str
    line: int | None


def is_protected_path(raw_path: str) -> bool:
    path = PurePosixPath(raw_path)
    return any(path == prefix or prefix in path.parents for prefix in PROTECTED_PATHS)


def _call_is_a_plain_lookup(line: str, open_paren: int) -> bool:
    """True only if the call has at most one quoted-string argument (a plain
    `get("KEY")`/`read_text(encoding="utf-8")`-shaped lookup). A second quoted
    argument is the `get(key, "hardcoded-fallback")` shape — a real, common way to
    hide a literal secret behind an otherwise-safe-looking accessor call, so that
    must still be flagged, not whitelisted just because *a* call is present."""
    depth = 0
    for index in range(open_paren, len(line)):
        char = line[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                arguments = line[open_paren + 1:index]
                return len(QUOTED_STRING.findall(arguments)) <= 1
    return len(QUOTED_STRING.findall(line[open_paren + 1:])) <= 1  # unbalanced/multiline call


def scan_text(text: str, path: str) -> list[Finding]:
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if FIXTURE_MARKER in line:
            continue
        for kind, pattern in SENSITIVE_PATTERNS:
            # finditer, not search: a line can carry more than one `keyword = value`
            # (e.g. a safe `token = os.environ.get(...)` followed by a second, real
            # literal assignment later on the same line) — checking only the first
            # match would let a later literal secret slip through undetected.
            for match in pattern.finditer(line):
                # credential_assignment's value pattern has no way to require a string
                # literal (the value may or may not be quoted), so a line like
                # `token = os.environ.get("X")` or `token = path.read_text(...)`
                # matches too: the unquoted greedy run just stops at the "(" of the
                # call. That is the correct, secure way to obtain a secret (never a
                # hardcoded literal) *unless* the call itself embeds a second literal
                # as a fallback/default argument — so only skip a call-shaped match
                # when it's a plain single-argument lookup, not any call whatsoever.
                end = match.end()
                if (kind == "credential_assignment" and line[end:end + 1] == "("
                        and _call_is_a_plain_lookup(line, end)):
                    continue
                findings.append(Finding(kind, path, line_number))
                break
    return findings


def audit_tracked_files(root: Path, tracked_files: list[str]) -> list[Finding]:
    findings = []
    for relative in tracked_files:
        if is_protected_path(relative):
            findings.append(Finding("protected_runtime_path", relative, None))
            continue
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(text, relative))
    return findings


def tracked_files(root: Path) -> list[str]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("required command not found: git")
    result = subprocess.run(  # noqa: S603 - fixed Git argv, no shell
        [git, "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [entry.decode() for entry in result.stdout.split(b"\0") if entry]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = audit_tracked_files(root, tracked_files(root))
    for finding in findings:
        location = finding.path if finding.line is None else f"{finding.path}:{finding.line}"
        print(f"FAIL|{finding.kind}|{location}")
    if findings:
        print(f"POLICY|FAILED|findings={len(findings)}")
        return 1
    print("POLICY|PASS|findings=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
