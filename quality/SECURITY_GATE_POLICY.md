# GMV Security Gate Policy

Status: S002-16 (`SEC-010`)

The release gate is `scripts/quality_gate.sh`. It must run tests, Ruff security
rules, dependency consistency, runtime-data policy, secret detection, whitespace,
and Git diff validation. A nonzero result blocks release.

Exceptions require an exact rule/path/finding, owner, reason, compensating
control, and expiry. Expired or broadened exceptions fail review. Baselines may
record only reviewed false positives; they may never absorb a finding merely to
pass CI. Plugin capability enforcement remains deferred to `ARC-007`.

Current exception ownership is recorded in `quality/LEGACY_EXCEPTIONS.md`.
Before every release the Quality Owner must confirm that its expiry statements
are future-dated or explicitly carried by an approved closeout. Unsafe subprocess,
credential, protected-runtime-path, broken dependency, and expired-exception
fixtures must remain negative tests.

Release requires zero unexplained findings, no protected runtime files in Git,
no broken requirements, and no silent scanner/baseline update.

## Quality floor (diff-scoped)

`scripts/check_floor.py` compares the working tree with the merge-base with
`origin/main` and fails on: a new checker suppression (`noqa`, `type: ignore`),
a new test skip or xfail, a new silent `except ...: pass` handler, and a net drop
in the number of `test_*` functions. Existing debt is not touched. A single added
line may be accepted with `gmv-floor-ok: <reason>` on that line (a non-empty
reason is mandatory and reviewed in the diff); a deliberate test removal needs
`--allow-test-removal`. Without `origin/main` the check prints `FLOOR|SKIP` and
passes.

The check is run by hand (`python scripts/check_floor.py`) and is not yet part of
`scripts/quality_gate.sh`. To enforce it in the gate, add it there and make CI
fetch full history (`fetch-depth: 0` in `.github/workflows/ci.yml`).
