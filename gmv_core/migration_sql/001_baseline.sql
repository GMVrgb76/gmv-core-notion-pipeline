BEGIN IMMEDIATE;

CREATE TABLE objects (
    oid TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE engine_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engine TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    duration_seconds REAL,
    command TEXT,
    stdout_path TEXT,
    stderr_path TEXT
);

CREATE TABLE timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oid TEXT NOT NULL,
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    source TEXT
);

CREATE TABLE engines (
    engine_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    compatibility_mode INTEGER NOT NULL DEFAULT 0,
    entrypoint TEXT,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE service_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_oid TEXT NOT NULL,
    service_name TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_seconds REAL,
    command TEXT,
    stdout_path TEXT,
    stderr_path TEXT,
    summary TEXT
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oid TEXT NOT NULL,
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    source TEXT
);

CREATE TABLE architecture_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    decision TEXT NOT NULL,
    consequence TEXT NOT NULL
);

CREATE TABLE plugin_metadata (
    plugin_oid TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    path TEXT,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE plugin_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_oid TEXT NOT NULL,
    service_oid TEXT NOT NULL,
    role TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plugin_oid, service_oid)
);

CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_oid TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_oid TEXT NOT NULL,
    created_at TEXT,
    source TEXT,
    UNIQUE(source_oid, relation_type, target_oid)
);

CREATE TABLE resources (
    resource_oid TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT,
    mime_guess TEXT,
    size_bytes INTEGER,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    UNIQUE(sha256)
);

CREATE TABLE import_queue (
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
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE VIEW timeline_view AS
SELECT e.id, e.oid, o.type AS object_type, o.name AS object_name,
       e.event_at, e.event_type, e.description, e.source
FROM events e
LEFT JOIN objects o ON o.oid = e.oid
ORDER BY e.event_at DESC;

CREATE VIEW service_registry_view AS
SELECT oid AS service_oid, name AS service_name, status, created_at, updated_at
FROM objects
WHERE type = 'Service'
ORDER BY oid;

CREATE VIEW plugin_registry_view AS
SELECT o.oid AS plugin_oid, o.name AS plugin_name, pm.slug, pm.version,
       pm.status, pm.description
FROM objects o
JOIN plugin_metadata pm ON pm.plugin_oid = o.oid
WHERE o.type = 'Plugin'
ORDER BY o.oid;

CREATE VIEW plugin_services_view AS
SELECT p.plugin_oid, p.plugin_name, p.slug, ps.service_oid,
       s.name AS service_name, ps.role
FROM plugin_registry_view p
LEFT JOIN plugin_services ps ON ps.plugin_oid = p.plugin_oid
LEFT JOIN objects s ON s.oid = ps.service_oid
ORDER BY p.plugin_oid, ps.service_oid;

CREATE VIEW relation_view AS
SELECT r.id, r.source_oid, so.name AS source_name, so.type AS source_type,
       r.relation_type, r.target_oid, target.name AS target_name,
       target.type AS target_type, r.created_at, r.source
FROM relations r
LEFT JOIN objects so ON so.oid = r.source_oid
LEFT JOIN objects target ON target.oid = r.target_oid
ORDER BY r.id;

CREATE VIEW resource_view AS
SELECT r.resource_oid, o.name AS resource_name, o.status AS object_status,
       r.path, r.filename, r.extension, r.size_bytes, r.sha256,
       r.imported_at, r.status
FROM resources r
LEFT JOIN objects o ON o.oid = r.resource_oid;

CREATE VIEW import_queue_view AS
SELECT import_id, resource_oid, filename, status, review_status,
       proposed_destination, confidence, error, created_at, updated_at
FROM import_queue
ORDER BY created_at DESC;

PRAGMA user_version = 1;

COMMIT;
