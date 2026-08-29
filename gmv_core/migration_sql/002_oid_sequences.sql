BEGIN IMMEDIATE;

CREATE TABLE oid_sequences (
    object_type TEXT PRIMARY KEY,
    prefix TEXT NOT NULL UNIQUE,
    last_value INTEGER NOT NULL CHECK(last_value BETWEEN 0 AND 999999)
);

INSERT INTO oid_sequences (object_type, prefix, last_value)
SELECT 'Core', 'COR', COALESCE(MAX(CAST(SUBSTR(oid, 5) AS INTEGER)), 0)
FROM objects
WHERE type = 'Core' AND LENGTH(oid) = 10 AND SUBSTR(oid, 1, 4) = 'COR-'
  AND SUBSTR(oid, 5) NOT GLOB '*[^0-9]*';

INSERT INTO oid_sequences (object_type, prefix, last_value)
SELECT 'Person', 'PER', COALESCE(MAX(CAST(SUBSTR(oid, 5) AS INTEGER)), 0)
FROM objects
WHERE type = 'Person' AND LENGTH(oid) = 10 AND SUBSTR(oid, 1, 4) = 'PER-'
  AND SUBSTR(oid, 5) NOT GLOB '*[^0-9]*';

INSERT INTO oid_sequences (object_type, prefix, last_value)
SELECT 'Plugin', 'PLG', COALESCE(MAX(CAST(SUBSTR(oid, 5) AS INTEGER)), 0)
FROM objects
WHERE type = 'Plugin' AND LENGTH(oid) = 10 AND SUBSTR(oid, 1, 4) = 'PLG-'
  AND SUBSTR(oid, 5) NOT GLOB '*[^0-9]*';

INSERT INTO oid_sequences (object_type, prefix, last_value)
SELECT 'Resource', 'RES', COALESCE(MAX(CAST(SUBSTR(oid, 5) AS INTEGER)), 0)
FROM objects
WHERE type = 'Resource' AND LENGTH(oid) = 10 AND SUBSTR(oid, 1, 4) = 'RES-'
  AND SUBSTR(oid, 5) NOT GLOB '*[^0-9]*';

INSERT INTO oid_sequences (object_type, prefix, last_value)
SELECT 'Service', 'SRV', COALESCE(MAX(CAST(SUBSTR(oid, 5) AS INTEGER)), 0)
FROM objects
WHERE type = 'Service' AND LENGTH(oid) = 10 AND SUBSTR(oid, 1, 4) = 'SRV-'
  AND SUBSTR(oid, 5) NOT GLOB '*[^0-9]*';

INSERT INTO oid_sequences (object_type, prefix, last_value)
SELECT 'System', 'SYS', COALESCE(MAX(CAST(SUBSTR(oid, 5) AS INTEGER)), 0)
FROM objects
WHERE type = 'System' AND LENGTH(oid) = 10 AND SUBSTR(oid, 1, 4) = 'SYS-'
  AND SUBSTR(oid, 5) NOT GLOB '*[^0-9]*';

PRAGMA user_version = 2;

COMMIT;
