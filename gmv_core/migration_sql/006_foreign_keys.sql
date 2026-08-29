PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

CREATE TEMP TABLE _gmv_db002_orphan_guard (
    valid INTEGER NOT NULL CHECK(valid = 1)
);

INSERT INTO _gmv_db002_orphan_guard(valid)
SELECT CASE WHEN
    EXISTS (
        SELECT 1 FROM events AS child
        LEFT JOIN objects AS parent ON parent.oid = child.oid
        WHERE parent.oid IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM events AS child
        LEFT JOIN events AS parent ON parent.id = child.supersedes_event_id
        WHERE child.supersedes_event_id IS NOT NULL AND parent.id IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM service_runs AS child
        LEFT JOIN objects AS parent ON parent.oid = child.service_oid
        WHERE parent.oid IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM plugin_metadata AS child
        LEFT JOIN objects AS parent ON parent.oid = child.plugin_oid
        WHERE parent.oid IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM plugin_services AS child
        LEFT JOIN plugin_metadata AS parent
          ON parent.plugin_oid = child.plugin_oid
        WHERE parent.plugin_oid IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM plugin_services AS child
        LEFT JOIN objects AS parent ON parent.oid = child.service_oid
        WHERE parent.oid IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM relations AS child
        LEFT JOIN objects AS parent ON parent.oid = child.source_oid
        WHERE parent.oid IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM relations AS child
        LEFT JOIN objects AS parent ON parent.oid = child.target_oid
        WHERE parent.oid IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM resources AS child
        LEFT JOIN objects AS parent ON parent.oid = child.resource_oid
        WHERE parent.oid IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM import_queue AS child
        LEFT JOIN resources AS parent
          ON parent.resource_oid = child.resource_oid
        WHERE child.resource_oid IS NOT NULL AND parent.resource_oid IS NULL
    )
THEN 0 ELSE 1 END;

CREATE TEMP TABLE _gmv_db002_sequences AS
SELECT name, seq
FROM sqlite_sequence
WHERE name IN (
    'events',
    'service_runs',
    'plugin_services',
    'relations',
    'import_queue'
);

DROP VIEW plugin_services_view;
DROP VIEW plugin_registry_view;
DROP VIEW timeline_view;
DROP VIEW timeline;
DROP VIEW service_registry_view;
DROP VIEW relation_view;
DROP VIEW resource_view;
DROP VIEW import_queue_view;

CREATE TABLE _gmv_db002_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oid TEXT NOT NULL,
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    source TEXT,
    supersedes_event_id INTEGER,
    FOREIGN KEY (oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_event_id) REFERENCES events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE _gmv_db002_service_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_oid TEXT NOT NULL,
    service_name TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_seconds REAL,
    command TEXT,
    stdout_path TEXT,
    stderr_path TEXT,
    summary TEXT,
    FOREIGN KEY (service_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE _gmv_db002_plugin_metadata (
    plugin_oid TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    path TEXT,
    description TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (plugin_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE _gmv_db002_plugin_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_oid TEXT NOT NULL,
    service_oid TEXT NOT NULL,
    role TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plugin_oid, service_oid),
    FOREIGN KEY (plugin_oid) REFERENCES plugin_metadata(plugin_oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (service_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE _gmv_db002_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_oid TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_oid TEXT NOT NULL,
    created_at TEXT,
    source TEXT,
    UNIQUE(source_oid, relation_type, target_oid),
    FOREIGN KEY (source_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (target_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE _gmv_db002_resources (
    resource_oid TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT,
    mime_guess TEXT,
    size_bytes INTEGER,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    UNIQUE(sha256),
    FOREIGN KEY (resource_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE _gmv_db002_import_queue (
    import_id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_oid TEXT,
    source_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    review_status TEXT NOT NULL DEFAULT 'pending_review',
    proposed_destination TEXT,
    confidence REAL,
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (resource_oid) REFERENCES resources(resource_oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

INSERT INTO _gmv_db002_events
SELECT id, oid, event_at, event_type, description, source, supersedes_event_id
FROM events;

INSERT INTO _gmv_db002_service_runs
SELECT id, service_oid, service_name, run_at, status, duration_seconds,
       command, stdout_path, stderr_path, summary
FROM service_runs;

INSERT INTO _gmv_db002_plugin_metadata
SELECT plugin_oid, slug, version, status, path, description, created_at, updated_at
FROM plugin_metadata;

INSERT INTO _gmv_db002_plugin_services
SELECT id, plugin_oid, service_oid, role, created_at
FROM plugin_services;

INSERT INTO _gmv_db002_relations
SELECT id, source_oid, relation_type, target_oid, created_at, source
FROM relations;

INSERT INTO _gmv_db002_resources
SELECT resource_oid, path, filename, extension, mime_guess, size_bytes, sha256,
       imported_at, status
FROM resources;

INSERT INTO _gmv_db002_import_queue
SELECT import_id, resource_oid, source_path, filename, status, review_status,
       proposed_destination, confidence, error, created_at, updated_at
FROM import_queue;

DROP TABLE plugin_services;
DROP TABLE plugin_metadata;
DROP TABLE import_queue;
DROP TABLE resources;
DROP TABLE relations;
DROP TABLE service_runs;
DROP TABLE events;

ALTER TABLE _gmv_db002_events RENAME TO events;
ALTER TABLE _gmv_db002_service_runs RENAME TO service_runs;
ALTER TABLE _gmv_db002_plugin_metadata RENAME TO plugin_metadata;
ALTER TABLE _gmv_db002_plugin_services RENAME TO plugin_services;
ALTER TABLE _gmv_db002_relations RENAME TO relations;
ALTER TABLE _gmv_db002_resources RENAME TO resources;
ALTER TABLE _gmv_db002_import_queue RENAME TO import_queue;

DELETE FROM sqlite_sequence
WHERE name IN (
    'events',
    'service_runs',
    'plugin_services',
    'relations',
    'import_queue'
);

INSERT INTO sqlite_sequence(name, seq)
SELECT name, seq FROM _gmv_db002_sequences;

CREATE VIEW timeline AS
SELECT id, oid, event_at, event_type, description, source
FROM events;

CREATE VIEW timeline_view AS
SELECT
    e.id,
    e.oid,
    o.type AS object_type,
    o.name AS object_name,
    e.event_at,
    e.event_type,
    e.description,
    e.source
FROM events e
LEFT JOIN objects o ON o.oid = e.oid
ORDER BY e.event_at DESC;

CREATE VIEW service_registry_view AS
SELECT
    oid AS service_oid,
    name AS service_name,
    status,
    created_at,
    updated_at
FROM objects
WHERE type = 'Service'
ORDER BY oid;

CREATE VIEW plugin_registry_view AS
SELECT
    o.oid AS plugin_oid,
    o.name AS plugin_name,
    pm.slug,
    pm.version,
    pm.status,
    pm.description
FROM objects o
JOIN plugin_metadata pm ON pm.plugin_oid = o.oid
WHERE o.type = 'Plugin'
ORDER BY o.oid;

CREATE VIEW plugin_services_view AS
SELECT
    p.plugin_oid,
    p.plugin_name,
    p.slug,
    ps.service_oid,
    s.name AS service_name,
    ps.role
FROM plugin_registry_view p
LEFT JOIN plugin_services ps ON ps.plugin_oid = p.plugin_oid
LEFT JOIN objects s ON s.oid = ps.service_oid
ORDER BY p.plugin_oid, ps.service_oid;

CREATE VIEW relation_view AS
SELECT
    r.id,
    r.source_oid,
    so.name AS source_name,
    so.type AS source_type,
    r.relation_type,
    r.target_oid,
    tobj.name AS target_name,
    tobj.type AS target_type,
    r.created_at,
    r.source
FROM relations r
LEFT JOIN objects so ON so.oid = r.source_oid
LEFT JOIN objects tobj ON tobj.oid = r.target_oid
ORDER BY r.id;

CREATE VIEW resource_view AS
SELECT
    r.resource_oid,
    o.name AS resource_name,
    o.status AS object_status,
    r.path,
    r.filename,
    r.extension,
    r.size_bytes,
    r.sha256,
    r.imported_at,
    r.status
FROM resources r
LEFT JOIN objects o ON o.oid = r.resource_oid;

CREATE VIEW import_queue_view AS
SELECT
    import_id,
    resource_oid,
    filename,
    status,
    review_status,
    proposed_destination,
    confidence,
    error,
    created_at,
    updated_at
FROM import_queue
ORDER BY created_at DESC;

CREATE TRIGGER events_reject_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only: UPDATE prohibited');
END;

CREATE TRIGGER events_reject_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only: DELETE prohibited');
END;

CREATE TRIGGER events_reject_id_reuse
BEFORE INSERT ON events
WHEN EXISTS (SELECT 1 FROM events WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'events are append-only: id reuse prohibited');
END;

CREATE TRIGGER events_require_superseded_event
BEFORE INSERT ON events
WHEN NEW.supersedes_event_id IS NOT NULL
 AND NOT EXISTS (
     SELECT 1 FROM events WHERE id = NEW.supersedes_event_id
 )
BEGIN
    SELECT RAISE(ABORT, 'superseded Event does not exist');
END;

CREATE TEMP TABLE _gmv_db002_fk_guard (
    valid INTEGER NOT NULL CHECK(valid = 1)
);

INSERT INTO _gmv_db002_fk_guard(valid)
SELECT CASE
    WHEN EXISTS (SELECT 1 FROM pragma_foreign_key_check)
    THEN 0
    ELSE 1
END;

DROP TABLE _gmv_db002_fk_guard;
DROP TABLE _gmv_db002_sequences;
DROP TABLE _gmv_db002_orphan_guard;

PRAGMA user_version = 6;
COMMIT;
PRAGMA foreign_keys = ON;
