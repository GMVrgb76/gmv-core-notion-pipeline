"""Static DB-002 boundary for every tracked production SQLite connection."""

from __future__ import annotations

import ast
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = ("01_RUNTIME/", "10_API/", "gmv_core/")
RAW_CONNECT_OWNER = "gmv_core/database.py"
FOREIGN_KEYS_OFF_OWNERS = (
    "gmv_core/migration_sql/006_foreign_keys.sql",
    "gmv_core/migration_sql/007_domain_constraints.sql",
    "gmv_core/migration_sql/008_oid_type_consistency.sql",
)
DISABLED_FOREIGN_KEYS = re.compile(
    r"PRAGMA\s+foreign_keys\s*=\s*(?:OFF|0)",
    flags=re.IGNORECASE,
)
SHELL_SHEBANG = re.compile(rb"^#![^\n]*(?:/|\s)(?:ba|da|k|z)?sh(?:\s|$)")


def _tracked_files(*patterns: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["/usr/bin/git", "ls-files", *patterns],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def _tracked_shell_files() -> tuple[str, ...]:
    shell_files = []
    for relative in _tracked_files():
        path = ROOT / relative
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            first_line = stream.readline(512)
        if SHELL_SHEBANG.search(first_line):
            shell_files.append(relative)
    return tuple(shell_files)


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


def _direct_sqlite_client_lines(source: str) -> tuple[int, ...]:
    """Find shell commands whose executable is the external SQLite client."""
    hits = []
    command_prefixes = {"command", "exec"}
    control_words = {"if", "then", "elif", "else", "while", "until", "do"}
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            lexer = shlex.shlex(stripped, posix=True, punctuation_chars=";&|()")
            lexer.commenters = "#"
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            continue

        expect_command = True
        for word in tokens:
            if word in control_words or set(word) <= set(";&|()"):
                expect_command = True
                continue
            if not expect_command:
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", word):
                continue
            if word in command_prefixes:
                continue
            if word == "env":
                continue
            if Path(word).name == "sqlite3":
                hits.append(line_number)
            expect_command = False
    return tuple(hits)


def test_only_core_factory_calls_sqlite_connect() -> None:
    calls = {
        relative: _raw_connect_lines(ROOT / relative)
        for relative in _tracked_files("*.py")
        if relative.startswith(PRODUCTION_ROOTS)
    }
    calls = {relative: lines for relative, lines in calls.items() if lines}

    assert set(calls) == {RAW_CONNECT_OWNER}
    assert len(calls[RAW_CONNECT_OWNER]) == 1


def test_tracked_production_shell_never_invokes_sqlite_client() -> None:
    hits = {
        relative: _direct_sqlite_client_lines((ROOT / relative).read_text(encoding="utf-8"))
        for relative in _tracked_shell_files()
    }
    assert {relative: lines for relative, lines in hits.items() if lines} == {}


def test_shell_sqlite_boundary_rejects_direct_client_forms() -> None:
    sources = (
        'sqlite3 "$DB" "SELECT type FROM objects"',
        "/usr/bin/sqlite3 ~/.gmv_core/09_DATABASE/GMV.db",
        'if command /usr/bin/sqlite3 "$HOME/.gmv_core/09_DATABASE/GMV.db"; then :; fi',
    )
    assert [_direct_sqlite_client_lines(source) for source in sources] == [
        (1,),
        (1,),
        (1,),
    ]


def test_shell_sqlite_boundary_ignores_non_executable_references() -> None:
    source = """
    # sqlite3 "$DB" "SELECT 1"
    echo 'documentation: sqlite3 ~/.gmv_core/09_DATABASE/GMV.db'
    printf '%s\\n' 'sqlite3 is not required'
    """
    assert _direct_sqlite_client_lines(source) == ()


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
