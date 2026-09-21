#!/usr/bin/env python3
"""GMV Crawler — rejection queue for BUILD ATOMS rejections (Task 7).

Consumes the output of `build_atoms()` (10_API/gmv_crawler_atom_builder.py,
Task 6): the `RejectedCandidate` tuples that today survive only for the
life of the process that called `build_atoms()` are accumulated here, as
JSONL rows in a caller-supplied file, across scans -- then summarized
into a frequency-ordered view a human can read to decide what to teach
the system next. This module READS `RejectedCandidate`; it never
modifies `gmv_crawler_atom_builder.py` in any way, and nothing in
`build_atoms()` calls it: appending stays the caller's decision, by
design (the future pipeline/orchestration decides when to enqueue).

Non-negotiable boundary, decided with the user, not a design gap: this
module NEVER decides anything by itself -- no predicate promotion, no
entity recognition, no similarity-based dedup of near-miss rejections
("is the author of" vs "is author of" stay two separate rows). It only
accumulates and summarizes, for a human who then decides.

Why JSONL and not a table: `tests/test_sqlite_connection_boundary.py`
whitelists exactly two production owners of `sqlite3.connect`
(gmv_core/database.py, gmv_crawler_fulltext_index.py) and
`tests/test_write_authorization.py` pins the DML site matrix to an
exact, user-approved set; adding a new connection/writer owner for a
read-and-triage tool would be disproportionate security scope. A plain
text file, one JSON object per line, path supplied explicitly by the
caller (no hardcoded default path here -- the `run_dir`/`bundle_dir`
pattern of gmv_notion_projection_adapter.py).

Other explicit non-goals: no rotation/purging/size limit (a file growing
without bound is a later step's problem); no handling of malformed lines
(this file is written only by `append_rejected()` in this module, so
well-formed lines are a correct assumption, not a generic
"never-validate-input").
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_atom_builder import RejectedCandidate  # noqa: E402 -- input type, not modified

#: Exactly the JSON keys each queued line carries, in this order.
_QUEUE_KEYS = ("source_id", "extraction_claim_ref", "raw_predicate", "reason_code", "detail", "subject_raw", "object_raw", "evidence_excerpt")


def append_rejected(rejected: Sequence[RejectedCandidate], queue_path: Path, *, now: str) -> None:
    """Append every `rejected` as one JSON line to `queue_path`.

    Creates the file and any missing parent directories (append, never
    overwrite -- a second scan appends after the first, it does not
    replace it). Each line is `json.dumps({...}, ensure_ascii=False) +
    "\\n"` with exactly the five `RejectedCandidate` fields taken verbatim
    plus `queued_at=now` -- the moment THIS rejection was enqueued, not a
    field of `RejectedCandidate` (Task 6 deliberately gives that class no
    timestamp field; it stays separate here, on the envelope).
    """
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as stream:
        for candidate in rejected:
            payload = {key: getattr(candidate, key) for key in _QUEUE_KEYS}
            payload["queued_at"] = now
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class RejectionQueueSummaryEntry:
    """One row of the human-readable summary: a single `(reason_code,
    raw_predicate)` group counted across the whole file."""

    reason_code: str
    raw_predicate: str
    count: int
    first_queued_at: str
    last_queued_at: str


def summarize_rejection_queue(queue_path: Path) -> tuple[RejectionQueueSummaryEntry, ...]:
    """Frequency-ordered summary of every group in `queue_path`.

    An absent file is a legitimate, common state (right after creating
    this module, before the first scan), not a caller bug -> empty tuple,
    no exception. Groups are keyed by the EXACT `(reason_code,
    raw_predicate)` pair -- not `reason_code` alone (that would throw
    away which predicate keeps failing) and not `raw_predicate` alone
    (that would blur "never recognized" vs "recognized but unsupported",
    a real operational distinction for the human deciding next steps).
    `first_queued_at`/`last_queued_at` are the min/max `queued_at` in the
    group -- because every crawler `now` in this repository is an
    ISO-8601-with-Z string (verified in tests/test_gmv_crawler_registry.py:
    NOW_1..NOW_3, and tests/test_gmv_crawler_atom_builder.py: NOW),
    plain lexicographic min/max is correct, no date parsing.

    Result order is ALWAYS the explicit sort `count` descending, then
    `(reason_code, raw_predicate)` ascending -- deterministic on
    identical input, independent of whichever dict/iteration order the
    aggregation happened to use.
    """
    if not queue_path.exists():
        return ()
    aggregate: dict[tuple[str, str], list[str]] = {}
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        aggregate.setdefault((record["reason_code"], record["raw_predicate"]), []).append(
            record["queued_at"]
        )
    entries = [
        RejectionQueueSummaryEntry(
            reason_code=reason_code,
            raw_predicate=raw_predicate,
            count=len(queued_at),
            first_queued_at=min(queued_at),
            last_queued_at=max(queued_at),
        )
        for (reason_code, raw_predicate), queued_at in aggregate.items()
    ]
    entries.sort(key=lambda entry: (-entry.count, entry.reason_code, entry.raw_predicate))
    return tuple(entries)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python gmv_crawler_rejection_queue.py <queue_path>", file=sys.stderr)
        raise SystemExit(2)
    for entry in summarize_rejection_queue(Path(sys.argv[1])):
        print(f"{entry.count}\t{entry.reason_code}\t{entry.raw_predicate}")