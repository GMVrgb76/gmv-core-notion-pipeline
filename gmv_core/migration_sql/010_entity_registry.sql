-- Registered as ENTITY_REGISTRY_VERSION = 10 in gmv_core/migrations.py.
-- Deliberately NOT CURRENT_SCHEMA_VERSION and NOT in SUPPORTED_SCHEMA_VERSIONS
-- -- same rationale as migration 009: the crawler subsystem that owns these
-- tables does not exist yet, so no caller of migrate(db) without an
-- explicit target_version=10 is affected.
--
-- Purpose: crawler spec §11-§12 (Entity resolution / GMV ID) --
-- ENTITY_REGISTRY with gmv_id/entity_type/canonical_name/aliases/status/
-- created_at, "never fuzzy-match -> automatic merge", gmv_id stable and
-- independent of the current name. §27's minimum-database table list
-- names `entities` and `entity_aliases` as two separate tables (not a
-- JSON blob on one row) -- followed here, not invented.
--
-- Identity deliberately NOT integrated with gmv_core's objects/OID
-- system (gmv_core/identity.py: PREFIX_TO_TYPE is a closed 6-value enum
-- -- Core/Person/Plugin/Resource/Service/System -- all infrastructure
-- bookkeeping concepts, not domain knowledge entities). Forcing ARTIST/
-- EXHIBITION/WORK/etc. into that enum would mean either one new OID
-- prefix per entity_type (doubling that already-fixed enum across
-- multiple migration files) or a single generic type Core does not have
-- today -- both a materially larger, riskier change than adding an
-- entity registry. gmv_id gets its own separate "GMV-" scheme instead,
-- visually similar to Core's OID style but mechanically independent.
--
-- gmv_id generation algorithm (UUIDv7? content-derived? sequential?) is
-- NOT decided by this migration -- the CHECK below only constrains shape
-- (GMV- prefix, non-trivial length), not a specific algorithm. That
-- decision belongs to whoever builds the entity-resolution engine
-- (a later, still-unbuilt step), matching this file's own schema-only
-- scope (no engine implementation here, same as migration 009).
--
-- entity_type is constrained to exactly the CORE- and DOMAIN-status
-- class_ids in 00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json (committed on
-- this branch), cross-checked by a dedicated test so the two files
-- cannot silently drift apart. ARTWORK is excluded (DEPRECATED,
-- superseded by WORK/ARTWORK_INSTANCE). SPONSOR and CONTRACT are also
-- excluded, deliberately, even though they are not DEPRECATED: that
-- registry's own governance rule says a CANDIDATE class_id "cannot
-- silently enter canonical (CORE/DOMAIN) vocabulary" -- SPONSOR/CONTRACT
-- are status=CANDIDATE there (SPONSOR: coded but unit-test-only
-- coverage, never validated on real data; CONTRACT: never produced in
-- any real run). Accepting them here, in a registry meant to hold
-- confirmed entities from real crawls, would be exactly the silent
-- CANDIDATE promotion that rule forbids -- caught by review in an
-- earlier version of this CHECK, which filtered only "not DEPRECATED"
-- instead of "CORE or DOMAIN".

BEGIN IMMEDIATE;

CREATE TABLE entities (
    gmv_id TEXT PRIMARY KEY
        CHECK(gmv_id GLOB 'GMV-*' AND length(gmv_id) > length('GMV-')),
    entity_type TEXT NOT NULL
        CHECK(entity_type IN (
            'PERSON', 'ORGANIZATION', 'INSTITUTION', 'PLACE', 'EVENT', 'DOCUMENT',
            'ARTIST', 'EXHIBITION', 'PROJECT', 'COLLECTION', 'WORK', 'ARTWORK_INSTANCE'
        )),
    canonical_name TEXT NOT NULL,
    -- No uniqueness constraint on (entity_type, canonical_name):
    -- homonymous entities (two different real PERSONs sharing a name)
    -- are a real, expected case the crawler spec treats as an audit
    -- finding to surface ("entita omonime" in the base pre-plan's audit
    -- list), not a condition a schema constraint should silently block.
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK(status IN ('ACTIVE', 'MERGE_CANDIDATE', 'MERGED')),
    merged_into TEXT
        REFERENCES entities(gmv_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    created_at TEXT NOT NULL
);

CREATE INDEX entities_entity_type_idx ON entities(entity_type);
CREATE INDEX entities_status_idx ON entities(status);
CREATE INDEX entities_merged_into_idx ON entities(merged_into);

-- UNIQUE(entity_gmv_id, alias) is case-sensitive (SQLite's default TEXT
-- comparison) and scoped per-entity only: "F. Garibaldi" and
-- "f. garibaldi" are distinct rows for the same entity, and the same
-- alias string is free to be reused across different entities. No
-- normalization happens here -- that is application-layer work for
-- whoever writes to this table, not decided by this schema.
CREATE TABLE entity_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_gmv_id TEXT NOT NULL
        REFERENCES entities(gmv_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    alias TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE(entity_gmv_id, alias)
);

CREATE INDEX entity_aliases_entity_gmv_id_idx ON entity_aliases(entity_gmv_id);

-- "Never fuzzy-match -> automatic merge" made structural, not just
-- discipline: status=MERGED must always carry the confirmed successor;
-- any other status must never carry a stale/dangling merged_into. Both
-- INSERT and UPDATE are guarded, and UPDATE watches both columns
-- together -- same pattern as
-- gmv_crawler_source_registry_deleted_at_required_insert/update in
-- 009_crawler_source_registry.sql, after review found a single-trigger,
-- single-column version of that guard was bypassable.
CREATE TRIGGER gmv_entities_merged_into_required_insert
BEFORE INSERT ON entities
FOR EACH ROW
WHEN
    (NEW.status = 'MERGED' AND NEW.merged_into IS NULL)
    OR (NEW.status != 'MERGED' AND NEW.merged_into IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'entities.merged_into must be set if and only if status=MERGED');
END;

CREATE TRIGGER gmv_entities_merged_into_required_update
BEFORE UPDATE OF status, merged_into ON entities
FOR EACH ROW
WHEN
    (NEW.status = 'MERGED' AND NEW.merged_into IS NULL)
    OR (NEW.status != 'MERGED' AND NEW.merged_into IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'entities.merged_into must be set if and only if status=MERGED');
END;

CREATE TRIGGER gmv_entities_merged_into_not_self_insert
BEFORE INSERT ON entities
FOR EACH ROW
WHEN NEW.merged_into = NEW.gmv_id
BEGIN
    SELECT RAISE(ABORT, 'entities.merged_into must not reference its own gmv_id');
END;

CREATE TRIGGER gmv_entities_merged_into_not_self_update
BEFORE UPDATE OF merged_into ON entities
FOR EACH ROW
WHEN NEW.merged_into = NEW.gmv_id
BEGIN
    SELECT RAISE(ABORT, 'entities.merged_into must not reference its own gmv_id');
END;

-- Blocks both indirect cycles (A merged_into B, then B merged_into A --
-- reproduced and confirmed by review: neither the self-reference guard
-- above nor anything else caught this) and multi-hop chains (A -> B ->
-- C): merged_into may only point at an entity that is NOT itself
-- currently MERGED. This forces every merge to resolve in one hop, to a
-- survivor that is still ACTIVE/MERGE_CANDIDATE at write time --
-- sufficient for this schema-only step without deciding a resolution
-- algorithm for chains.
CREATE TRIGGER gmv_entities_merged_into_not_already_merged_insert
BEFORE INSERT ON entities
FOR EACH ROW
WHEN NEW.merged_into IS NOT NULL AND EXISTS (
    SELECT 1 FROM entities WHERE gmv_id = NEW.merged_into AND status = 'MERGED'
)
BEGIN
    SELECT RAISE(ABORT, 'entities.merged_into must reference a currently non-MERGED entity');
END;

CREATE TRIGGER gmv_entities_merged_into_not_already_merged_update
BEFORE UPDATE OF merged_into ON entities
FOR EACH ROW
WHEN NEW.merged_into IS NOT NULL AND EXISTS (
    SELECT 1 FROM entities WHERE gmv_id = NEW.merged_into AND status = 'MERGED'
)
BEGIN
    SELECT RAISE(ABORT, 'entities.merged_into must reference a currently non-MERGED entity');
END;

PRAGMA user_version = 10;

COMMIT;
