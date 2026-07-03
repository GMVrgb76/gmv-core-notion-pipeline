PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE objects (
    oid TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT,
    updated_at TEXT
);
INSERT INTO objects VALUES('PER-000001','Person','Giacomo Marco Valerio','active','2026-07-02T12:18:17','2026-07-02T12:18:17');
INSERT INTO objects VALUES('SYS-000001','System','GMV OS','active','2026-07-03T12:07:02','2026-07-03T12:07:02');
INSERT INTO objects VALUES('COR-000001','Core','GMV Core','active','2026-07-03T12:07:02','2026-07-03T12:07:02');
INSERT INTO objects VALUES('SRV-000001','Service','Knowledge Engine','active','2026-07-03T12:07:02','2026-07-03T12:07:02');
INSERT INTO objects VALUES('SRV-000002','Service','Morning Brief','active','2026-07-03T12:07:02','2026-07-03T12:07:02');
INSERT INTO objects VALUES('SRV-000003','Service','Daily Log','active','2026-07-03T12:07:02','2026-07-03T12:07:02');
INSERT INTO objects VALUES('SRV-000004','Service','Market Engine','active','2026-07-03T12:07:02','2026-07-03T12:07:02');
INSERT INTO objects VALUES('PLG-000001','Plugin','Core','active','2026-07-03T12:10:25','2026-07-03T12:10:25');
INSERT INTO objects VALUES('PLG-000002','Plugin','Area35','active','2026-07-03T12:10:25','2026-07-03 10:27:12');
INSERT INTO objects VALUES('PLG-000003','Plugin','Real Estate','active','2026-07-03T12:10:25','2026-07-03T12:10:25');
INSERT INTO objects VALUES('PLG-000004','Plugin','Communication','active','2026-07-03T12:10:25','2026-07-03T12:10:25');
INSERT INTO objects VALUES('RES-000001','Resource','09_OBJECT_SYSTEM.md','active','2026-07-03T12:44:03','2026-07-03T12:44:03');
CREATE TABLE engine_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engine TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT
, duration_seconds REAL, command TEXT, stdout_path TEXT, stderr_path TEXT);
INSERT INTO engine_runs VALUES(1,'knowledge_engine','2026-07-02T12:18:17','OK','Knowledge Engine V0 executed. GMV.db initialized. First persistent OID verified: PER-000001.',NULL,NULL,NULL,NULL);
INSERT INTO engine_runs VALUES(2,'daily_log','2026-07-02T12:30:13','OK','daily_log bridge run completed with status OK, return code 0',0.07037000000000000199,'/Users/giacomomarcovalerio/.gmv_scripts/genera_daily_log.sh','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/bridge/2026_07_02_123013_daily_log.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/bridge/2026_07_02_123013_daily_log.err.log');
INSERT INTO engine_runs VALUES(3,'daily_log','2026-07-02T12:31:42','OK','daily_log compatibility run completed with status OK, return code 0',0.07299700000000000633,'/Users/giacomomarcovalerio/.gmv_scripts/genera_daily_log.sh','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_02_123142_daily_log.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_02_123142_daily_log.err.log');
INSERT INTO engine_runs VALUES(4,'morning_brief','2026-07-03T11:35:55','OK','morning_brief compatibility run completed with status OK, return code 0',3.849527000000000143,'/Users/giacomomarcovalerio/.gmv_scripts/genera_morning_brief.sh','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_113555_morning_brief.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_113555_morning_brief.err.log');
INSERT INTO engine_runs VALUES(5,'market_engine','2026-07-03T11:43:23','OK','market_engine compatibility run completed with status OK, return code 0',0.02829399999999999971,'python3 /Users/giacomomarcovalerio/Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/99_SYSTEM/02_SERVICES/RealEstate/market_engine.py','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_114323_market_engine.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_114323_market_engine.err.log');
INSERT INTO engine_runs VALUES(6,'daily_log','2026-07-03T12:17:55','OK','daily_log compatibility run completed with status OK, return code 0',0.08813699999999999312,'/Users/giacomomarcovalerio/.gmv_scripts/genera_daily_log.sh','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_121755_daily_log.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_121755_daily_log.err.log');
INSERT INTO engine_runs VALUES(7,'knowledge_engine','2026-07-03T12:19:31','OK','Knowledge Engine V0 executed. GMV.db initialized. First persistent OID verified: PER-000001.',NULL,NULL,NULL,NULL);
CREATE TABLE timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oid TEXT NOT NULL,
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    source TEXT
);
INSERT INTO timeline VALUES(1,'PER-000001','2026-07-02T12:18:17','system_event','Knowledge Engine V0 initialized from former Apprentice concept.','knowledge_engine.py');
INSERT INTO timeline VALUES(2,'SYS-000001','2026-07-02T12:30:13','engine_run','daily_log bridge run completed with status OK, return code 0','gmv_bridge.py');
INSERT INTO timeline VALUES(3,'SYS-000001','2026-07-02T12:31:42','engine_run','daily_log compatibility run completed with status OK, return code 0','gmv_compatibility.py');
INSERT INTO timeline VALUES(4,'SYS-000001','2026-07-03T11:35:55','engine_run','morning_brief compatibility run completed with status OK, return code 0','gmv_compatibility.py');
INSERT INTO timeline VALUES(5,'SYS-000001','2026-07-03T11:43:23','engine_run','market_engine compatibility run completed with status OK, return code 0','gmv_compatibility.py');
INSERT INTO timeline VALUES(6,'SYS-000001','2026-07-03T12:17:55','engine_run','daily_log compatibility run completed with status OK, return code 0','gmv_compatibility.py');
INSERT INTO timeline VALUES(7,'PER-000001','2026-07-03T12:19:31','system_event','Knowledge Engine V0 initialized from former Apprentice concept.','knowledge_engine.py');
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
INSERT INTO engines VALUES('ENG-000001','Knowledge Engine','Cognitive','0.1','active',0,'/Users/giacomomarcovalerio/.gmv_core/01_RUNTIME/knowledge_engine.py','Core knowledge acquisition engine','2026-07-03T11:41:51','2026-07-03T11:41:51');
INSERT INTO engines VALUES('ENG-000002','Morning Brief','Communication','1.x','active',1,'/Users/giacomomarcovalerio/.gmv_core/12_SCHEDULER/run_morning_brief_compatibility.sh','Compatibility wrapper for Morning Brief','2026-07-03T11:41:51','2026-07-03T11:41:51');
INSERT INTO engines VALUES('ENG-000003','Daily Log','Communication','1.x','active',1,'/Users/giacomomarcovalerio/.gmv_core/12_SCHEDULER/run_daily_log_compatibility.sh','Compatibility wrapper for Daily Log','2026-07-03T11:41:51','2026-07-03T11:41:51');
INSERT INTO engines VALUES('ENG-000004','Market Engine','Domain','1.x','active',1,'/Users/giacomomarcovalerio/.gmv_core/12_SCHEDULER/run_market_engine_compatibility.sh','Compatibility wrapper for Real Estate Market Engine','2026-07-03T11:41:51','2026-07-03 09:43:23');
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
INSERT INTO service_runs VALUES(1,'SRV-000001','Knowledge Engine','2026-07-02T12:18:17','OK',NULL,NULL,NULL,NULL,'Knowledge Engine V0 executed. GMV.db initialized. First persistent OID verified: PER-000001.');
INSERT INTO service_runs VALUES(2,'SRV-000003','Daily Log','2026-07-02T12:30:13','OK',0.07037000000000000199,'/Users/giacomomarcovalerio/.gmv_scripts/genera_daily_log.sh','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/bridge/2026_07_02_123013_daily_log.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/bridge/2026_07_02_123013_daily_log.err.log','daily_log bridge run completed with status OK, return code 0');
INSERT INTO service_runs VALUES(3,'SRV-000003','Daily Log','2026-07-02T12:31:42','OK',0.07299700000000000633,'/Users/giacomomarcovalerio/.gmv_scripts/genera_daily_log.sh','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_02_123142_daily_log.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_02_123142_daily_log.err.log','daily_log compatibility run completed with status OK, return code 0');
INSERT INTO service_runs VALUES(4,'SRV-000002','Morning Brief','2026-07-03T11:35:55','OK',3.849527000000000143,'/Users/giacomomarcovalerio/.gmv_scripts/genera_morning_brief.sh','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_113555_morning_brief.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_113555_morning_brief.err.log','morning_brief compatibility run completed with status OK, return code 0');
INSERT INTO service_runs VALUES(5,'SRV-000004','Market Engine','2026-07-03T11:43:23','OK',0.02829399999999999971,'python3 /Users/giacomomarcovalerio/Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/99_SYSTEM/02_SERVICES/RealEstate/market_engine.py','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_114323_market_engine.out.log','/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/2026_07_03_114323_market_engine.err.log','market_engine compatibility run completed with status OK, return code 0');
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oid TEXT NOT NULL,
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    source TEXT
);
INSERT INTO events VALUES(1,'PER-000001','2026-07-02T12:18:17','system_event','Knowledge Engine V0 initialized from former Apprentice concept.','knowledge_engine.py');
INSERT INTO events VALUES(2,'SYS-000001','2026-07-02T12:30:13','engine_run','daily_log bridge run completed with status OK, return code 0','gmv_bridge.py');
INSERT INTO events VALUES(3,'SYS-000001','2026-07-02T12:31:42','engine_run','daily_log compatibility run completed with status OK, return code 0','gmv_compatibility.py');
INSERT INTO events VALUES(4,'SYS-000001','2026-07-03T11:35:55','engine_run','morning_brief compatibility run completed with status OK, return code 0','gmv_compatibility.py');
INSERT INTO events VALUES(5,'SYS-000001','2026-07-03T11:43:23','engine_run','market_engine compatibility run completed with status OK, return code 0','gmv_compatibility.py');
INSERT INTO events VALUES(6,'PLG-000001','2026-07-03T12:10:25','plugin_model_initialized','Plugin Model V0 initialized.','plugin_manager_bootstrap');
INSERT INTO events VALUES(7,'COR-000001','2026-07-03T12:39:18','relation_engine_initialized','Relation Engine V0 initialized.','relation_engine_v0');
INSERT INTO events VALUES(8,'RES-000001','2026-07-03T12:44:03','resource_imported','Resource imported: /Users/giacomomarcovalerio/.gmv_core/00_CONFIG/09_OBJECT_SYSTEM.md','import_service');
INSERT INTO events VALUES(9,'RES-000001','2026-07-03T17:40:05','resource_seen_again','Resource seen again: /Users/giacomomarcovalerio/.gmv_core/00_CONFIG/09_OBJECT_SYSTEM.md','import_service');
CREATE TABLE architecture_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    decision TEXT NOT NULL,
    consequence TEXT NOT NULL
);
INSERT INTO architecture_decisions VALUES(1,'2026-07-03 10:07:02','engines is deprecated','Services are represented as objects(type=Service).');
INSERT INTO architecture_decisions VALUES(2,'2026-07-03 10:07:02','engine_runs is deprecated','Service executions migrate to service_runs and events.');
INSERT INTO architecture_decisions VALUES(3,'2026-07-03 10:07:02','timeline is a view concept','The persistent table is events; timeline is derived by ordering events.');
INSERT INTO architecture_decisions VALUES(4,'2026-07-03 10:07:02','documents are objects','documents table may only store physical metadata, not primary identity.');
INSERT INTO architecture_decisions VALUES(5,'2026-07-03 10:07:02','status is derived','Current state should be computed from events and attributes where possible.');
INSERT INTO architecture_decisions VALUES(6,'2026-07-03 10:07:43','engines is deprecated','Services are represented as objects(type=Service).');
INSERT INTO architecture_decisions VALUES(7,'2026-07-03 10:07:43','engine_runs is deprecated','Service executions migrate to service_runs and events.');
INSERT INTO architecture_decisions VALUES(8,'2026-07-03 10:07:43','timeline is derived','Timeline is not a primary table; it is a view over events ordered by time.');
INSERT INTO architecture_decisions VALUES(9,'2026-07-03 10:07:43','documents are objects','Document identity belongs to objects(type=Document); document tables store only physical metadata.');
INSERT INTO architecture_decisions VALUES(10,'2026-07-03 10:07:43','attributes are limited','Simple scalar properties remain attributes; entities and places become relations.');
INSERT INTO architecture_decisions VALUES(11,'2026-07-03 10:07:43','events are primary','Events are the persistent historical unit; timeline is their ordered representation.');
INSERT INTO architecture_decisions VALUES(12,'2026-07-03 10:07:43','status is derived','Current status should be computed from events and attributes where possible.');
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
INSERT INTO plugin_metadata VALUES('PLG-000001','core','1.0','active','/Users/giacomomarcovalerio/.gmv_core','Core system plugin','2026-07-03T12:10:25','2026-07-03T12:10:25');
INSERT INTO plugin_metadata VALUES('PLG-000002','area35','0.1','active','','Area35 domain plugin','2026-07-03T12:10:25','2026-07-03 10:27:12');
INSERT INTO plugin_metadata VALUES('PLG-000003','real_estate','0.1','active','','Real estate domain plugin','2026-07-03T12:10:25','2026-07-03T12:10:25');
INSERT INTO plugin_metadata VALUES('PLG-000004','communication','0.1','active','','Morning Brief and Daily Log plugin','2026-07-03T12:10:25','2026-07-03T12:10:25');
CREATE TABLE plugin_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_oid TEXT NOT NULL,
    service_oid TEXT NOT NULL,
    role TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plugin_oid, service_oid)
);
INSERT INTO plugin_services VALUES(1,'PLG-000001','SRV-000001','knowledge','2026-07-03 10:10:25');
INSERT INTO plugin_services VALUES(2,'PLG-000003','SRV-000004','market','2026-07-03 10:10:25');
INSERT INTO plugin_services VALUES(3,'PLG-000004','SRV-000002','morning_brief','2026-07-03 10:10:25');
INSERT INTO plugin_services VALUES(4,'PLG-000004','SRV-000003','daily_log','2026-07-03 10:10:25');
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_oid TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_oid TEXT NOT NULL,
    created_at TEXT,
    source TEXT,
    UNIQUE(source_oid, relation_type, target_oid)
);
INSERT INTO relations VALUES(1,'SYS-000001','contains_core','COR-000001','2026-07-03T12:39:18','relation_engine_v0');
INSERT INTO relations VALUES(2,'COR-000001','manages_service','SRV-000001','2026-07-03T12:39:18','relation_engine_v0');
INSERT INTO relations VALUES(3,'COR-000001','manages_service','SRV-000002','2026-07-03T12:39:18','relation_engine_v0');
INSERT INTO relations VALUES(4,'COR-000001','manages_service','SRV-000003','2026-07-03T12:39:18','relation_engine_v0');
INSERT INTO relations VALUES(5,'COR-000001','manages_service','SRV-000004','2026-07-03T12:39:18','relation_engine_v0');
INSERT INTO relations VALUES(6,'PLG-000001','provides_service','SRV-000001','2026-07-03T12:39:18','relation_engine_v0');
INSERT INTO relations VALUES(7,'PLG-000003','provides_service','SRV-000004','2026-07-03T12:39:18','relation_engine_v0');
INSERT INTO relations VALUES(8,'PLG-000004','provides_service','SRV-000002','2026-07-03T12:39:18','relation_engine_v0');
INSERT INTO relations VALUES(9,'PLG-000004','provides_service','SRV-000003','2026-07-03T12:39:18','relation_engine_v0');
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
INSERT INTO resources VALUES('RES-000001','/Users/giacomomarcovalerio/.gmv_core/00_CONFIG/09_OBJECT_SYSTEM.md','09_OBJECT_SYSTEM.md','.md','text/markdown',5105,'957e7b8c0a4577f1da51b301225bfd4cb562de70686c4aa890818ffe2dde1c00','2026-07-03T12:44:03','active');
INSERT INTO sqlite_sequence VALUES('timeline',7);
INSERT INTO sqlite_sequence VALUES('engine_runs',7);
INSERT INTO sqlite_sequence VALUES('service_runs',5);
INSERT INTO sqlite_sequence VALUES('events',9);
INSERT INTO sqlite_sequence VALUES('architecture_decisions',12);
INSERT INTO sqlite_sequence VALUES('plugin_services',4);
INSERT INTO sqlite_sequence VALUES('relations',9);
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
COMMIT;
