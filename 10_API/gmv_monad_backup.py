#!/usr/bin/env python3
"""GMV Crawler — standalone backup for materialized Monad files (the "Ombra").

Copies every `*.md` file under `03_STATE/ombra/` to a separate backup
directory. Deliberately NOT an extension of `10_API/backup_service.py`,
and deliberately unaware of `10_API/gmv_monad_materializer.py`.

Grounding, read in full before writing this module:

- **`00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md`**, `03_STATE/` row, verbatim:
  "Full-system backup after S002-20; never Git". `03_STATE/ombra/` row,
  verbatim: "Full-system backup after S002-20; never Git. Sub-path decision
  (crawler preplan step 8/9 handoff, this session): the canonical on-disk
  directory for materialized Monad `.md` files (the \"Ombra\") produced by
  `10_API/gmv_monad_materializer.py`. Already covered by `03_STATE/`'s
  existing \"Live state\" classification above; called out separately only
  because a caller-supplied `target_path` needed a concrete default. No new
  top-level path or governance class was created." So this directory has a
  backup obligation attached and no conflicting convention for it: this
  module is the first concrete implementation of that obligation for the
  Ombra specifically. It does not claim to discharge the wider
  "full-system backup" for `03_STATE/` as a whole.

- **`10_API/backup_service.py::create_backup()`** (line 184) does NOT cover
  this directory, verified by reading it, not assumed: it backs up exactly
  two things — `09_DATABASE/GMV.db` (via `_sqlite_backup`) and a
  `/usr/bin/git archive HEAD` tarball — and its own manifest records
  `"excluded": ["runtime", "cache", "temporary outputs", "generated
  indexes"]`. So the correction in the task brief is accurate: nothing in
  production code backs up `03_STATE/ombra/` today, and
  `gmv_monad_materializer.py`'s docstring phrase "within
  `secure_storage.py`'s/`backup_service.py`'s perimeter" is a spec-level
  declaration about write safety, not a statement that a backup exists.

- **`10_API/secure_storage.py`** (56 lines, read in full) is the write
  primitive this module reuses, exactly as `gmv_monad_materializer.py`
  already does (`from secure_storage import atomic_write_text`, line 116;
  used at line 442). `atomic_write_text(path, text)` ->
  `atomic_write_bytes()`, which enforces `0o700` on the parent directory
  and `0o600` on the file, then `mkstemp` + `fsync` + `os.replace`. Two
  consequences this module inherits rather than re-implements: writing a
  backup never leaves a partially-written file under its final name, and a
  pre-existing destination file with looser permissions raises
  `PermissionError` instead of being silently reused. No `shutil.copy`, no
  second write mechanism, per the task's constraint 3.

- **Destination** is `Path.home() / ".gmv_backups" / "ombra"`, the same
  root `backup_service.py::main()`'s own CLI already defaults to (line
  436: `create.add_argument("--root", type=Path, default=Path.home() /
  ".gmv_backups")`), under its own `ombra/` subfolder so it can never
  collide with `backup_service.py`'s `sets/<BKP-id>/` structure or its
  `audit/` log. `Path.home()` rather than a literal path on purpose: the
  repo's own `scripts/check_runtime_git_policy.py` flags any tracked file
  containing a hardcoded absolute path into a person's account as
  `personal_absolute_path` (its regex matches the two POSIX home layouts
  by prefix), and resolving at runtime is also what makes the default
  destination automatically redirectable in tests — the autouse
  `isolated_gmv` fixture in `tests/conftest.py` sets `HOME` to `tmp_path`,
  so tests exercise the real default path without touching the operator's
  real backup directory.

## What this module deliberately does NOT do

- **No SQL, no database, no dependency.** Nothing here imports `sqlite3`
  or touches `09_DATABASE/GMV.db`; `backup_service.py` owns the database
  concern and is not modified.
- **`gmv_monad_materializer.py` is untouched.** It stays a pure render +
  atomic-write function that knows nothing about backup. Backing up is a
  separate, later action a caller takes, the same separation of concerns
  as `project_public()` composing with, but never being called by,
  `materialize_monad()`.
- **No verification, no retention, no manifest, no audit log.** This is a
  current-state mirror, not a versioned archive: two runs on different
  days leave one copy, the newer one. That is a real limitation, stated
  rather than implied away. If a dated, verified, restorable history of
  Monads is wanted, `backup_service.py`'s existing `sets/<BKP-id>/` +
  `manifest.json` + `verify_backup()` machinery is where it belongs, and
  wiring Ombra files into that manifest schema is explicitly out of scope
  here (it would change a tested contract for an unrelated use case, and
  the task brief forbids touching `backup_service.py`).

## Scope of the copy: `rglob("*.md")`, mirrored by relative path

The source directory is flat by design (one `GMV-<id>.md` per entity), so
"under" is ambiguous for a subdirectory that does not exist today. The
recursive form is chosen anyway, and the destination mirrors each file's
path relative to the source, because the two failure modes of the flat
form are both silent:

- `glob("*.md")` would silently skip a nested Monad — a backup that
  reports success while missing a file is the worst failure mode a backup
  can have.
- `glob("*.md")` + a flat destination would let two same-named files in
  different subdirectories overwrite each other, also silently.

Mirroring costs one `relative_to()` call and makes both cases correct.
No file matching `*.md` is skipped for any other reason — not for being a
dotfile, not for its size. A directory whose own name ends in `.md` is not
special-cased either: reading it raises `IsADirectoryError`, which is a
louder and more truthful outcome than quietly omitting it.

## Byte fidelity, and the one real trap in "read it, write it"

The task's constraint is to read the source and write it through
`atomic_write_text()`, not `shutil.copy`. That is a text round trip, and a
text round trip has one real failure mode: `Path.read_text()` defaults to
`newline=None`, i.e. Python's universal-newline mode, which rewrites
`\r\n` and lone `\r` to `\n` on read. A CRLF source would therefore be
"backed up" with its line endings silently normalized — content changed,
no error raised, which for a backup is the worst kind of bug. Fixed by
reading with `newline=""`, which disables translation so the string handed
to `atomic_write_text()` re-encodes to exactly the source bytes.

`newline=""` was verified to exist on this interpreter's `Path.read_text`
(added in Python 3.13; this repo runs 3.14) rather than assumed, and the
CRLF case is pinned by a test that compares raw bytes, not strings.
The remaining precondition is honest and unavoidable on this path: the
source must be valid UTF-8, or `read_text()` raises `UnicodeDecodeError`
instead of copying bytes. Every file `materialize_monad()` writes is UTF-8
by construction (`atomic_write_text` encodes it), so this is a property of
the producer, not a new restriction; a hand-mangled non-UTF-8 file fails
loudly rather than being backed up corrupted.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from secure_storage import atomic_write_text  # noqa: E402 -- reused, not reimplemented

#: The canonical source directory for materialized Monads. Not read from
#: `SOURCE_RUNTIME_BOUNDARIES.md` at runtime -- that file is a governance
#: document, not configuration, and parsing a Markdown table to find a
#: path would be a worse dependency than one derived constant. The value
#: is the same one `gmv_monad_materializer.py`'s own docstring names.
OMBRA_SOURCE_DIR = REPO_ROOT / "03_STATE" / "ombra"

#: Backup root directory name under the operator's home, and the
#: subfolder this module owns inside it. `backup_service.py::main()`
#: already defaults its own `--root` to the parent of the first.
BACKUP_ROOT_NAME = ".gmv_backups"
OMBRA_BACKUP_DIRNAME = "ombra"

#: Only Markdown is copied. This is the one filter, and it is a suffix
#: match, not a content check: it selects Monad files and nothing else,
#: and it is what keeps an unrelated stray file in the directory from
#: being presented as a backed-up Monad.
MONAD_SUFFIX = ".md"


def default_backup_dir() -> Path:
    """`~/.gmv_backups/ombra`, the destination this module writes to when
    the caller names none. Resolved at call time, never at import time,
    so that the test suite's `HOME` redirect (`tests/conftest.py`'s
    autouse `isolated_gmv` fixture) applies to it."""
    return Path.home() / BACKUP_ROOT_NAME / OMBRA_BACKUP_DIRNAME


def backup_materialized_monads(
    source_dir: Path | None = None,
    destination: Path | None = None,
) -> tuple[Path, ...]:
    """Copy every `*.md` file under `source_dir` to `destination`.

    Returns the destination paths written, in sorted source order, so a
    caller can report or assert exactly what was copied. Each copy goes
    through `secure_storage.atomic_write_text()`; the destination
    directory tree is created by that function with `0o700` as a side
    effect, so there is no separate `mkdir` here and no way for this
    module to create a world-readable backup directory.

    An absent `source_dir` and an existing-but-empty one both return `()`
    without raising and without creating anything. Chosen deliberately:
    a maintenance script run on a machine where nothing has been
    materialized yet should report "nothing to back up", not crash, and
    the empty return is how a caller tells that apart from a partial run.
    A *typo'd* source path is therefore also a quiet no-op — the honest
    cost of that choice, and the reason the CLI prints the source
    directory it used.

    Existing destination files are replaced, not merged or skipped: this
    is a mirror of current state, so the newest materialization wins.
    `secure_storage` enforces `0o600` on any pre-existing destination
    file, so a world-readable file left at that path raises
    `PermissionError` rather than being overwritten or trusted.
    """
    source = OMBRA_SOURCE_DIR if source_dir is None else Path(source_dir)
    target_root = default_backup_dir() if destination is None else Path(destination)
    if not source.is_dir():
        return ()
    written: list[Path] = []
    for path in sorted(source.rglob(f"*{MONAD_SUFFIX}")):
        target = target_root / path.relative_to(source)
        atomic_write_text(target, path.read_text(encoding="utf-8", newline=""))
        written.append(target)
    return tuple(written)


def main(arguments: list[str] | None = None) -> int:
    """CLI entry point, in this file on purpose: this is a standalone
    maintenance script, not a pipeline stage, so it is deliberately not
    registered as a subcommand of `11_CLI/gmv`."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=OMBRA_SOURCE_DIR)
    parser.add_argument("--destination", type=Path, default=None)
    parsed = parser.parse_args(arguments)
    destination = parsed.destination or default_backup_dir()
    written = backup_materialized_monads(parsed.source, destination)
    print(f"source      : {parsed.source}")
    print(f"destination : {destination}")
    print(f"backed up   : {len(written)}")
    for path in written:
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())