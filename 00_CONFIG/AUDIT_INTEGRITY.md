# Operational Audit Integrity

Status: S002-17 (`SEC-012`)

Future backup operations write `backup_events.v2.jsonl` as locked, mode `0600`,
hash-chained JSONL. Sequence, previous hash, and record hash detect modification,
reordering, insertion, malformed partial writes, and non-tail deletion. Legacy
`backup_events.jsonl` is preserved as evidence and is not rewritten.

Without an independently stored anchor, deletion of the final valid record cannot
be detected. Canonical Event append-only enforcement remains deferred to
`DB-004`/`ARC-002`; this control never rewrites or substitutes canonical Events.
