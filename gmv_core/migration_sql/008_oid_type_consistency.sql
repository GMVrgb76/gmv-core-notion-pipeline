CREATE TEMP TABLE _gmv_db008_connection_guard (
    foreign_keys_active INTEGER NOT NULL CHECK(foreign_keys_active = 1)
);

INSERT INTO _gmv_db008_connection_guard(foreign_keys_active)
SELECT foreign_keys FROM pragma_foreign_keys;

PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

CREATE TEMP TABLE _gmv_db008_preflight_guard (
    version_valid INTEGER NOT NULL CHECK(version_valid = 1),
    integrity_valid INTEGER NOT NULL CHECK(integrity_valid = 1),
    foreign_keys_valid INTEGER NOT NULL CHECK(foreign_keys_valid = 1),
    object_pairs_valid INTEGER NOT NULL CHECK(object_pairs_valid = 1),
    typed_references_valid INTEGER NOT NULL CHECK(typed_references_valid = 1),
    sequence_map_valid INTEGER NOT NULL CHECK(sequence_map_valid = 1),
    sequence_positions_valid INTEGER NOT NULL CHECK(sequence_positions_valid = 1)
);

INSERT INTO _gmv_db008_preflight_guard
SELECT
    CASE WHEN (SELECT user_version FROM pragma_user_version) = 7
        THEN 1 ELSE 0 END,
    CASE WHEN NOT EXISTS (
        SELECT 1 FROM pragma_integrity_check WHERE integrity_check <> 'ok'
    ) THEN 1 ELSE 0 END,
    CASE WHEN NOT EXISTS (SELECT 1 FROM pragma_foreign_key_check)
        THEN 1 ELSE 0 END,
    CASE WHEN NOT EXISTS (
        SELECT 1
        FROM objects
        WHERE typeof(oid) <> 'text'
           OR length(oid) <> 10
           OR oid NOT GLOB '[A-Z][A-Z][A-Z]-[0-9][0-9][0-9][0-9][0-9][0-9]'
           OR substr(oid, 5, 6) = '000000'
           OR NOT (
                (substr(oid, 1, 3) = 'COR' AND type = 'Core')
                OR (substr(oid, 1, 3) = 'PER' AND type = 'Person')
                OR (substr(oid, 1, 3) = 'PLG' AND type = 'Plugin')
                OR (substr(oid, 1, 3) = 'RES' AND type = 'Resource')
                OR (substr(oid, 1, 3) = 'SRV' AND type = 'Service')
                OR (substr(oid, 1, 3) = 'SYS' AND type = 'System')
           )
    ) THEN 1 ELSE 0 END,
    CASE WHEN NOT (
        EXISTS (
            SELECT 1 FROM resources r
            LEFT JOIN objects o ON o.oid = r.resource_oid
            WHERE o.oid IS NULL OR o.type <> 'Resource'
        )
        OR EXISTS (
            SELECT 1 FROM plugin_metadata pm
            LEFT JOIN objects o ON o.oid = pm.plugin_oid
            WHERE o.oid IS NULL OR o.type <> 'Plugin'
        )
        OR EXISTS (
            SELECT 1 FROM plugin_services ps
            LEFT JOIN objects o ON o.oid = ps.plugin_oid
            WHERE o.oid IS NULL OR o.type <> 'Plugin'
        )
        OR EXISTS (
            SELECT 1 FROM plugin_services ps
            LEFT JOIN objects o ON o.oid = ps.service_oid
            WHERE o.oid IS NULL OR o.type <> 'Service'
        )
        OR EXISTS (
            SELECT 1 FROM service_runs sr
            LEFT JOIN objects o ON o.oid = sr.service_oid
            WHERE o.oid IS NULL OR o.type <> 'Service'
        )
        OR EXISTS (
            SELECT 1 FROM import_queue iq
            LEFT JOIN objects o ON o.oid = iq.resource_oid
            WHERE iq.resource_oid IS NOT NULL
              AND (o.oid IS NULL OR o.type <> 'Resource')
        )
    ) THEN 1 ELSE 0 END,
    CASE WHEN
        (SELECT COUNT(*) FROM oid_sequences) = 6
        AND NOT EXISTS (
            SELECT 1
            FROM oid_sequences
            WHERE NOT (
                (prefix = 'COR' AND object_type = 'Core')
                OR (prefix = 'PER' AND object_type = 'Person')
                OR (prefix = 'PLG' AND object_type = 'Plugin')
                OR (prefix = 'RES' AND object_type = 'Resource')
                OR (prefix = 'SRV' AND object_type = 'Service')
                OR (prefix = 'SYS' AND object_type = 'System')
            )
        )
        THEN 1 ELSE 0 END,
    CASE WHEN NOT EXISTS (
        SELECT 1
        FROM oid_sequences s
        WHERE s.last_value < COALESCE(
            (
                SELECT MAX(CAST(substr(o.oid, 5, 6) AS INTEGER))
                FROM objects o
                WHERE o.type = s.object_type
                  AND substr(o.oid, 1, 3) = s.prefix
            ),
            0
        )
    ) THEN 1 ELSE 0 END;

DROP VIEW plugin_services_view;
DROP VIEW plugin_registry_view;
DROP VIEW timeline_view;
DROP VIEW service_registry_view;
DROP VIEW relation_view;
DROP VIEW resource_view;

CREATE TABLE _gmv_db008_objects (
    oid TEXT PRIMARY KEY NOT NULL
        CHECK(
            typeof(oid) = 'text'
            AND length(oid) = 10
            AND oid GLOB '[A-Z][A-Z][A-Z]-[0-9][0-9][0-9][0-9][0-9][0-9]'
            AND substr(oid, 5, 6) <> '000000'
        ),
    type TEXT NOT NULL
        CHECK(
            (substr(oid, 1, 3) = 'COR' AND type = 'Core')
            OR (substr(oid, 1, 3) = 'PER' AND type = 'Person')
            OR (substr(oid, 1, 3) = 'PLG' AND type = 'Plugin')
            OR (substr(oid, 1, 3) = 'RES' AND type = 'Resource')
            OR (substr(oid, 1, 3) = 'SRV' AND type = 'Service')
            OR (substr(oid, 1, 3) = 'SYS' AND type = 'System')
        ),
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE _gmv_db008_oid_sequences (
    object_type TEXT PRIMARY KEY,
    prefix TEXT NOT NULL UNIQUE,
    last_value INTEGER NOT NULL CHECK(last_value BETWEEN 0 AND 999999),
    CHECK(
        (prefix = 'COR' AND object_type = 'Core')
        OR (prefix = 'PER' AND object_type = 'Person')
        OR (prefix = 'PLG' AND object_type = 'Plugin')
        OR (prefix = 'RES' AND object_type = 'Resource')
        OR (prefix = 'SRV' AND object_type = 'Service')
        OR (prefix = 'SYS' AND object_type = 'System')
    )
);

INSERT INTO _gmv_db008_objects
SELECT oid, type, name, status, created_at, updated_at
FROM objects;

INSERT INTO _gmv_db008_oid_sequences
SELECT object_type, prefix, last_value
FROM oid_sequences;

DROP TABLE objects;
DROP TABLE oid_sequences;
ALTER TABLE _gmv_db008_objects RENAME TO objects;
ALTER TABLE _gmv_db008_oid_sequences RENAME TO oid_sequences;

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

CREATE TRIGGER gmv_resources_resource_type_insert
BEFORE INSERT ON resources
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.resource_oid AND type = 'Resource'
)
BEGIN
    SELECT RAISE(ABORT, 'resources.resource_oid must reference Resource Object');
END;

CREATE TRIGGER gmv_resources_resource_type_update
BEFORE UPDATE OF resource_oid ON resources
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.resource_oid AND type = 'Resource'
)
BEGIN
    SELECT RAISE(ABORT, 'resources.resource_oid must reference Resource Object');
END;

CREATE TRIGGER gmv_plugin_metadata_plugin_type_insert
BEFORE INSERT ON plugin_metadata
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.plugin_oid AND type = 'Plugin'
)
BEGIN
    SELECT RAISE(ABORT, 'plugin_metadata.plugin_oid must reference Plugin Object');
END;

CREATE TRIGGER gmv_plugin_metadata_plugin_type_update
BEFORE UPDATE OF plugin_oid ON plugin_metadata
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.plugin_oid AND type = 'Plugin'
)
BEGIN
    SELECT RAISE(ABORT, 'plugin_metadata.plugin_oid must reference Plugin Object');
END;

CREATE TRIGGER gmv_plugin_services_plugin_type_insert
BEFORE INSERT ON plugin_services
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.plugin_oid AND type = 'Plugin'
)
BEGIN
    SELECT RAISE(ABORT, 'plugin_services.plugin_oid must reference Plugin Object');
END;

CREATE TRIGGER gmv_plugin_services_plugin_type_update
BEFORE UPDATE OF plugin_oid ON plugin_services
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.plugin_oid AND type = 'Plugin'
)
BEGIN
    SELECT RAISE(ABORT, 'plugin_services.plugin_oid must reference Plugin Object');
END;

CREATE TRIGGER gmv_plugin_services_service_type_insert
BEFORE INSERT ON plugin_services
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.service_oid AND type = 'Service'
)
BEGIN
    SELECT RAISE(ABORT, 'plugin_services.service_oid must reference Service Object');
END;

CREATE TRIGGER gmv_plugin_services_service_type_update
BEFORE UPDATE OF service_oid ON plugin_services
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.service_oid AND type = 'Service'
)
BEGIN
    SELECT RAISE(ABORT, 'plugin_services.service_oid must reference Service Object');
END;

CREATE TRIGGER gmv_service_runs_service_type_insert
BEFORE INSERT ON service_runs
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.service_oid AND type = 'Service'
)
BEGIN
    SELECT RAISE(ABORT, 'service_runs.service_oid must reference Service Object');
END;

CREATE TRIGGER gmv_service_runs_service_type_update
BEFORE UPDATE OF service_oid ON service_runs
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.service_oid AND type = 'Service'
)
BEGIN
    SELECT RAISE(ABORT, 'service_runs.service_oid must reference Service Object');
END;

CREATE TRIGGER gmv_import_queue_resource_type_insert
BEFORE INSERT ON import_queue
FOR EACH ROW
WHEN NEW.resource_oid IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.resource_oid AND type = 'Resource'
)
BEGIN
    SELECT RAISE(ABORT, 'import_queue.resource_oid must reference Resource Object');
END;

CREATE TRIGGER gmv_import_queue_resource_type_update
BEFORE UPDATE OF resource_oid ON import_queue
FOR EACH ROW
WHEN NEW.resource_oid IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM objects WHERE oid = NEW.resource_oid AND type = 'Resource'
)
BEGIN
    SELECT RAISE(ABORT, 'import_queue.resource_oid must reference Resource Object');
END;

CREATE TEMP TABLE _gmv_db008_fk_guard (
    valid INTEGER NOT NULL CHECK(valid = 1)
);

INSERT INTO _gmv_db008_fk_guard(valid)
SELECT CASE
    WHEN EXISTS (SELECT 1 FROM pragma_foreign_key_check)
    THEN 0
    ELSE 1
END;

DROP TABLE _gmv_db008_fk_guard;
DROP TABLE _gmv_db008_preflight_guard;
DROP TABLE _gmv_db008_connection_guard;

PRAGMA user_version = 8;
COMMIT;
PRAGMA foreign_keys = ON;
