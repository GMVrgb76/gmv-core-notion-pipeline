"""Static DB-002 boundary for every tracked production SQLite connection."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = ("01_RUNTIME/", "10_API/", "gmv_core/")
RAW_CONNECT_OWNER = "gmv_core/database.py"
FOREIGN_KEYS_OFF_OWNERS = (
    "gmv_core/migration_sql/006_foreign_keys.sql",
    "gmv_core/migration_sql/007_domain_constraints.sql",
)
DISABLED_FOREIGN_KEYS = re.compile(
    r"PRAGMA\s+foreign_keys\s*=\s*(?:OFF|0)",
    flags=re.IGNORECASE,
)


def _tracked_files(*patterns: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["/usr/bin/git", "ls-files", *patterns],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def _raw_connect_lines(path: Path) -> tuple[int, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_aliases = set()
    function_aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                if name.name == "sqlite3":
                    module_aliases.add(name.asname or name.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "sqlite3":
            for name in node.names:
                if name.name == "connect":
                    function_aliases.add(name.asname or name.name)

    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        direct = isinstance(function, ast.Name) and function.id in function_aliases
        qualified = (
            isinstance(function, ast.Attribute)
            and function.attr == "connect"
            and isinstance(function.value, ast.Name)
            and function.value.id in module_aliases
        )
        if direct or qualified:
            lines.append(node.lineno)
    return tuple(sorted(lines))


def test_only_core_factory_calls_sqlite_connect() -> None:
    calls = {
        relative: _raw_connect_lines(ROOT / relative)
        for relative in _tracked_files("*.py")
        if relative.startswith(PRODUCTION_ROOTS)
    }
    calls = {relative: lines for relative, lines in calls.items() if lines}

    assert set(calls) == {RAW_CONNECT_OWNER}
    assert len(calls[RAW_CONNECT_OWNER]) == 1


def test_foreign_key_disable_is_confined_to_atomic_table_rebuild() -> None:
    hits = {}
    for relative in _tracked_files("*.py", "*.sql"):
        if not relative.startswith(PRODUCTION_ROOTS):
            continue
        matches = DISABLED_FOREIGN_KEYS.findall(
            (ROOT / relative).read_text(encoding="utf-8")
        )
        if matches:
            hits[relative] = len(matches)

    assert hits == {owner: 1 for owner in FOREIGN_KEYS_OFF_OWNERS}

    for owner in FOREIGN_KEYS_OFF_OWNERS:
        migration = (ROOT / owner).read_text(encoding="utf-8")
        disable = migration.index("PRAGMA foreign_keys = OFF;")
        begin = migration.index("BEGIN IMMEDIATE;")
        commit = migration.rindex("COMMIT;")
        enable = migration.rindex("PRAGMA foreign_keys = ON;")
        assert disable < begin < commit < enable
