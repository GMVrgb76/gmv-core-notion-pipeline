BEGIN IMMEDIATE;

ALTER TABLE events ADD COLUMN supersedes_event_id INTEGER;

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

PRAGMA user_version = 4;

COMMIT;
