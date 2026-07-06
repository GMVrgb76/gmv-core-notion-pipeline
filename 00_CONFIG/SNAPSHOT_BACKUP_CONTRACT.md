# Snapshot and Backup Contract

Status: S002-23 (`DOC-008`)

- **SQLite dump:** SQL text produced by legacy `gmv snapshot create`. It covers one
  database and is not proof of complete recovery.
- **Snapshot:** legacy CLI/category for database dumps and recovery inspection.
  The name alone grants no integrity, retention, or restore guarantee.
- **Verified full-system backup:** a `~/.gmv_backups/sets/BKP-*` recovery set with
  Recovery Policy v1 manifest, checksums, Git archive, consistent SQLite copy,
  Resource-reference report, private modes, verification, and audit evidence.

`gmv snapshot inspect` reads a backup manifest. `verify` checks declared files and
SQLite integrity. `restore-check` writes only to a new isolated target and refuses
an existing target. No command restores, overwrites, or promotes canonical state.

Rolling backups retain 90 days; Sprint/release/migration milestones are permanent.
Encryption is unsupported until key custody is approved. External Resources are
reported, not copied. A successful dump never substitutes for verified backup and
isolated restore evidence.
