"""SEC-006 first slice: capability-based write authorization (log-only).

Layers two independent mechanisms:

- WHAT is happening: ``sqlite3.Connection.set_authorizer`` receives the exact
  SQLite action code and operand (table, pragma name, trigger/view source)
  for every action taken while a statement is prepared -- including DDL,
  PRAGMA, and actions performed indirectly through triggers. This replaces
  any text-based classification of the SQL string.
- WHO is doing it: the Python function that materially calls
  ``execute``/``executemany``/``executescript`` on a connection or cursor
  issued by this module. Identity is the direct caller of that exact call,
  a single fixed stack hop -- never a search for an allowed ancestor frame.

A capability is the tuple ``(caller_file, caller_function, verb, table)``.
DDL is authorized per-caller (not per-table) to exactly the two migration
functions listed in ``DDL_CALLERS``; every other action code not explicitly
recognized as always-safe is denied by default.

This slice only ever installs mode ``"log"``: violations are recorded as
``would_deny`` and still execute. Nothing is blocked. ``"enforce"`` mode
exists and is exercised by tests, but no production caller in this
codebase can select it -- ``gmv_core.database.connect_path`` passes the
literal string ``"log"``, never a parameter.

Statement caching is incompatible with per-call authorization: SQLite's
authorizer only fires when a statement is newly prepared, and Python's
``sqlite3`` module reuses a cached prepared statement -- skipping the
authorizer entirely -- for a repeated identical SQL string, regardless of
which caller issues it or which mode is active. Every connection this
module protects must therefore be opened with ``cached_statements=0``;
this is enforced by the factory, not optional per caller.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

from gmv_core.errors import UnauthorizedWriteError

_REPO_ROOT = Path(__file__).resolve().parents[1]

# --- Approved capability matrix (Project Owner-approved, 2026-07-21) ------

_IDENTITY_FILE = "gmv_core/repositories/identity.py"
_KNOWLEDGE_FILE = "01_RUNTIME/knowledge_engine.py"
_COMPAT_FILE = "10_API/gmv_compatibility.py"
_IMPORT_FILE = "10_API/import_service.py"
_MIGRATIONS_FILE = "gmv_core/migrations.py"

#: (caller_file, caller_function, verb, table) -- exactly the 10 approved
#: DML call sites inventoried during the SEC-006 first-slice review.
#: DB-005/DB-006's migration-reconciliation writers (engine_service_runs_
#: migration.py, timeline_events_migration.py) are deliberately absent:
#: those migrations are closed and their write capability is revoked.
#: plugin_manager.py and base_service.py are deliberately absent: neither
#: has a write call site today, and none is granted here.
DML_CAPABILITIES: frozenset[tuple[str, str, str, str]] = frozenset(
    {
        (_IDENTITY_FILE, "allocate_and_create_object", "UPDATE", "oid_sequences"),
        (_IDENTITY_FILE, "allocate_and_create_object", "INSERT", "objects"),
        (_KNOWLEDGE_FILE, "<module>", "INSERT", "events"),
        (_KNOWLEDGE_FILE, "<module>", "INSERT", "service_runs"),
        (_COMPAT_FILE, "run_engine", "INSERT", "service_runs"),
        (_COMPAT_FILE, "run_engine", "INSERT", "events"),
        (_IMPORT_FILE, "update_import_queue", "UPDATE", "import_queue"),
        (_IMPORT_FILE, "update_import_queue", "INSERT", "import_queue"),
        (_IMPORT_FILE, "import_file", "INSERT", "events"),
        (_IMPORT_FILE, "import_file", "INSERT", "resources"),
    }
)

#: (caller_file, caller_function) -- exactly the 2 approved DDL callers.
#: Granted at the caller level, not per-table: DDL (and the sqlite_master
#: bookkeeping SQLite performs internally as its side effect) is trusted
#: wholesale for these two functions, which already have their own
#: independent transactional/rollback governance (ADR_DB002_RESTRICTIVE_
#: FOREIGN_KEYS.md). No other function is granted DDL of any kind.
DDL_CALLERS: frozenset[tuple[str, str]] = frozenset(
    {
        (_MIGRATIONS_FILE, "_baseline_signature"),
        (_MIGRATIONS_FILE, "_apply_migration"),
    }
)

#: The only PRAGMA names the 2 DDL callers may ever write (lower-cased).
#: No other mutating PRAGMA -- including journal_mode -- is ever granted,
#: to either caller, regardless of DDL trust.
_AUTHORIZED_PRAGMA_WRITES: frozenset[str] = frozenset({"user_version", "foreign_keys"})

# --- SQLite authorizer action codes (fixed list -- these integers alias
# unrelated result/limit codes elsewhere in the sqlite3 module namespace,
# so only this explicit list may be used to build a code-to-name map) ----

_DML_VERBS: dict[int, str] = {
    sqlite3.SQLITE_INSERT: "INSERT",
    sqlite3.SQLITE_UPDATE: "UPDATE",
    sqlite3.SQLITE_DELETE: "DELETE",
}

_DDL_ACTION_NAMES: dict[int, str] = {
    sqlite3.SQLITE_CREATE_INDEX: "CREATE_INDEX",
    sqlite3.SQLITE_CREATE_TABLE: "CREATE_TABLE",
    sqlite3.SQLITE_CREATE_TEMP_INDEX: "CREATE_TEMP_INDEX",
    sqlite3.SQLITE_CREATE_TEMP_TABLE: "CREATE_TEMP_TABLE",
    sqlite3.SQLITE_CREATE_TEMP_TRIGGER: "CREATE_TEMP_TRIGGER",
    sqlite3.SQLITE_CREATE_TEMP_VIEW: "CREATE_TEMP_VIEW",
    sqlite3.SQLITE_CREATE_TRIGGER: "CREATE_TRIGGER",
    sqlite3.SQLITE_CREATE_VIEW: "CREATE_VIEW",
    sqlite3.SQLITE_DROP_INDEX: "DROP_INDEX",
    sqlite3.SQLITE_DROP_TABLE: "DROP_TABLE",
    sqlite3.SQLITE_DROP_TEMP_INDEX: "DROP_TEMP_INDEX",
    sqlite3.SQLITE_DROP_TEMP_TABLE: "DROP_TEMP_TABLE",
    sqlite3.SQLITE_DROP_TEMP_TRIGGER: "DROP_TEMP_TRIGGER",
    sqlite3.SQLITE_DROP_TEMP_VIEW: "DROP_TEMP_VIEW",
    sqlite3.SQLITE_DROP_TRIGGER: "DROP_TRIGGER",
    sqlite3.SQLITE_DROP_VIEW: "DROP_VIEW",
    sqlite3.SQLITE_ALTER_TABLE: "ALTER_TABLE",
    sqlite3.SQLITE_REINDEX: "REINDEX",
}

# arg index (1 or 2) holding the most meaningful "object" name for a DDL
# action, for logging only -- DDL authorization is caller-scoped, not
# table-scoped, so this never affects the allow/deny decision.
_DDL_OBJECT_ARG: dict[int, int] = {
    sqlite3.SQLITE_CREATE_INDEX: 2,
    sqlite3.SQLITE_CREATE_TABLE: 1,
    sqlite3.SQLITE_CREATE_TEMP_INDEX: 2,
    sqlite3.SQLITE_CREATE_TEMP_TABLE: 1,
    sqlite3.SQLITE_CREATE_TEMP_TRIGGER: 2,
    sqlite3.SQLITE_CREATE_TEMP_VIEW: 1,
    sqlite3.SQLITE_CREATE_TRIGGER: 2,
    sqlite3.SQLITE_CREATE_VIEW: 1,
    sqlite3.SQLITE_DROP_INDEX: 2,
    sqlite3.SQLITE_DROP_TABLE: 1,
    sqlite3.SQLITE_DROP_TEMP_INDEX: 2,
    sqlite3.SQLITE_DROP_TEMP_TABLE: 1,
    sqlite3.SQLITE_DROP_TEMP_TRIGGER: 2,
    sqlite3.SQLITE_DROP_TEMP_VIEW: 1,
    sqlite3.SQLITE_DROP_TRIGGER: 2,
    sqlite3.SQLITE_DROP_VIEW: 1,
    sqlite3.SQLITE_ALTER_TABLE: 2,
    sqlite3.SQLITE_REINDEX: 1,
}

#: Actions that are never a data/schema mutation and are always permitted,
#: for every caller, without being logged.
_ALWAYS_ALLOWED: frozenset[int] = frozenset(
    {
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
        sqlite3.SQLITE_SAVEPOINT,
        sqlite3.SQLITE_TRANSACTION,
    }
)

DEFAULT_LOG_RELATIVE_PATH = Path("04_LOGS") / "write_authorization.jsonl"


def _resolve_caller(frame) -> tuple[str, str]:
    """Identify the direct caller from an already-captured frame.

    Never walks or searches the stack: the caller passes the exact frame
    it wants identified (always ``sys._getframe(1)`` at the call site,
    one fixed hop above the overridden execute/executemany/executescript
    method). The capability belongs to whichever function that frame
    represents -- if a future shared helper sits between two writers and
    itself calls execute(), the helper becomes the single writer of
    record, uniformly, not a silently inherited or lost identity.
    """
    filename = frame.f_code.co_filename
    try:
        relative = Path(filename).resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        relative = filename
    qualname = getattr(frame.f_code, "co_qualname", None) or frame.f_code.co_name
    return (relative, qualname)


def _resolve_log_path(database: object) -> Path | None:
    """Best-effort log location for a real GMV.db target; ``None`` otherwise.

    Deliberately does not log for ``:memory:`` connections, ``mode=ro``
    URIs, or arbitrary test/rehearsal paths -- only for the one real
    production database shape (``.../09_DATABASE/GMV.db``). Logging is
    observability, never a precondition for a database operation, so an
    unresolved path means "skip logging", not an error.
    """
    if not isinstance(database, (str, os.PathLike)):
        return None
    text = os.fspath(database)
    if text == ":memory:" or text.startswith("file:"):
        return None
    path = Path(text)
    if path.name != "GMV.db" or path.parent.name != "09_DATABASE":
        return None
    return path.parent.parent / DEFAULT_LOG_RELATIVE_PATH


def _append_log_record(log_path: Path | None, record: dict[str, object]) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(log_path.parent, 0o700)
    descriptor = os.open(log_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)


def _decide(
    action_code: int,
    arg1: str | None,
    arg2: str | None,
    caller: tuple[str, str] | None,
) -> tuple[str, str, str | None]:
    """Return (status, verb, object) for a governed action.

    status is "authorized" or "violation". Every action code not
    explicitly recognized below falls through to the final, unconditional
    "violation" return -- there is no "else: allow" branch anywhere in
    this function.
    """
    if action_code in _DML_VERBS:
        verb = _DML_VERBS[action_code]
        table = arg1 or ""
        if caller is not None and (
            caller in DDL_CALLERS or (*caller, verb, table) in DML_CAPABILITIES
        ):
            return "authorized", verb, table
        return "violation", verb, table

    if action_code == sqlite3.SQLITE_PRAGMA:
        pragma_name = arg1 or ""
        if arg2 is None:
            return "authorized", "PRAGMA_READ", pragma_name
        # PRAGMA writes are governed by an explicit name allow-list, not by
        # caller trust alone: only `user_version` (schema-version bookkeeping)
        # and `foreign_keys` (the migration-confined FK toggle, already
        # fenced by ADR_DB002_RESTRICTIVE_FOREIGN_KEYS.md) are ever granted,
        # and only to the 2 DDL callers. SQLite reports the pragma name
        # exactly as written in the SQL text (case preserved, verified
        # empirically) -- normalize before comparing so this cannot be
        # bypassed by case alone. Every other PRAGMA write -- including
        # journal_mode -- is denied even for a DDL caller; there is no
        # blanket "DDL callers may write any PRAGMA" branch. The one-time
        # connect_path() bootstrap (`PRAGMA foreign_keys = ON`) runs before
        # install() and never reaches this authorizer at all.
        if (
            caller is not None
            and caller in DDL_CALLERS
            and pragma_name.lower() in _AUTHORIZED_PRAGMA_WRITES
        ):
            return "authorized", "PRAGMA_WRITE", pragma_name
        return "violation", "PRAGMA_WRITE", pragma_name

    if action_code in _DDL_ACTION_NAMES:
        verb = _DDL_ACTION_NAMES[action_code]
        arg_index = _DDL_OBJECT_ARG[action_code]
        obj = (arg2 if arg_index == 2 else arg1) or ""
        if caller is not None and caller in DDL_CALLERS:
            return "authorized", verb, obj
        return "violation", verb, obj

    # SQLITE_ATTACH, SQLITE_DETACH, SQLITE_ANALYZE, SQLITE_CREATE_VTABLE,
    # SQLITE_DROP_VTABLE, and any action code introduced by a future
    # SQLite version and not listed above: denied by construction.
    return "violation", f"ACTION_{action_code}", arg1


class AuthorizingCursor(sqlite3.Cursor):
    def execute(self, sql, parameters=()):
        caller = _resolve_caller(sys._getframe(1))
        return _guarded_call(self.connection, caller, super().execute, sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        caller = _resolve_caller(sys._getframe(1))
        return _guarded_call(
            self.connection, caller, super().executemany, sql, seq_of_parameters
        )

    def executescript(self, sql_script):
        caller = _resolve_caller(sys._getframe(1))
        return _guarded_call(self.connection, caller, super().executescript, sql_script)


class AuthorizingConnection(sqlite3.Connection):
    def cursor(self, factory=None):
        return super().cursor(factory or AuthorizingCursor)

    def execute(self, sql, parameters=()):
        caller = _resolve_caller(sys._getframe(1))
        return _guarded_call(self, caller, super().execute, sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        caller = _resolve_caller(sys._getframe(1))
        return _guarded_call(self, caller, super().executemany, sql, seq_of_parameters)

    def executescript(self, sql_script):
        caller = _resolve_caller(sys._getframe(1))
        return _guarded_call(self, caller, super().executescript, sql_script)

    def set_authorizer(self, authorizer):
        if getattr(self, "_gmv_authorizer_locked", False):
            raise UnauthorizedWriteError(
                "set_authorizer is locked on this Core-issued connection"
            )
        return super().set_authorizer(authorizer)


def _guarded_call(connection, caller, bound_method, *args):
    stack = getattr(connection, "_gmv_caller_stack", None)
    if stack is None:
        # Authorization has not been installed on this connection yet (the
        # DB-002 foreign-key bootstrap in gmv_core.database runs before
        # install() is called) -- pass straight through, ungoverned.
        return bound_method(*args)
    stack.append(caller)
    connection._gmv_last_denial = None
    try:
        return bound_method(*args)
    except sqlite3.DatabaseError as exc:
        denial = connection._gmv_last_denial
        if denial is not None:
            denial_caller, verb, table = denial
            raise UnauthorizedWriteError(
                f"unauthorized write: caller={denial_caller} verb={verb} object={table}"
            ) from exc
        raise
    finally:
        stack.pop()
        connection._gmv_last_denial = None


def _make_authorizer(connection, log_path):
    def authorizer(action_code, arg1, arg2, dbname, source):
        if action_code in _ALWAYS_ALLOWED:
            return sqlite3.SQLITE_OK

        caller = connection._gmv_caller_stack[-1] if connection._gmv_caller_stack else None
        status, verb, obj = _decide(action_code, arg1, arg2, caller)
        mode = connection._gmv_mode

        if status == "authorized":
            # Authorized actions are never logged: the log exists to
            # surface violations (would_deny/denied) during the log-only
            # observation period, not to duplicate a full audit trail of
            # already-legitimate operations. A connection that never
            # violates the capability matrix writes nothing to disk.
            return sqlite3.SQLITE_OK

        if mode == "enforce":
            outcome = "denied"
            decision = sqlite3.SQLITE_DENY
            connection._gmv_last_denial = (caller, verb, obj)
        else:
            outcome = "would_deny"
            decision = sqlite3.SQLITE_OK

        _append_log_record(
            log_path,
            {
                "timestamp": _now_iso(),
                "caller_file": caller[0] if caller else None,
                "caller_function": caller[1] if caller else None,
                "verb": verb,
                "table": obj,
                "mode": mode,
                "outcome": outcome,
                "correlation_id": connection._gmv_correlation_id,
            },
        )
        return decision

    return authorizer


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


def install(
    connection: sqlite3.Connection,
    *,
    mode: str,
    database: object = None,
) -> None:
    """Install log-only or enforce-mode authorization on an open connection.

    Only ``gmv_core.database.connect_path`` calls this in production, and
    it always passes the literal string ``"log"`` -- there is no
    production code path that can select ``"enforce"``. Tests call this
    directly with either mode against their own throwaway connections.

    ``database`` is the same path/URI argument the connection was opened
    with; it is used only to derive the log location (see
    ``_resolve_log_path``) and never touched otherwise.
    """
    if mode not in ("log", "enforce"):
        raise ValueError(f"unsupported write-authorization mode: {mode!r}")
    connection._gmv_mode = mode
    connection._gmv_caller_stack = []
    connection._gmv_last_denial = None
    connection._gmv_correlation_id = os.environ.get("GMV_CORRELATION_ID") or uuid.uuid4().hex
    log_path = _resolve_log_path(database)
    connection.set_authorizer(_make_authorizer(connection, log_path))
    connection._gmv_authorizer_locked = True
