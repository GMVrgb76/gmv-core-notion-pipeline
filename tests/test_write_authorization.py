"""SEC-006 first slice: capability-based write authorization (log-only).

Covers, in order: (A) static cross-checks that the source tree matches the
approved capability matrix exactly; (B) runtime behavior of
``gmv_core.authorization`` against synthetic, monkeypatched capabilities on
throwaway connections -- never the live database; (C) one end-to-end
integration proof against a real production writer (Knowledge Engine) run
as an isolated subprocess, matching the existing characterization pattern.

Every runtime test opens its own throwaway ``sqlite3`` connection under
``tmp_path`` or ``:memory:``. None touches ``09_DATABASE/GMV.db``; the
autouse ``isolated_gmv`` fixture (tests/conftest.py) additionally guards
against that by construction.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from gmv_core import authorization
from gmv_core.errors import UnauthorizedWriteError
from gmv_core.migrations import FOREIGN_KEYS_VERSION, migrate

ROOT = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve().relative_to(ROOT).as_posix()
KNOWLEDGE_ENGINE = ROOT / "01_RUNTIME" / "knowledge_engine.py"

PRODUCTION_ROOTS = ("01_RUNTIME/", "10_API/", "gmv_core/")

_STATIC_TABLE_RE = {
    "INSERT": re.compile(r"^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+([A-Za-z_]\w*)", re.IGNORECASE),
    "UPDATE": re.compile(r"^\s*UPDATE\s+([A-Za-z_]\w*)\s+SET", re.IGNORECASE),
    "DELETE": re.compile(r"^\s*DELETE\s+FROM\s+([A-Za-z_]\w*)", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# A. Static cross-checks
# ---------------------------------------------------------------------------


def _tracked_production_files() -> tuple[str, ...]:
    result = subprocess.run(
        ["/usr/bin/git", "ls-files", "*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        line for line in result.stdout.splitlines() if line.startswith(PRODUCTION_ROOTS)
    )


class _ScopeTracker(ast.NodeVisitor):
    """Walks a module tracking (file, qualname) for execute-family calls."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self._scope: list[str] = []
        self.dml_sites: set[tuple[str, str, str, str]] = set()
        self.executescript_sites: set[tuple[str, str]] = set()
        self.set_authorizer_sites: set[tuple[str, str]] = set()

    def _qualname(self) -> str:
        return ".".join(self._scope) if self._scope else "<module>"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        if isinstance(func, ast.Attribute):
            method = func.attr
            if method in ("execute", "executemany"):
                self._record_dml(node)
            elif method == "executescript":
                self.executescript_sites.add((self.relative_path, self._qualname()))
            elif method == "set_authorizer":
                self.set_authorizer_sites.add((self.relative_path, self._qualname()))
        self.generic_visit(node)

    def _record_dml(self, node: ast.Call) -> None:
        if not node.args:
            return
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            return
        sql = first.value
        for verb, pattern in _STATIC_TABLE_RE.items():
            match = pattern.match(sql)
            if match:
                self.dml_sites.add((self.relative_path, self._qualname(), verb, match.group(1)))
                return


def _scan_production_tree() -> _ScopeTracker:
    combined = _ScopeTracker("<combined>")
    for relative in _tracked_production_files():
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        tracker = _ScopeTracker(relative)
        tracker.visit(tree)
        combined.dml_sites |= tracker.dml_sites
        combined.executescript_sites |= tracker.executescript_sites
        combined.set_authorizer_sites |= tracker.set_authorizer_sites
    return combined


#: These two DB-005/DB-006 migration-reconciliation write sites still exist
#: in source (the modules are dormant, not deleted) but are deliberately
#: revoked: they must never appear in DML_CAPABILITIES. Listed explicitly
#: so a *third*, undocumented, unauthorized DML site is still caught.
_REVOKED_DML_SITES = frozenset(
    {
        ("gmv_core/engine_service_runs_migration.py", "apply_migration", "INSERT", "service_runs"),
        ("gmv_core/timeline_events_migration.py", "apply_migration", "INSERT", "events"),
    }
)


def test_dml_capability_matrix_matches_source() -> None:
    """Every INSERT/UPDATE/DELETE call site in production code is exactly
    the approved 10-tuple matrix plus the 2 explicitly revoked DB-005/
    DB-006 sites -- no more, no fewer, and none of the revoked sites is
    present in the live matrix."""
    scan = _scan_production_tree()
    assert scan.dml_sites == set(authorization.DML_CAPABILITIES) | _REVOKED_DML_SITES
    assert not (_REVOKED_DML_SITES & set(authorization.DML_CAPABILITIES))


def test_ddl_callers_match_source() -> None:
    """executescript() is called from exactly the 2 approved migration
    functions in the whole tracked production tree."""
    scan = _scan_production_tree()
    assert scan.executescript_sites == set(authorization.DDL_CALLERS)


def test_set_authorizer_called_only_by_the_authorization_module() -> None:
    """set_authorizer() is invoked from exactly two sites, both inside
    gmv_core/authorization.py: the install() factory call, and the
    AuthorizingConnection.set_authorizer() override's own super() call.
    No other tracked production file may call it."""
    scan = _scan_production_tree()
    assert scan.set_authorizer_sites == {
        ("gmv_core/authorization.py", "install"),
        ("gmv_core/authorization.py", "AuthorizingConnection.set_authorizer"),
    }


# ---------------------------------------------------------------------------
# B. Runtime behavior against synthetic capabilities
# ---------------------------------------------------------------------------


def _open(tmp_path: Path, name: str, *, mode: str = "log", with_log: bool = False):
    if with_log:
        db_dir = tmp_path / "09_DATABASE"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / name
    else:
        db_path = tmp_path / name
    connection = sqlite3.connect(
        str(db_path), cached_statements=0, factory=authorization.AuthorizingConnection
    )
    connection.executescript(
        """
        CREATE TABLE allowed_tbl (id INTEGER PRIMARY KEY, v TEXT);
        CREATE TABLE other_tbl (id INTEGER PRIMARY KEY, v TEXT);
        """
    )
    log_path = tmp_path / "04_LOGS" / "write_authorization.jsonl" if with_log else None
    authorization.install(connection, mode=mode, database=str(db_path) if with_log else None)
    return connection, log_path


def _writer_a(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> None:
    connection.execute(sql, params)


def _writer_b(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> None:
    connection.execute(sql, params)


def _shared_helper(connection: sqlite3.Connection, sql: str) -> None:
    connection.execute(sql)


def _outer_caller_using_helper(connection: sqlite3.Connection, sql: str) -> None:
    _shared_helper(connection, sql)


def test_negative_authorized_function_wrong_table(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a", "INSERT", "allowed_tbl")}),
    )
    connection, _ = _open(tmp_path, "wrong_table.db", mode="enforce")
    _writer_a(connection, "INSERT INTO allowed_tbl (v) VALUES ('x')")  # granted table: OK
    with pytest.raises(UnauthorizedWriteError):
        _writer_a(connection, "INSERT INTO other_tbl (v) VALUES ('x')")  # same function, wrong table


def test_negative_authorized_function_wrong_verb(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a", "INSERT", "allowed_tbl")}),
    )
    connection, _ = _open(tmp_path, "wrong_verb.db", mode="enforce")
    _writer_a(connection, "INSERT INTO allowed_tbl (id, v) VALUES (1, 'x')")
    with pytest.raises(UnauthorizedWriteError):
        _writer_a(connection, "DELETE FROM allowed_tbl WHERE id=1")  # never granted DELETE


def test_indirect_trigger_action_is_governed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A direct INSERT that cascades into a trigger-driven INSERT on a
    table the caller lacks capability for must deny the whole statement,
    atomically -- zero rows in either table."""
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a", "INSERT", "allowed_tbl")}),
    )
    db_path = tmp_path / "trigger.db"
    connection = sqlite3.connect(
        str(db_path), cached_statements=0, factory=authorization.AuthorizingConnection
    )
    connection.executescript(
        """
        CREATE TABLE allowed_tbl (id INTEGER PRIMARY KEY, v TEXT);
        CREATE TABLE other_tbl (id INTEGER PRIMARY KEY, v TEXT);
        CREATE TRIGGER cascade AFTER INSERT ON allowed_tbl
        BEGIN INSERT INTO other_tbl (v) VALUES (NEW.v); END;
        """
    )  # trigger installed before authorization.install(): ungoverned bootstrap, like enable_foreign_keys
    authorization.install(connection, mode="enforce")
    with pytest.raises(UnauthorizedWriteError):
        _writer_a(connection, "INSERT INTO allowed_tbl (v) VALUES ('cascades')")
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (0,)
    assert connection.execute("SELECT COUNT(*) FROM other_tbl").fetchone() == (0,)


def _writer_a_many(connection: sqlite3.Connection, sql: str, seq) -> None:
    connection.executemany(sql, seq)


def _writer_b_many(connection: sqlite3.Connection, sql: str, seq) -> None:
    connection.executemany(sql, seq)


def test_executemany_is_governed_per_call(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a_many", "INSERT", "allowed_tbl")}),
    )
    connection, _ = _open(tmp_path, "many.db", mode="enforce")
    _writer_a_many(connection, "INSERT INTO allowed_tbl (v) VALUES (?)", [("a",), ("b",)])
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (2,)
    with pytest.raises(UnauthorizedWriteError):
        _writer_b_many(connection, "INSERT INTO other_tbl (v) VALUES (?)", [("c",), ("d",)])


def _trusted_ddl_caller(connection: sqlite3.Connection, sql: str) -> None:
    connection.executescript(sql)


def _untrusted_ddl_caller(connection: sqlite3.Connection, sql: str) -> None:
    connection.executescript(sql)


def test_executescript_restricted_to_ddl_callers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        authorization, "DDL_CALLERS", frozenset({(THIS_FILE, "_trusted_ddl_caller")})
    )
    connection, _ = _open(tmp_path, "ddl.db", mode="enforce")
    _trusted_ddl_caller(connection, "CREATE TABLE t2 (id INTEGER);")  # allowed
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "t2" in tables
    with pytest.raises(UnauthorizedWriteError):
        _untrusted_ddl_caller(connection, "CREATE TABLE t3 (id INTEGER);")


def _writer_a_cursor(connection: sqlite3.Connection, sql: str) -> None:
    cursor = connection.cursor()
    cursor.execute(sql)


def _writer_b_cursor(connection: sqlite3.Connection, sql: str) -> None:
    cursor = connection.cursor()
    cursor.execute(sql)


def test_cursor_execute_is_governed_identically_to_connection_execute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a_cursor", "INSERT", "allowed_tbl")}),
    )
    connection, _ = _open(tmp_path, "cursor.db", mode="enforce")
    assert isinstance(connection.cursor(), authorization.AuthorizingCursor)
    _writer_a_cursor(connection, "INSERT INTO allowed_tbl (v) VALUES ('via-cursor')")
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (1,)
    with pytest.raises(UnauthorizedWriteError):
        _writer_b_cursor(connection, "INSERT INTO other_tbl (v) VALUES ('via-cursor')")


def test_pragma_read_always_allowed_pragma_write_always_denied(tmp_path: Path) -> None:
    connection, _ = _open(tmp_path, "pragma.db", mode="enforce")
    connection.execute("PRAGMA user_version")  # read: always fine, no capability needed
    with pytest.raises(UnauthorizedWriteError):
        connection.execute("PRAGMA user_version = 7")  # write: never granted to anyone


@pytest.mark.parametrize(
    "sql",
    [
        "ATTACH DATABASE ':memory:' AS other",
        "VACUUM",
        "ANALYZE allowed_tbl",
    ],
)
def test_attach_vacuum_analyze_always_denied(tmp_path: Path, sql: str) -> None:
    connection, _ = _open(tmp_path, "misc.db", mode="enforce")
    with pytest.raises(UnauthorizedWriteError):
        connection.execute(sql)


def test_detach_always_denied(tmp_path: Path) -> None:
    connection, _ = _open(tmp_path, "detach.db", mode="log")  # attach in log mode to set up detach
    connection.execute("ATTACH DATABASE ':memory:' AS other")
    enforce_connection = connection
    enforce_connection._gmv_mode = "enforce"
    with pytest.raises(UnauthorizedWriteError):
        enforce_connection.execute("DETACH DATABASE other")


def test_unknown_action_code_denied_by_construction() -> None:
    status, verb, obj = authorization._decide(999999, "whatever", None, (THIS_FILE, "_writer_a"))
    assert status == "violation"
    assert verb == "ACTION_999999"


def test_capability_belongs_to_the_function_that_materially_executes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Authorizing the shared helper (the function that materially calls
    execute()) grants the write even though a different, unauthorized
    function invoked that helper -- no inheritance, no stack search."""
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_shared_helper", "INSERT", "allowed_tbl")}),
    )
    connection, _ = _open(tmp_path, "helper.db", mode="enforce")
    _outer_caller_using_helper(connection, "INSERT INTO allowed_tbl (v) VALUES ('via-helper')")
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (1,)


def test_capability_does_not_inherit_to_the_outer_caller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The inverse: authorizing the OUTER function (which never itself
    calls execute()) does not help -- the actual executing frame is the
    shared helper, and it is unauthorized."""
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_outer_caller_using_helper", "INSERT", "allowed_tbl")}),
    )
    connection, _ = _open(tmp_path, "helper2.db", mode="enforce")
    with pytest.raises(UnauthorizedWriteError):
        _outer_caller_using_helper(connection, "INSERT INTO allowed_tbl (v) VALUES ('x')")


def test_set_authorizer_locked_after_install(tmp_path: Path) -> None:
    connection, _ = _open(tmp_path, "locked.db", mode="log")
    with pytest.raises(UnauthorizedWriteError):
        connection.set_authorizer(lambda *args: sqlite3.SQLITE_OK)


def test_non_authorization_database_errors_pass_through_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A genuine UNIQUE constraint violation on an otherwise-authorized
    write must raise sqlite3.IntegrityError unchanged, never
    UnauthorizedWriteError -- last_denial is only set on a real policy
    violation, never on an unrelated SQLite error."""
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a", "INSERT", "allowed_tbl")}),
    )
    connection, _ = _open(tmp_path, "constraint.db", mode="enforce")
    _writer_a(connection, "INSERT INTO allowed_tbl (id, v) VALUES (1, 'first')")
    with pytest.raises(sqlite3.IntegrityError):
        _writer_a(connection, "INSERT INTO allowed_tbl (id, v) VALUES (1, 'dup')")


def test_temporary_state_cleared_in_finally_after_denial(tmp_path: Path) -> None:
    connection, _ = _open(tmp_path, "cleanup.db", mode="enforce")
    with pytest.raises(UnauthorizedWriteError):
        _writer_b(connection, "INSERT INTO allowed_tbl (v) VALUES ('x')")
    assert connection._gmv_caller_stack == []
    assert connection._gmv_last_denial is None


_LOG_ALLOWED_KEYS = {
    "timestamp",
    "caller_file",
    "caller_function",
    "verb",
    "table",
    "mode",
    "outcome",
    "correlation_id",
}


def test_log_contains_only_structural_fields_no_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Authorized writes are never logged at all (see
    test_no_log_file_created_without_any_violation); only the would_deny
    violation reaches the log, and even then carries no SQL or values."""
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a", "INSERT", "allowed_tbl")}),
    )
    connection, log_path = _open(tmp_path, "GMV.db", mode="log", with_log=True)
    secret_value = "gmv-test-fixture-do-not-log-me-0e5f3c2a"  # noqa: S105 (test fixture, not a real secret)
    _writer_a(connection, "INSERT INTO allowed_tbl (v) VALUES (?)", (secret_value,))  # authorized: not logged
    _writer_b(connection, "INSERT INTO other_tbl (v) VALUES (?)", (secret_value,))  # would_deny: logged

    assert log_path is not None and log_path.exists()
    raw_text = log_path.read_text(encoding="utf-8")
    assert secret_value not in raw_text
    assert "INSERT INTO" not in raw_text  # no raw SQL text logged either

    lines = [json.loads(line) for line in raw_text.splitlines() if line]
    assert len(lines) == 1
    assert set(lines[0]) == _LOG_ALLOWED_KEYS
    assert lines[0]["outcome"] == "would_deny"


def test_no_log_file_created_without_any_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a", "INSERT", "allowed_tbl")}),
    )
    connection, log_path = _open(tmp_path, "GMV.db", mode="log", with_log=True)
    _writer_a(connection, "INSERT INTO allowed_tbl (v) VALUES ('only-authorized-activity')")
    assert log_path is not None
    assert not log_path.exists()
    assert not log_path.parent.exists()


def test_single_log_only_violation_creates_exactly_one_would_deny_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(authorization, "DML_CAPABILITIES", frozenset())
    connection, log_path = _open(tmp_path, "GMV.db", mode="log", with_log=True)
    _writer_b(connection, "INSERT INTO allowed_tbl (v) VALUES ('x')")
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (1,)  # log-only: not blocked

    assert log_path is not None and log_path.exists()
    lines = [json.loads(line) for line in log_path.read_text().splitlines() if line]
    assert len(lines) == 1
    assert lines[0]["outcome"] == "would_deny"
    assert lines[0]["mode"] == "log"
    assert lines[0]["verb"] == "INSERT"
    assert lines[0]["table"] == "allowed_tbl"


def test_single_enforce_violation_creates_exactly_one_denied_line_and_no_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(authorization, "DML_CAPABILITIES", frozenset())
    connection, log_path = _open(tmp_path, "GMV.db", mode="enforce", with_log=True)
    with pytest.raises(UnauthorizedWriteError):
        _writer_b(connection, "INSERT INTO allowed_tbl (v) VALUES ('x')")
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (0,)  # enforce: blocked

    assert log_path is not None and log_path.exists()
    lines = [json.loads(line) for line in log_path.read_text().splitlines() if line]
    assert len(lines) == 1
    assert lines[0]["outcome"] == "denied"
    assert lines[0]["mode"] == "enforce"


def test_statement_cache_disabled_prevents_authorization_bypass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The regression this whole slice exists to prevent: with
    cached_statements=0 (as the factory always uses), an identical SQL
    string executed first by an authorized caller and then by an
    unauthorized caller is re-evaluated every time -- no silent reuse."""
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a", "INSERT", "allowed_tbl")}),
    )
    connection, _ = _open(tmp_path, "cache.db", mode="enforce")
    sql = "INSERT INTO allowed_tbl (v) VALUES ('identical-text')"
    _writer_a(connection, sql)  # primes any would-be statement cache
    with pytest.raises(UnauthorizedWriteError):
        _writer_b(connection, sql)  # identical SQL text, different (unauthorized) caller
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (1,)


def test_statement_cache_enabled_would_have_allowed_the_bypass(tmp_path: Path) -> None:
    """Documents, as a permanent regression guard, that the vulnerability
    is real when the statement cache is left at its sqlite3 default --
    this test does not exercise gmv_core, only bare sqlite3 with a single
    stable authorizer callback (never swapped -- swapping the callback
    itself is not how the real design works and is not what is being
    measured here), to prove the danger this design deliberately avoids.
    """
    db_path = tmp_path / "bare_cache.db"
    connection = sqlite3.connect(str(db_path))  # default cached_statements, NOT our factory
    connection.executescript("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT);")
    state = {"deny": False, "calls": 0}

    def authorizer(action_code, arg1, arg2, dbname, source):
        if action_code == sqlite3.SQLITE_INSERT:
            state["calls"] += 1
            if state["deny"]:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(authorizer)  # installed once, never swapped
    sql = "INSERT INTO t (v) VALUES ('identical-text')"
    connection.execute(sql)  # state["deny"] is False: primes the default statement cache
    state["deny"] = True
    connection.execute(sql)  # identical text: SQLite reuses the cached prepared statement
    assert state["calls"] == 1, "authorizer was NOT bypassed -- environment behavior changed"
    assert connection.execute("SELECT COUNT(*) FROM t").fetchone() == (2,)


def test_log_only_to_enforce_mode_switch_reauthorizes_with_cached_statements_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        authorization,
        "DML_CAPABILITIES",
        frozenset({(THIS_FILE, "_writer_a", "INSERT", "allowed_tbl")}),
    )
    connection, log_path = _open(tmp_path, "GMV.db", mode="log", with_log=True)
    sql = "INSERT INTO allowed_tbl (v) VALUES ('same-text')"
    _writer_b(connection, sql)  # log-only: recorded as would_deny, still executes
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (1,)

    connection._gmv_mode = "enforce"  # never done in production; here only to prove the property
    with pytest.raises(UnauthorizedWriteError):
        _writer_b(connection, sql)  # identical SQL text: must be re-evaluated, not reused
    assert connection.execute("SELECT COUNT(*) FROM allowed_tbl").fetchone() == (1,)

    outcomes = [json.loads(line)["outcome"] for line in log_path.read_text().splitlines() if line]
    assert "would_deny" in outcomes
    assert "denied" in outcomes


# ---------------------------------------------------------------------------
# C. End-to-end integration: a real production writer, isolated subprocess
# ---------------------------------------------------------------------------


def test_knowledge_engine_approved_writes_are_never_logged_only_its_preexisting_ddl_gap_is(
    isolated_gmv,
) -> None:
    """End-to-end proof against a real production writer, run as an
    isolated subprocess (never the live database). knowledge_engine.py's
    two approved writes (INSERT events, INSERT service_runs) are
    authorized and therefore produce no log entry at all. Its `<module>`
    scope is not a DDL caller, so its own pre-existing
    `CREATE TABLE IF NOT EXISTS objects/service_runs/timeline` bootstrap
    (3 statements, each producing a CREATE_TABLE action plus an internal
    INSERT INTO sqlite_master bookkeeping action) is a real, observed,
    non-blocking would_deny violation in log-only mode -- exactly the
    kind of pre-existing gap this observation period exists to surface.
    """
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    migrate(isolated_gmv.database, target_version=FOREIGN_KEYS_VERSION)
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute(
            "INSERT INTO objects(oid,type,name,status) "
            "VALUES ('SRV-000001','Service','Knowledge Engine','active')"
        )
        connection.execute(
            "INSERT INTO objects(oid,type,name,status) "
            "VALUES ('PER-000001','Person','Giacomo Marco Valerio','active')"
        )
    log_path = isolated_gmv.home / "04_LOGS" / "write_authorization.jsonl"
    assert not log_path.exists()  # migrate() itself is DDL-authorized: nothing logged yet

    result = subprocess.run(
        [sys.executable, str(KNOWLEDGE_ENGINE)],
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    assert log_path.exists()
    records = [json.loads(line) for line in log_path.read_text().splitlines() if line]
    knowledge_records = [
        record for record in records if record["caller_file"] == "01_RUNTIME/knowledge_engine.py"
    ]
    assert all(record["outcome"] == "would_deny" for record in knowledge_records)
    assert all(record["mode"] == "log" for record in knowledge_records)
    assert len(knowledge_records) == 6
    assert {record["verb"] for record in knowledge_records} == {"CREATE_TABLE", "INSERT"}
    assert {record["table"] for record in knowledge_records} == {
        "objects",
        "service_runs",
        "timeline",
        "sqlite_master",
    }
    # The two approved capability writes (events, service_runs INSERTs)
    # are authorized and therefore produce no record at all.
    assert not any(record["table"] == "events" for record in knowledge_records)
