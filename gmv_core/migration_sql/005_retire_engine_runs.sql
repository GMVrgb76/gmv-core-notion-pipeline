BEGIN IMMEDIATE;

CREATE TEMP TABLE _gmv_engine_service_identity (
    engine TEXT PRIMARY KEY,
    service_oid TEXT NOT NULL,
    service_name TEXT NOT NULL
);

INSERT INTO _gmv_engine_service_identity (engine, service_oid, service_name)
VALUES
    ('knowledge_engine', 'SRV-000001', 'Knowledge Engine'),
    ('morning_brief', 'SRV-000002', 'Morning Brief'),
    ('daily_log', 'SRV-000003', 'Daily Log'),
    ('market_engine', 'SRV-000004', 'Market Engine');

CREATE TEMP TABLE _gmv_engine_runs_retirement_guard (
    valid INTEGER NOT NULL CHECK(valid = 1)
);

INSERT INTO _gmv_engine_runs_retirement_guard (valid)
SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM engine_runs AS er
        LEFT JOIN _gmv_engine_service_identity AS identity
          ON identity.engine = er.engine
        WHERE identity.engine IS NULL
          AND NOT (
              er.id = 23
              AND gmv_engine_run_content_sha256(
                  er.engine,
                  er.run_at,
                  er.status,
                  er.duration_seconds,
                  er.command,
                  er.stdout_path,
                  er.stderr_path,
                  er.summary
              ) = '14cb0faf3f2db75eb4a428eddc9dfadb2d1c02439218fb8667432b2fa0f66a8d'
          )
    )
    OR EXISTS (
        SELECT 1
        FROM (
            SELECT identity.service_oid,
                   identity.service_name,
                   er.run_at,
                   er.status,
                   er.duration_seconds,
                   er.command,
                   er.stdout_path,
                   er.stderr_path,
                   er.summary,
                   COUNT(*) AS row_count
            FROM engine_runs AS er
            JOIN _gmv_engine_service_identity AS identity
              ON identity.engine = er.engine
            GROUP BY identity.service_oid,
                     identity.service_name,
                     er.run_at,
                     er.status,
                     er.duration_seconds,
                     er.command,
                     er.stdout_path,
                     er.stderr_path,
                     er.summary
        ) AS engine_rows
        LEFT JOIN (
            SELECT service_oid,
                   service_name,
                   run_at,
                   status,
                   duration_seconds,
                   command,
                   stdout_path,
                   stderr_path,
                   summary,
                   COUNT(*) AS row_count
            FROM service_runs
            GROUP BY service_oid,
                     service_name,
                     run_at,
                     status,
                     duration_seconds,
                     command,
                     stdout_path,
                     stderr_path,
                     summary
        ) AS service_rows
          ON service_rows.service_oid IS engine_rows.service_oid
         AND service_rows.service_name IS engine_rows.service_name
         AND service_rows.run_at IS engine_rows.run_at
         AND service_rows.status IS engine_rows.status
         AND service_rows.duration_seconds IS engine_rows.duration_seconds
         AND service_rows.command IS engine_rows.command
         AND service_rows.stdout_path IS engine_rows.stdout_path
         AND service_rows.stderr_path IS engine_rows.stderr_path
         AND service_rows.summary IS engine_rows.summary
        WHERE COALESCE(service_rows.row_count, 0) < engine_rows.row_count
    )
    THEN 0
    ELSE 1
END;

DROP TABLE engine_runs;

DROP TABLE _gmv_engine_runs_retirement_guard;
DROP TABLE _gmv_engine_service_identity;

PRAGMA user_version = 5;

COMMIT;
