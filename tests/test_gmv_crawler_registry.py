"""Crawler REGISTER + DETECT CHANGE driver for crawler_source_registry (Task 2).

Covers the algorithm specified by opencode_task_2.md: first scan (all NEW),
identical re-scan (all UNCHANGED), same-content-new-locator (MOVED),
same-locator-new-content (MODIFIED, old row transitions to DELETED rather
than being removed), disappeared file (DELETED with deleted_at, row never
deleted), and the real migration-009 triggers (DELETED without deleted_at
rejected on both INSERT and UPDATE). Plus the two decisions the brief
leaves open, tested against the implementation's documented behavior: a
per-item content_hash failure marks any existing row for that locator as
FAILED and is excluded from the DELETED sweep; brand-new unreadable items
are reported without any write. No real connector, no network calls, no
credentials -- the connector is a hand-implemented SourceConnector
Protocol, the same fake-injection pattern tests/test_gmv_dropbox_connector.py
already establishes.
"""

import hashlib
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))
import gmv_core.migrations as migrations  # noqa: E402
from gmv_crawler_contracts import SourceConnector, SourceListing  # noqa: E402
from gmv_crawler_registry import register_scan  # noqa: E402
from tests.helpers import connect_fixture_database  # noqa: E402

NOW_1 = "2026-01-01T10:00:00Z"
NOW_2 = "2026-01-02T10:00:00Z"
NOW_3 = "2026-01-03T10:00:00Z"

_COLUMNS = (
    "content_hash",
    "connector",
    "canonical_locator",
    "resource_oid",
    "remote_revision",
    "state",
    "discovered_at",
    "last_seen_at",
    "deleted_at",
)


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class FakeSource:
    """Hand-implemented SourceConnector (structural Protocol, no base
    class, same pattern as tests/test_gmv_dropbox_connector.py's fake
    session). `register_scan` is only allowed to call list() and
    content_hash(): the other three Protocol methods raise AssertionError
    so any accidental use fails the test loudly. Locators in `unreadable`
    make content_hash() raise -- the per-item failure path."""

    def __init__(
        self,
        locators: dict[str, str],
        *,
        unreadable: set[str] | None = None,
    ) -> None:
        self.locators = dict(locators)
        self.unreadable = set(unreadable or ())

    def list(self) -> list[SourceListing]:
        stamp = datetime.fromisoformat("2026-01-01T00:00:00+00:00").replace(tzinfo=UTC)
        return [
            SourceListing(locator=loc, filename=Path(loc).name, size=0, modified_at=stamp)
            for loc in self.locators
        ]

    def metadata(self, locator: str):  # pragma: no cover - must never be called
        raise AssertionError("register_scan must not call metadata()")

    def download(self, locator: str):  # pragma: no cover - must never be called
        raise AssertionError("register_scan must not call download()")

    def revision(self, locator: str):  # pragma: no cover - must never be called
        raise AssertionError("register_scan must not call revision()")

    def content_hash(self, locator: str) -> str:
        if locator in self.unreadable:
            raise RuntimeError(f"unreadable: {locator}")
        return self.locators[locator]


def _migrated_database(tmp_path: Path, name: str = "crawler-registry.db") -> Path:
    database = tmp_path / name
    assert (
        migrations.migrate(
            database,
            target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION,
        )
        == migrations.CRAWLER_SOURCE_REGISTRY_VERSION
    )
    return database


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    database = _migrated_database(tmp_path)
    con = connect_fixture_database(database)
    yield con
    con.close()


def _rows(connection: sqlite3.Connection) -> list[dict]:
    return [
        dict(zip(_COLUMNS, row))
        for row in connection.execute(
            "SELECT content_hash, connector, canonical_locator, resource_oid, "
            "remote_revision, state, discovered_at, last_seen_at, deleted_at "
            "FROM crawler_source_registry ORDER BY content_hash"
        ).fetchall()
    ]


def test_fake_source_satisfies_source_connector_protocol() -> None:
    """Grounding: the fake really implements the real step-4 Protocol, so
    register_scan() is exercised against the contract it actually takes --
    not against a lookalike the real contract would reject."""
    assert isinstance(FakeSource({"/a": _hash("a")}), SourceConnector)


def test_first_scan_registers_every_listing_as_new(connection: sqlite3.Connection) -> None:
    connector = FakeSource({"/a.pdf": _hash("file-a"), "/b.pdf": _hash("file-b")})
    result = register_scan(connection, connector, connector_id="dropbox", now=NOW_1)

    assert result.created == 2
    assert result.unchanged == result.modified == result.moved == result.deleted == 0
    assert result.transitioned_to_failed == 0
    assert result.failed == ()

    rows = _rows(connection)
    assert {r["content_hash"] for r in rows} == {_hash("file-a"), _hash("file-b")}
    for row in rows:
        assert row["state"] == "NEW"
        assert row["connector"] == "dropbox"
        assert row["discovered_at"] == NOW_1
        assert row["last_seen_at"] == NOW_1
        assert row["deleted_at"] is None
        # Task scope: resource_oid/remote_revision are never written here.
        assert row["resource_oid"] is None
        assert row["remote_revision"] is None


def test_second_identical_scan_marks_unchanged_and_keeps_discovered_at(
    connection: sqlite3.Connection,
) -> None:
    connector = FakeSource({"/a.pdf": _hash("file-a")})
    register_scan(connection, connector, connector_id="dropbox", now=NOW_1)
    result = register_scan(connection, connector, connector_id="dropbox", now=NOW_2)

    assert result.unchanged == 1
    assert result.created == result.modified == result.moved == result.deleted == 0

    row = _rows(connection)[0]
    assert row["state"] == "UNCHANGED"
    assert row["discovered_at"] == NOW_1
    assert row["last_seen_at"] == NOW_2
    assert row["deleted_at"] is None


def test_same_content_new_locator_is_moved(connection: sqlite3.Connection) -> None:
    content = _hash("artifact")
    register_scan(
        connection, FakeSource({"/old/artifact.pdf": content}), connector_id="dropbox", now=NOW_1
    )
    result = register_scan(
        connection, FakeSource({"/new/artifact.pdf": content}), connector_id="dropbox", now=NOW_2
    )

    assert result.moved == 1
    assert result.created == result.unchanged == result.modified == result.deleted == 0

    rows = _rows(connection)
    assert len(rows) == 1
    assert rows[0]["content_hash"] == content
    assert rows[0]["canonical_locator"] == "/new/artifact.pdf"
    assert rows[0]["state"] == "MOVED"
    assert rows[0]["discovered_at"] == NOW_1
    assert rows[0]["last_seen_at"] == NOW_2
    assert rows[0]["deleted_at"] is None


def test_modified_content_at_same_locator_keeps_old_row(
    connection: sqlite3.Connection,
) -> None:
    old_hash, new_hash = _hash("v1"), _hash("v2")
    register_scan(connection, FakeSource({"/x": old_hash}), connector_id="dropbox", now=NOW_1)
    result = register_scan(
        connection, FakeSource({"/x": new_hash}), connector_id="dropbox", now=NOW_2
    )

    assert result.modified == 1
    assert result.deleted == 1
    assert result.created == result.unchanged == result.moved == 0

    rows = _rows(connection)
    # The old row was never DELETEd from the table -- it transitioned.
    assert len(rows) == 2
    by_hash = {r["content_hash"]: r for r in rows}
    assert by_hash[old_hash]["state"] == "DELETED"
    assert by_hash[old_hash]["deleted_at"] == NOW_2
    assert by_hash[old_hash]["last_seen_at"] == NOW_2
    assert by_hash[old_hash]["discovered_at"] == NOW_1
    assert by_hash[old_hash]["canonical_locator"] == "/x"
    assert by_hash[new_hash]["state"] == "MODIFIED"
    assert by_hash[new_hash]["deleted_at"] is None
    assert by_hash[new_hash]["discovered_at"] == NOW_2
    assert by_hash[new_hash]["last_seen_at"] == NOW_2


def test_removed_file_transitions_to_deleted_never_removed(
    connection: sqlite3.Connection,
) -> None:
    content = _hash("gone")
    register_scan(connection, FakeSource({"/gone.txt": content}), connector_id="dropbox", now=NOW_1)
    result = register_scan(connection, FakeSource({}), connector_id="dropbox", now=NOW_2)

    assert result.deleted == 1
    assert result.created == result.unchanged == result.modified == result.moved == 0

    # Direct query: the row still exists -- never a DELETE FROM.
    assert connection.execute("SELECT COUNT(*) FROM crawler_source_registry").fetchone() == (1,)
    row = _rows(connection)[0]
    assert row["content_hash"] == content
    assert row["state"] == "DELETED"
    assert row["deleted_at"] == NOW_2
    assert row["last_seen_at"] == NOW_2
    assert row["discovered_at"] == NOW_1


def test_real_trigger_rejects_deleted_without_deleted_at_on_insert(
    connection: sqlite3.Connection,
) -> None:
    """The migration-009 triggers, not this module's discipline: a direct
    INSERT landing on state='DELETED' with deleted_at NULL must be
    rejected by SQLite itself."""
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO crawler_source_registry "
            "(content_hash, connector, canonical_locator, state, discovered_at, last_seen_at) "
            "VALUES (?, 'dropbox', '/manual', 'DELETED', 't', 't')",
            (_hash("manual"),),
        )


def test_real_trigger_rejects_deleted_without_deleted_at_on_update(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        "INSERT INTO crawler_source_registry "
        "(content_hash, connector, canonical_locator, state, discovered_at, last_seen_at) "
        "VALUES (?, 'dropbox', '/x', 'NEW', 't', 't')",
        (_hash("x"),),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE crawler_source_registry SET state='DELETED' WHERE content_hash=?",
            (_hash("x"),),
        )
    # The legal pairing is accepted -- the state transition exists, the row never disappears.
    connection.execute(
        "UPDATE crawler_source_registry SET state='DELETED', deleted_at='t' WHERE content_hash=?",
        (_hash("x"),),
    )
    assert connection.execute("SELECT COUNT(*) FROM crawler_source_registry").fetchone() == (1,)


def test_content_hash_failure_marks_existing_row_failed_and_does_not_abort(
    connection: sqlite3.Connection,
) -> None:
    h_x, h_y = _hash("x"), _hash("y")
    register_scan(
        connection, FakeSource({"/x": h_x, "/y": h_y}), connector_id="dropbox", now=NOW_1
    )
    result = register_scan(
        connection,
        FakeSource({"/x": h_x, "/y": h_y}, unreadable={"/x"}),
        connector_id="dropbox",
        now=NOW_2,
    )

    assert result.failed == (("/x", "RuntimeError: unreadable: /x"),)
    assert result.transitioned_to_failed == 1
    assert result.unchanged == 1  # the healthy sibling still processed: no whole-scan abort

    rows = {r["content_hash"]: r for r in _rows(connection)}
    assert rows[h_x]["state"] == "FAILED"
    assert rows[h_x]["deleted_at"] is None
    assert rows[h_x]["last_seen_at"] == NOW_2
    assert rows[h_x]["canonical_locator"] == "/x"
    # The FAILED row survived the step-5 sweep: its locator was excluded.
    assert rows[h_y]["state"] == "UNCHANGED"


def test_content_hash_failure_for_brand_new_item_reports_without_write(
    connection: sqlite3.Connection,
) -> None:
    result = register_scan(
        connection,
        FakeSource({"/brand-new": _hash("x")}, unreadable={"/brand-new"}),
        connector_id="dropbox",
        now=NOW_1,
    )

    assert result.failed == (("/brand-new", "RuntimeError: unreadable: /brand-new"),)
    assert result.created == 0
    assert result.transitioned_to_failed == 0
    assert connection.execute("SELECT COUNT(*) FROM crawler_source_registry").fetchone() == (0,)


def test_malformed_content_hash_is_a_per_item_failure(
    connection: sqlite3.Connection,
) -> None:
    """A connector returning a non-sha256 value violates the step-4
    contract its own validate_content_hash() documents -- treated as the
    same isolated per-item failure as an exception, never an abort."""
    result = register_scan(
        connection, FakeSource({"/bad": "not-a-valid-hash"}), connector_id="dropbox", now=NOW_1
    )

    assert result.failed == (
        ("/bad", "ValueError: content_hash must match sha256:<64 lowercase hex chars>, got: 'not-a-valid-hash'"),
    )
    assert connection.execute("SELECT COUNT(*) FROM crawler_source_registry").fetchone() == (0,)


def test_recovery_from_failed_back_to_unchanged(connection: sqlite3.Connection) -> None:
    content = _hash("x")
    register_scan(connection, FakeSource({"/x": content}), connector_id="dropbox", now=NOW_1)
    register_scan(
        connection,
        FakeSource({"/x": content}, unreadable={"/x"}),
        connector_id="dropbox",
        now=NOW_2,
    )

    result = register_scan(connection, FakeSource({"/x": content}), connector_id="dropbox", now=NOW_3)

    assert result.unchanged == 1
    row = _rows(connection)[0]
    assert row["state"] == "UNCHANGED"
    assert row["deleted_at"] is None


def test_connectors_are_independent_locator_namespaces(
    connection: sqlite3.Connection,
) -> None:
    """Two connectors sharing a locator string but different content must
    not see each other's rows: the locator lookup is scoped per
    connector_id, so neither is a false MODIFIED against the other's
    row."""
    dropbox = FakeSource({"/same": _hash("dropbox-content")})
    fs = FakeSource({"/same": _hash("fs-content")})
    register_scan(connection, dropbox, connector_id="dropbox", now=NOW_1)
    result_fs = register_scan(connection, fs, connector_id="fs", now=NOW_1)

    assert result_fs.created == 1
    assert result_fs.modified == 0
    rows = {r["connector"]: r for r in _rows(connection)}
    assert set(rows) == {"dropbox", "fs"}
    assert rows["dropbox"]["state"] == "NEW"
    assert rows["fs"]["state"] == "NEW"

    result_fs_again = register_scan(connection, fs, connector_id="fs", now=NOW_2)
    assert result_fs_again.unchanged == 1
    assert result_fs_again.modified == 0
    assert connection.execute("SELECT COUNT(*) FROM crawler_source_registry").fetchone() == (2,)


def test_duplicate_content_in_one_scan_collapses_to_single_row(
    connection: sqlite3.Connection,
) -> None:
    """Adversarial: the same content (same hash) listed twice in one scan,
    at two different locators. The table is content-addressed (content_hash
    is the PK, singular canonical_locator) -- the second occurrence MOVEs
    the row, it never becomes a second row. Documented behavior of the
    specified algorithm, not a duplicate bug."""
    content = _hash("dup")
    result = register_scan(
        connection,
        FakeSource({"/a/dup": content, "/b/dup": content}),
        connector_id="dropbox",
        now=NOW_1,
    )

    assert result.created == 1
    assert result.moved == 1
    rows = _rows(connection)
    assert len(rows) == 1
    assert rows[0]["canonical_locator"] == "/b/dup"


def test_register_scan_commits_so_a_fresh_connection_sees_the_rows(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)
    con = connect_fixture_database(database)
    try:
        register_scan(con, FakeSource({"/a": _hash("a")}), connector_id="dropbox", now=NOW_1)
    finally:
        con.close()

    with sqlite3.connect(database) as fresh:
        assert fresh.execute("SELECT COUNT(*) FROM crawler_source_registry").fetchone() == (1,)