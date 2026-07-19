BEGIN IMMEDIATE;

CREATE TEMP TABLE _gmv_timeline_parity_guard (
    valid INTEGER NOT NULL CHECK(valid = 1)
);

INSERT INTO _gmv_timeline_parity_guard (valid)
SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM (
            SELECT oid, event_at, event_type, description, source,
                   COUNT(*) AS row_count
            FROM timeline
            GROUP BY oid, event_at, event_type, description, source
        ) AS timeline_rows
        LEFT JOIN (
            SELECT oid, event_at, event_type, description, source,
                   COUNT(*) AS row_count
            FROM events
            GROUP BY oid, event_at, event_type, description, source
        ) AS event_rows
          ON event_rows.oid IS timeline_rows.oid
         AND event_rows.event_at IS timeline_rows.event_at
         AND event_rows.event_type IS timeline_rows.event_type
         AND event_rows.description IS timeline_rows.description
         AND event_rows.source IS timeline_rows.source
        WHERE COALESCE(event_rows.row_count, 0) < timeline_rows.row_count
    )
    THEN 0
    ELSE 1
END;

DROP TABLE timeline;

CREATE VIEW timeline AS
SELECT id, oid, event_at, event_type, description, source
FROM events;

DROP TABLE _gmv_timeline_parity_guard;

PRAGMA user_version = 3;

COMMIT;
