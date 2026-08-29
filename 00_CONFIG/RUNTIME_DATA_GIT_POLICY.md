# GMV Runtime Data and Git Policy

Status: Enforced Sprint 002 policy (`SEC-004`)

## Purpose

Git contains deterministic source, configuration, sanitized fixtures, and
approved governance. It must not become a store for live databases, operational
state, logs, generated reports, snapshots, credentials, or private filesystem
locations. Runtime files remain governed by
`00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md` and future backup/retention controls.

## Sensitivity classes

| Class | Examples | Git rule | Owner |
|---|---|---|---|
| Public | Approved public documentation | Allowed after review | Governance owner |
| Internal | Source, configuration, architecture, sanitized fixtures | Allowed after review and policy scan | Repository maintainer |
| Confidential | Operational logs, reports, inventories, state, personal paths | Prohibited unless a specific redacted evidence exception is approved | Producing Service owner / Project Owner |
| Restricted | Live databases, credentials, tokens, private keys, recovery secrets | Prohibited | Security owner / Project Owner |

Classification follows content, not filename. A Markdown, JSON, or SQL file that
contains runtime or personal data remains Confidential or Restricted.

## Protected runtime paths

The following repository-root paths must have no tracked files:

- `.DS_Store`;
- `02_INDEXES/`;
- `03_STATE/`;
- `04_LOGS/`;
- `05_OUTPUT/`;
- `06_CACHE/`;
- `07_IMPORT/`;
- `08_BACKUP_LOCAL/`;
- `09_DATABASE/`.

Sanitized fixtures under `tests/fixtures/` remain tracked. They must contain no
live rows, credentials, private paths, or external message/document bodies.

## Enforcement

`scripts/check_runtime_git_policy.py` examines the current Git index. It fails
when a protected runtime path is tracked or tracked readable content contains a
high-confidence credential/private-key pattern or a personal absolute path. The
quality gate runs this scanner before the existing `detect-secrets` baseline
check. Test-only scanner examples must carry the literal marker
`gmv-policy-test-fixture`; the marker is not valid as a production exception.

The scanner does not inspect ignored runtime data, Git history, external
Resources, or untracked documents. Those boundaries are deliberate: ignored
runtime data belongs to operational security/retention, while every untracked
document must pass this gate before it can be proposed for staging.

Exceptions require a documented owner, exact path/finding, justification,
expiration date, and compensating control. Updating a baseline merely to make a
gate pass is forbidden.

## Historical exposure report

Git history before commit `6bd8a8c` contains the live `09_DATABASE/GMV.db`,
operational logs, state/index files, generated reports/inventories, compatibility
outputs, a SQLite snapshot, and `.DS_Store`. S002-13 removed those paths from the
current index without deleting local files or rewriting history. Their historical
presence is a Confidential/Restricted exposure and must be considered when
sharing or publishing any clone.

The secret baseline previously referenced a high-entropy hash in the tracked
legacy SQLite snapshot. That stale entry is removed by S002-14 because the file
is no longer in the current index. The `legacy_inventory.py` extension-list
finding and three scheduler SHA-256 source-integrity pins remain explicitly
reviewed in `quality/LEGACY_EXCEPTIONS.md`; they are not permission to add
further findings.

No history repair is performed in Sprint 002. Any future history rewrite must
have explicit Project Owner approval, recipient/remote coordination, a preserved
evidence record, credential-impact analysis, rollback, and post-rewrite clone
verification. Until then, access to repository history must be treated as access
to historical runtime data.

## Release gate

A change passes this policy only when:

1. the runtime-data scanner returns zero;
2. `detect-secrets` reports no finding beyond the reviewed baseline;
3. protected runtime paths have no tracked entries;
4. sanitized fixtures remain tracked and pass tests;
5. any historical exposure remains explicitly reported rather than concealed;
6. no database, runtime artifact, or external Resource was changed by validation.
