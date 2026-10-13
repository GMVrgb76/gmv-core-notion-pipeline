---
name: test-driven-development
description: Red-green-refactor and Prove-It bug workflow for GMV Core Python code, using the repository's real test commands and isolation fixtures. Use when implementing logic, fixing a bug, or changing behavior.
---

# Test-Driven Development (GMV)

Adapted from addyosmani/agent-skills (MIT). Authority: yields to
`gmv-core-safety`, `gmv-evidence-pipeline` and `quality/SECURITY_GATE_POLICY.md`.

## Real commands (verified 2026-10-13)

`python` on the shell PATH has no pytest or ruff. Use the project venv of the main
checkout, and set `GMV_CORE_ROOT` when working in a worktree (as CI does):

```
PY=~/.gmv_core/.venv/bin/python
GMV_CORE_ROOT="$(git rev-parse --show-toplevel)" PYTHONDONTWRITEBYTECODE=1 \
  $PY -m pytest -q -p no:cacheprovider tests/test_x.py::test_name   # narrowest first
$PY -m pytest -q -p no:cacheprovider tests/security                  # then the module
./scripts/quality_gate.sh                                            # before handing over
```

Run the narrowest test first, then the related module. Run the whole suite only
before handing over or when asked; never run full pipelines against live data.
Count tests before and after: the number must not drop (see `scripts/check_floor.py`).

## Cycle

1. **RED** - write one failing test that states the behavior. Run it and read the
   failure; a test that never failed proves nothing.
2. **GREEN** - the smallest code that passes. No extras.
3. **REFACTOR** - only with all tests green; rerun after each step.

**Prove-It for bugs**: reproduce with a failing test first, then fix, then show the
test passes and the neighbors still do. No test, no fix claim.

## GMV-specific rules

- `tests/conftest.py` gives every test a disposable `HOME`/`GMV_HOME` and a live
  database guard. Never bypass it, never point a test at `09_DATABASE/GMV.db`, `runs/`
  or other protected runtime paths.
- Prefer real implementations and tmp_path fixtures over mocks. Mock only the
  network boundary (Ollama, Notion, Dropbox) and assert on the request, not the call count.
- Test state and outputs (schema, verification fields, provenance preserved), not
  internals. For consolidation or precedence logic, test the precedence table.
- Never add `noqa`, `type: ignore`, a skip/xfail or an `except: pass` to get green.
  If truly needed, justify it on the line with `gmv-floor-ok: <reason>`.
- Name tests by behavior (`test_hash_mismatch_is_not_completed`); one concept each.

## Verification

- [ ] Test failed first for the right reason
- [ ] Narrowest test, then module, then gate output shown (not claimed)
- [ ] Test count did not drop; no new suppressions or skips
