# GMV Run Ledger MVP — Corrections

Applied against the first implementation draft. Severity:

- **BLOCKING** — the code does not satisfy the contract it implements.
- **DEFECT** — wrong behaviour in a reachable case.
- **WEAKNESS** — correct but fragile, slow, or misleading.

The corrected `gmv_run_ledger.py` is delivered in full. Changes to
`gmv_pipeline.py`, `gmv_recovery.py` and the tests are given as patches below.

---

## C-1 — BLOCKING — `RunLock.release()` destroys the B2 guarantee

```python
# draft
fcntl.flock(self.fd, fcntl.LOCK_UN)   # ← releases for children too
os.close(self.fd)
```

An `flock` is held by the **open file description**, not by the file
descriptor. Parent and inheriting children share one description. `LOCK_UN`
therefore releases the lock for every holder at once.

The whole point of B2 is that an orphaned child keeps the lock after the
wrapper dies. With `LOCK_UN` in `release()`, the moment the wrapper exits
normally the lock is gone even if a child is still writing into
`artifacts/` — and `tests/test_lock_inheritance.py` fails, because the
competing `acquire()` succeeds where the test asserts `LockUnavailable`.

**Fix:** `release()` closes the descriptor and nothing else. The kernel
releases the lock when the last descriptor referring to that description is
closed. No code path may ever call `LOCK_UN`.

This is the single most important correction: the draft's own B2 test would
have failed and could easily have been mistaken for a platform limitation.

---

## C-2 — DEFECT — `splitlines()` on ledger bytes

`bytes.splitlines()` breaks on `\r` as well as `\n`. A carriage return
reaching the file — from a hand-edit, a recovered fragment, or any writer
that is not this module — would split one record into two and be reported as
interior corruption, or worse, parse as two partial records.

**Fix:** `data.split(b"\n")`, with the trailing element treated as the
uncommitted tail. Record boundaries are then exactly what the writer
produced.

---

## C-3 — DEFECT — validation skipped whenever the tail was truncated

The draft returned early from `read_events` on a truncated final line,
**before** calling `validate_event_sequence`. A ledger with both a corrupt
interior record and a partial last line therefore replayed as clean, and the
corruption was only discovered after the repair had already appended
`LEDGER_REPAIRED`.

**Fix:** validate the committed prefix in both branches, before returning.

---

## C-4 / C-5 — WEAKNESS — quadratic replay

`append_event` re-read and re-parsed the entire ledger, then called
`refresh_state_cache`, which re-read it again. Every event therefore cost two
full passes: a Run with *n* events performs O(n²) work, and a Notion
extraction registering hundreds of artifacts is noticeably slow. The manifest
was likewise re-read and re-parsed on every append.

**Fix:** cache the manifest (immutable after `RUN_STARTED`) and cache the
replay keyed on file size, refreshing in place after each committed append.
The cache is bypassed whenever the lock is not held, so it can never mask
another writer's changes.

---

## C-6 — DEFECT — component identity recomputed per stage

`fingerprint()` called `git_dirty()` and `sha256_file(config)` at every
stage. Editing any file, or touching the config, while the pipeline ran
produced **different fingerprints inside a single Run**. Intra-run resume
(§35 Rule 2) compares the current fingerprint against the one recorded at
`STAGE_COMPLETED`, so this silently makes resume decisions on a moving
reference.

**Fix:** `RunIdentity.capture()` snapshots commit, dirty state and config
hash once, before the Run is created. All stage fingerprints derive from it.

---

## C-7 — DEFECT — artifact directory entry never fsynced

`register_artifact` fsynced the file but not its parent directory. A crash
between the two could leave a committed `ARTIFACT_REGISTERED` event pointing
at a file whose directory entry never reached disk.

Recovery would classify it `FILE_MISSING` — fail-closed, so not unsafe, but
it converts a recoverable Run into a rerun for no reason.

**Fix:** `fsync_file(path)` then `fsync_directory(path.parent)`. Also added:
`size_bytes` is now checked before hashing in `verify_artifact`, which turns
the common truncation case into a cheap `SIZE_MISMATCH` instead of a full
re-hash.

---

## C-8 — DEFECT — `SKIPPED` treated as an unsatisfied boundary

`build_report` collected only `COMPLETED` stages as candidate checkpoints.
The pipeline emits `STAGE_SKIPPED` for `10_EXTRACT` whenever it is invoked
with `--rows`. Recovery of such a Run therefore found no valid boundary at
`10_EXTRACT`, fell back to `resume_from = requested[0]`, and demanded
recomputation of every stage — including stages that had completed and
verified.

**Fix:** `SATISFIED_STAGE_STATES = {"COMPLETED", "SKIPPED"}`.
`evaluate_checkpoint` returns a valid projection for a skipped stage, and
the recovery report walks the requested stages in order.

---

## C-9 — DEFECT — a Run crashed before `RUN_STARTED` was unclassifiable

`RUN_TRANSITIONS` had no `CREATED → INTERRUPTED` edge. A crash in the window
between `RUN_CREATED` and `RUN_STARTED` left the Run in `CREATED` forever:
`gmv_recovery` only classifies `RUNNING`, and `RUN_STARTED` can no longer be
written by the dead process. The Run stays in `_active` permanently and
nothing can clear it except manual deletion.

**Fix:** add `("CREATED", "RUN_INTERRUPTED"): "INTERRUPTED"`, and classify
whenever the recorded state is non-terminal rather than only `RUNNING`.

**This is a contract change**, not only an implementation fix: §18 of
v0.1.2 must gain the same row.

---

## C-10 — WEAKNESS — substrate check inspected the wrong path

`verify_substrate` resolved only the *nearest existing ancestor*. If
`~/Dropbox/gmv/runs` did not yet exist, the sync-root comparison ran against
whichever ancestor happened to exist, and creation of the denied path could
succeed on the first invocation.

**Fix:** compare both the fully resolved intended path and the nearest
existing ancestor against the sync roots. Mount-type detection still uses the
existing ancestor, since an unborn path has no mount.

---

## C-11 — DEFECT — `_active` registered after the first events

§53 requires registration in `_active` on `RUN_CREATED`. The draft created
the symlink after `RUN_STARTED`. A crash in that window produced an
interrupted Run that `gmv_recovery` could never discover, since discovery
scans `_active` only (§40).

**Fix:** create and fsync the `_active` entry before acquiring the lock and
appending the first event.

---

## C-12 — BLOCKING — `20_ADAPT` records a fingerprint for code that never ran

```python
component = fingerprint(component="adapter_contract",
                        files=["adapter_notion.py"], ...)
...
shutil.copy2(rows_input, adapted)
```

The stage claims `adapter_notion.py` as its source set, but the work is done
by `shutil.copy2`. The recorded fingerprint asserts an identity that is
false, which is exactly what §34 exists to prevent: a later edit to
`adapter_notion.py` would invalidate resume for a stage that never used it,
and an edit to the copy logic in `gmv_pipeline.py` would not.

The accompanying prose says the stage should be `SKIPPED` when the current
extractor is used. The code does not do that.

**Fix — choose one, do not blend them:**

**Option A (recommended for the MVP).** `notion_extract.py` already emits the
normalized rows the validator consumes. Emit `STAGE_SKIPPED` for `20_ADAPT`
and let `30_AUDIT` consume the extract artifact directly. No copy, no
fictitious component, no duplicated 380 KB per Run.

```python
ledger.append_event(
    actor="gmv_pipeline",
    event_type="STAGE_SKIPPED",
    stage="20_ADAPT",
    reason="EXTRACTOR_EMITS_NORMALIZED_ROWS",
)
rows_artifact = extract_artifact          # consumed by 30_AUDIT
rows_path     = extract_path
```

With C-8 applied, recovery handles the skipped boundary correctly.

**Option B.** Keep the stage, but declare its true source set —
`["gmv_pipeline.py"]`, the module that performs the copy — and name the
component `pipeline_rows_adoption`. Honest, but it registers a second copy of
the same bytes for no analytical gain.

`adapter_notion.py` should be named as a source set only when it is actually
executed.

---

## C-13 — DEFECT — the pipeline returns 0 when the audit gate fires

`run_child(..., accepted_codes={0, 1})` correctly treats validator exit 1
(BLOCKER found) as a valid epistemic result rather than a crash. But `main()`
then returns 0, so a caller — `launchd`, a shell script, CI — cannot
distinguish "audit clean" from "audit found blockers".

**Fix:** return a distinct code. Suggested: `0` clean, `1` completed with
blockers, `2` pipeline failure.

```python
run_pipeline(...)
ledger.append_event(actor="gmv_pipeline", event_type="RUN_COMPLETED")
deactivate_run(ledger.manifest["run_id"], args.ledger_root)
return 1 if blocker_gate else 0
```

`run_pipeline` must return the gate result rather than discarding it.

---

## C-14 — WEAKNESS — `except Exception` around the whole pipeline

`main()` catches `Exception`, so `KeyboardInterrupt` and `SystemExit`
propagate and the Run is left `RUNNING` for recovery to classify. That is
the right split, but it is accidental rather than stated.

**Fix:** make it explicit in a comment, and add `finally: ledger.lock.release()`
— present in the draft, worth keeping deliberately, since it is what allows
`gmv_recovery` to inspect a Run whose wrapper failed cleanly.

Note the interaction with B2: if a child was started and is still alive, the
release is a no-op in practice, because the child still holds the
description.

---

## Patches

### `gmv_pipeline.py`

```diff
-from gmv_run_ledger import (LEDGER_ROOT, RunLedger, component_fingerprint,
-                            create_run, sha256_file)
+from gmv_run_ledger import (LEDGER_ROOT, RunIdentity, RunLedger,
+                            create_run, deactivate_run)

 def main() -> int:
     args = parse_args()
     repo = Path(__file__).resolve().parent
     config = args.config.resolve()
+
+    # C-6: snapshot code and config identity once, before anything runs.
+    identity = RunIdentity.capture(repo, config)

     ledger = create_run(
-        repo_root=repo,
+        identity=identity,
         requested_stages=STAGES,
         source_identity="area35",
         config_path=config,
         ...
     )

     try:
-        run_pipeline(ledger=ledger, repo=repo, config=config, args=args)
+        blocker_gate = run_pipeline(
+            ledger=ledger, identity=identity, repo=repo, args=args
+        )
         ledger.append_event(actor="gmv_pipeline", event_type="RUN_COMPLETED")
-        active = args.ledger_root.expanduser() / "_active" / ledger.manifest["run_id"]
-        active.unlink(missing_ok=True)
-        return 0
+        deactivate_run(ledger.manifest["run_id"], args.ledger_root)
+        return 1 if blocker_gate else 0   # C-13
```

Replace the `fingerprint()` helper with:

```python
def fingerprint(identity, *, component, files, stage):
    return identity.fingerprint(
        component_name=component,
        source_set=files,
        stage_contract_version=VERSIONS[stage],
    )
```

Replace the whole `20_ADAPT` block with Option A from C-12.

Have `run_pipeline` return `audit_code == 1`.

### `gmv_recovery.py`

```diff
-        state = ledger.recorded_state()
-        recorded = state["run_state"]
-
-        if recorded == "RUNNING":
+        recorded = ledger.recorded_state()["run_state"]
+
+        # C-9: classify any non-terminal recorded state, not only RUNNING.
+        if recorded in {"CREATED", "RUNNING"}:
             last_seq = ledger.replay().events[-1]["seq"]
             ledger.append_event(
                 actor="gmv_recovery",
                 event_type="RUN_INTERRUPTED",
                 observed={
-                    "recorded_state": "RUNNING",
+                    "recorded_state": recorded,
                     "last_committed_seq": last_seq,
                     "lock_acquired": True,
                     "prior_host": ledger.manifest.get("host"),
                 },
             )
-            state = ledger.recorded_state()
-            recorded = state["run_state"]
+            recorded = ledger.recorded_state()["run_state"]
```

And in `build_report`, replace the checkpoint walk:

```python
from gmv_run_ledger import SATISFIED_STAGE_STATES

checkpoints = {}
last_satisfied = None

for stage in requested:
    if stages.get(stage) not in SATISFIED_STAGE_STATES:   # C-8
        break
    projection = ledger.evaluate_checkpoint(stage)
    checkpoints[stage] = projection
    if not projection["valid"]:
        break
    last_satisfied = stage

if last_satisfied is None:
    resume_from = requested[0] if requested else None
else:
    index = requested.index(last_satisfied)
    resume_from = requested[index + 1] if index + 1 < len(requested) else None
```

Walking in requested order and stopping at the first unsatisfied boundary is
also more correct than the draft's `valid_completed[-1]`: a later valid stage
after an invalid earlier one must not be treated as a resume point.

### `tests/`

Two additions the draft's suite does not cover, both of which would have
caught real defects above:

```python
def test_release_does_not_unlock_for_children(self):
    """C-1 regression: release() must not issue LOCK_UN."""
    # See tests/test_lock_inheritance.py — it already asserts this.
    # Add the direct unit form: two RunLock objects on one path, where the
    # first releases while a child holds the inherited descriptor.

def test_truncated_tail_over_corrupt_interior(self):
    """C-3 regression."""
    # Append a malformed complete record, then a truncated final record.
    # replay() must raise LedgerCorrupt, not report a clean prefix.

def test_skipped_stage_is_a_satisfied_boundary(self):
    """C-8 regression."""
    # STAGE_SKIPPED on 10_EXTRACT, STAGE_COMPLETED on 20_ADAPT.
    # resume_from must be the stage after 20_ADAPT, not 10_EXTRACT.

def test_run_created_then_crash_is_classifiable(self):
    """C-9 regression."""
    # Ledger containing only RUN_CREATED must accept RUN_INTERRUPTED.
```

Also fix `test_completed_run_cannot_resume`: the illegal event uses
`"seq": 4` where the history has three events, and the whole setup is inside
the `assertRaises` block, so the assertion would pass even if
`reduce_recorded_state` were removed. Build the illegal event outside the
block and assert only on the reduction.

---

## Open, unimplemented

Not defects in the draft — deliberate gaps worth naming so they are not
mistaken for completeness.

1. **`--resume RUN_ID` does not exist.** The draft says so explicitly and is
   right to keep observation separate from execution. Until it exists, the
   Recovery Report is a verdict nobody acts on automatically.
2. **§10.1 migration path (M5)** is unimplemented. A `runs/` tree found on a
   denied substrate currently fails closed with no way out.
3. **`runs/index.jsonl`** is declared in §41 and never written. It is a MAY,
   but `deactivate_run` is the natural place to record terminal closure.
4. **Cross-run reuse (§46)** is unimplemented. Only intra-run resume is
   contemplated by the current code, which is correct for the MVP scope.

---

## Integration hardening applied in the operational repository

The installed version also closes issues found during the executable review:

1. `RunIdentity.capture()` now snapshots every dirty component source-set hash
   before Run creation. The delivered implementation captured commit, dirty
   state and config but still recalculated source hashes when each stage began.
2. Replay converts non-object JSON records and invalid component fingerprints
   into `LedgerCorrupt` instead of leaking `AttributeError`.
3. Recovery renders `LEDGER_CORRUPT` and `NOT_FOUND` reports safely, returns
   exit `2`, and never creates a missing Run as a side effect of inspection.
4. `_active` discovery rejects symlinks escaping the configured ledger root.
5. `deactivate_run()` fsyncs `_active` after removing a terminal Run entry.
6. The default `~/.gmv_core/runs` path is ignored and protected by the GMV
   runtime-data Git policy.
