# OpenCode Task 30 — a minimal, standalone backup for materialized Monads

**Status: DRAFT TASK — approved plan, not yet executed.**
**Correction to the plan's original premise, verified before writing this task: `backup_service.py`
does NOT currently back up `03_STATE/ombra/`. Read `create_backup()` in full
(`10_API/backup_service.py:184`) before starting — it only backs up `09_DATABASE/GMV.db` plus a
`git archive HEAD` of the repo, and its own manifest explicitly lists `"runtime", "cache",
"temporary outputs", "generated indexes"` as excluded categories. `gmv_monad_materializer.py`'s own
docstring citing "within secure_storage.py's/backup_service.py's perimeter" is a spec-level
declaration, not a description of code that exists today. Do not assume it does.**

## Why this task is scoped the way it is

`backup_service.py` is a careful, security-conscious module (file locking, atomic writes, audit
log, verify-before-finalize) backing a different real concern (the SQL database + git history).
Extending IT to also handle `03_STATE/ombra/` would mean changing its manifest schema and its
tested contract for an unrelated use case — risk not justified by today's volume (currently 1 real
Monad file). This task instead builds a small, SEPARATE, narrowly-scoped mechanism, reusing
primitives (not the whole module) that already exist.

## Hard constraints

1. **Do not modify `backup_service.py` or its manifest schema.** This is a new, separate script/
   function, not an extension of that module.
2. **Do not modify `gmv_monad_materializer.py`.** It stays exactly as it is — a pure render +
   atomic-write function with no knowledge of backup. The backup step is a separate, later action
   a caller takes, same separation of concerns this project already uses elsewhere (e.g.
   `project_public()` composing with but not being called BY `materialize_monad()`).
3. **Reuse `secure_storage.py`'s existing atomic-write primitive** for writing the backup copy
   itself, same as `gmv_monad_materializer.py` already does for the original — don't invent a
   second write mechanism.
4. **No SQL, no new dependency.** Destination is already decided, do not stop to ask or pick a
   different one: `Path.home() / ".gmv_backups" / "ombra"` — the same root
   `backup_service.py::main()`'s own CLI default already uses (`Path.home() / ".gmv_backups"`,
   confirmed this session at `10_API/backup_service.py:436`), under its own clearly-separate
   `ombra/` subfolder so it can never collide with `backup_service.py`'s own `sets/` structure.

## Steps

1. `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md`'s real entry for `03_STATE/ombra/` (already read this
   session, quoted here so you don't need to re-derive it): "Full-system backup after S002-20;
   never Git... Already covered by `03_STATE/`'s existing 'Live state' classification... called out
   separately only because a caller-supplied `target_path` needed a concrete default." This
   confirms no conflicting convention exists yet for this specific directory — proceed with this
   task's design (step 4's destination, below) as the first real implementation of that general
   policy for this specific directory. Do not stop to ask about this — it is resolved.
2. Write a small function in a new file, `10_API/gmv_monad_backup.py` (fixed location, do not pick
   a different one) that: lists every `.md` file under `03_STATE/ombra/`, copies each to the
   destination from step 4 below, preserving the `gmv_id`-derived filename, using
   `secure_storage.atomic_write_text()` (read the source file, write it via that function to the
   destination) rather than a raw `shutil.copy`.
3. A CLI entry point: a plain `if __name__ == "__main__":` block in `gmv_monad_backup.py` itself is
   sufficient — do not add a new subcommand to `11_CLI/gmv` for this, and do not stop to ask whether
   to; this is a standalone maintenance script, not a pipeline-stage command.
4. Tests: a test proving a real materialized Monad file gets backed up correctly (content-identical
   copy, correct destination path), and a test proving an EMPTY `03_STATE/ombra/` (no Monads yet)
   is a clean no-op, not an error.
5. Run `.venv/bin/python -m pytest tests/ -q` / `ruff check .` — confirm only the one pre-existing
   failure.
6. Live proof: run it for real against the actual `03_STATE/ombra/GMV-000002.md` (the real Bucchi
   Monad from tonight) and confirm the backup copy exists and is byte-identical.

## Report back

1. Where `SOURCE_RUNTIME_BOUNDARIES.md` says about `03_STATE/` backup (verbatim), and whether it
   changed this task's approach.
2. The real backup destination chosen and why.
3. Confirmation of the live proof (step 6) — real file, real byte-identical copy.
4. Test/ruff results, `git diff`/`git status --short`.
