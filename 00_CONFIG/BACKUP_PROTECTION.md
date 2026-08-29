# Backup and Inventory Protection

Status: S002-22 (`SEC-009`)

`~/.gmv_backups` is Restricted recovery data: directories are `0700`, files are
`0600`, manifests contain no credentials, and audit errors expose only exception
types. Rolling sets expire after 90 days only when another verified set remains.
Sprint, release, and migration milestones are permanent. Retention is dry-run by
default and mutation requires `--apply`.

Encryption is disabled and fails closed because key custody is not approved.
It may not be enabled until the Human Owner approves provider, key ownership,
rotation, escrow/recovery, and key-loss behavior. Resource paths remain protected
metadata inside restricted manifests and are never reinjected automatically.
