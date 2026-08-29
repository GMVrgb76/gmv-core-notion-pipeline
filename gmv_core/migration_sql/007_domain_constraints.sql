PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

CREATE TEMP TABLE _gmv_db003_preflight_guard (
    oid_grammar_valid INTEGER NOT NULL CHECK(oid_grammar_valid = 1),
    service_run_status_valid INTEGER NOT NULL CHECK(service_run_status_valid = 1),
    compatibility_mode_valid INTEGER NOT NULL CHECK(compatibility_mode_valid = 1),
    relations_non_self_valid INTEGER NOT NULL CHECK(relations_non_self_valid = 1)
);

INSERT INTO _gmv_db003_preflight_guard
SELECT
    CASE WHEN EXISTS (
        SELECT 1
        FROM objects
        WHERE typeof(oid) <> 'text'
           OR length(oid) <> 10
           OR oid NOT GLOB '[A-Z][A-Z][A-Z]-[0-9][0-9][0-9][0-9][0-9][0-9]'
           OR substr(oid, 5, 6) = '000000'
    ) THEN 0 ELSE 1 END,
    CASE WHEN EXISTS (
        SELECT 1
        FROM service_runs
        WHERE typeof(status) <> 'text'
           OR status NOT IN ('OK', 'ERROR', 'TIMEOUT', 'CANCELLED')
    ) THEN 0 ELSE 1 END,
    CASE WHEN EXISTS (
        SELECT 1
        FROM engines
        WHERE typeof(compatibility_mode) <> 'integer'
           OR compatibility_mode NOT IN (0, 1)
    ) THEN 0 ELSE 1 END,
    CASE WHEN EXISTS (
        SELECT 1
        FROM relations
        WHERE source_oid = target_oid
    ) THEN 0 ELSE 1 END;

CREATE TEMP TABLE _gmv_db003_sequences AS
SELECT name, seq
FROM sqlite_sequence
WHERE name IN ('service_runs', 'relations');

DROP VIEW plugin_services_view;
DROP VIEW plugin_registry_view;
DROP VIEW timeline_view;
DROP VIEW service_registry_view;
DROP VIEW relation_view;
DROP VIEW resource_view;

CREATE TABLE _gmv_db003_objects (
    oid TEXT PRIMARY KEY NOT NULL
        CHECK(
            typeof(oid) = 'text'
            AND length(oid) = 10
            AND oid GLOB '[A-Z][A-Z][A-Z]-[0-9][0-9][0-9][0-9][0-9][0-9]'
            AND substr(oid, 5, 6) <> '000000'
        ),
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE _gmv_db003_service_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_oid TEXT NOT NULL,
    service_name TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK(status IN ('OK', 'ERROR', 'TIMEOUT', 'CANCELLED')),
    duration_seconds REAL,
    command TEXT,
    stdout_path TEXT,
    stderr_path TEXT,
    summary TEXT,
    FOREIGN KEY (service_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE _gmv_db003_engines (
    engine_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    compatibility_mode INTEGER NOT NULL DEFAULT 0
        CHECK(
            typeof(compatibility_mode) = 'integer'
            AND compatibility_mode IN (0, 1)
        ),
    entrypoint TEXT,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE _gmv_db003_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_oid TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_oid TEXT NOT NULL,
    created_at TEXT,
    source TEXT,
    UNIQUE(source_oid, relation_type, target_oid),
    CHECK(source_oid <> target_oid),
    FOREIGN KEY (source_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (target_oid) REFERENCES objects(oid)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

INSERT INTO _gmv_db003_objects
SELECT oid, type, name, status, created_at, updated_at
FROM objects;

INSERT INTO _gmv_db003_service_runs
SELECT id, service_oid, service_name, run_at, status, duration_seconds,
       command, stdout_path, stderr_path, summary
FROM service_runs;

INSERT INTO _gmv_db003_engines
SELECT engine_id, name, category, version, status, compatibility_mode,
       entrypoint, description, created_at, updated_at
FROM engines;

INSERT INTO _gmv_db003_relations
SELECT id, source_oid, relation_type, target_oid, created_at, source
FROM relations;

DROP TABLE relations;
DROP TABLE service_runs;
DROP TABLE engines;
DROP TABLE objects;

ALTER TABLE _gmv_db003_objects RENAME TO objects;
ALTER TABLE _gmv_db003_service_runs RENAME TO service_runs;
ALTER TABLE _gmv_db003_engines RENAME TO engines;
ALTER TABLE _gmv_db003_relations RENAME TO relations;

DELETE FROM sqlite_sequence
WHERE name IN ('service_runs', 'relations');

INSERT INTO sqlite_sequence(name, seq)
SELECT name, seq FROM _gmv_db003_sequences;

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

CREATE TEMP TABLE _gmv_db003_fk_guard (
    valid INTEGER NOT NULL CHECK(valid = 1)
);

INSERT INTO _gmv_db003_fk_guard(valid)
SELECT CASE
    WHEN EXISTS (SELECT 1 FROM pragma_foreign_key_check)
    THEN 0
    ELSE 1
END;

DROP TABLE _gmv_db003_fk_guard;
DROP TABLE _gmv_db003_sequences;
DROP TABLE _gmv_db003_preflight_guard;

PRAGMA user_version = 7;
COMMIT;
PRAGMA foreign_keys = ON;
