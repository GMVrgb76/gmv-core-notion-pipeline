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
)
FIXTURE_MARKER = "gmv-policy-test-fixture"
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


def scan_text(text: str, path: str) -> list[Finding]:
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if FIXTURE_MARKER in line:
            continue
        for kind, pattern in SENSITIVE_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(kind, path, line_number))
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
