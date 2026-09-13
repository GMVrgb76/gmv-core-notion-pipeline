-- Registered as CRAWLER_SOURCE_REGISTRY_VERSION = 9 in gmv_core/migrations.py.
-- Deliberately NOT CURRENT_SCHEMA_VERSION and NOT in SUPPORTED_SCHEMA_VERSIONS:
-- the crawler subsystem that owns this table does not exist yet, so no
-- caller of migrate(db) without an explicit target_version=9 is affected.
-- Reachable today only via migrate(db, target_version=CRAWLER_SOURCE_REGISTRY_VERSION),
-- the same way versions 1-7 remain reachable without being current.
--
-- Purpose: give the GMV Crawler its own live-scanning registry without
-- duplicating the identity anchor already owned by `resources`
-- (UNIQUE(sha256), gmv_core/migration_sql/006_foreign_keys.sql).
-- `resources` answers "is this content a canonical Core Resource Object";
-- this table answers "what does the crawler currently see at a source,
-- and has that changed since the last scan" -- a different, narrower
-- question that `resources` was never shaped to answer (single `path`,
-- no revision, no change-detection state, single `imported_at`).
--
-- resource_oid is nullable by design: a row can exist here from the
-- DISCOVER stage before the file has been promoted to a Resource Object
-- at REGISTER. Once populated, `FOREIGN KEY (resource_oid) REFERENCES
-- resources(resource_oid)` is the exact same reference import_queue uses
-- (006_foreign_keys.sql:180-181, canonical FK #10 in
-- ADR_DB002_RESTRICTIVE_FOREIGN_KEYS.md) -- not a lookalike pointed at
-- objects(oid). Referencing resources directly (rather than objects)
-- transitively inherits resources' own type-check triggers
-- (008_oid_type_consistency.sql) and additionally guarantees a real
-- resources row (path/sha256/size_bytes) exists, not just a Resource-typed
-- Object with nothing behind it.

BEGIN IMMEDIATE;

CREATE TABLE crawler_source_registry (
    content_hash TEXT PRIMARY KEY
        CHECK(content_hash GLOB 'sha256:[0-9a-f]*' AND length(content_hash) = 71),
    connector TEXT NOT NULL,
    canonical_locator TEXT NOT NULL,
    resource_oid TEXT,
    remote_revision TEXT,
    state TEXT NOT NULL DEFAULT 'NEW'
        CHECK(state IN ('NEW', 'UNCHANGED', 'MODIFIED', 'MOVED', 'DELETED', 'FAILED')),
    discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY (resource_oid) REFERENCES resources(resource_oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE INDEX crawler_source_registry_resource_oid_idx
    ON crawler_source_registry(resource_oid);

CREATE INDEX crawler_source_registry_state_idx
    ON crawler_source_registry(state);

CREATE INDEX crawler_source_registry_connector_idx
    ON crawler_source_registry(connector);

-- Correction 6 (silent deletion bug in gmv_evidence_pipeline.py::scan()):
-- a source with no residual path for its content_hash transitions state
-- to DELETED and stamps deleted_at. The row is never removed by the
-- crawler itself. Both INSERT and UPDATE are guarded -- an INSERT that
-- lands directly on state='DELETED' with deleted_at NULL is rejected just
-- like an UPDATE would be; the UPDATE trigger watches both `state` and
-- `deleted_at` so a later UPDATE that clears deleted_at back to NULL while
-- state stays 'DELETED' cannot slip through by touching only one column.
CREATE TRIGGER gmv_crawler_source_registry_deleted_at_required_insert
BEFORE INSERT ON crawler_source_registry
FOR EACH ROW
WHEN NEW.state = 'DELETED' AND NEW.deleted_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'crawler_source_registry.deleted_at must be set when state=DELETED');
END;

CREATE TRIGGER gmv_crawler_source_registry_deleted_at_required_update
BEFORE UPDATE OF state, deleted_at ON crawler_source_registry
FOR EACH ROW
WHEN NEW.state = 'DELETED' AND NEW.deleted_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'crawler_source_registry.deleted_at must be set when state=DELETED');
END;

PRAGMA user_version = 9;

COMMIT;
