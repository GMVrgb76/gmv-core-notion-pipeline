#!/usr/bin/env python3
"""GMV Crawler — review queue for MODEL_INFERENCE entity type proposals (Task 9).

Consumes the output of `classify_entity_types()` (10_API/gmv_crawler_entity_resolver.py,
Task 8): an `EntityTypeProposal` carries `needs_verification`, and only
the True ones are worth accumulating for human review. This module READS
`EntityTypeProposal`; it never modifies `gmv_crawler_entity_resolver.py`
in any way, and nothing in `classify_entity_types()` calls it: appending
stays the caller's decision, by design (the future
pipeline/orchestration decides when to enqueue) -- the exact same
decoupling as the Task 6 -> Task 7 pair.

The one deliberate difference from Task 7's rejection queue: a
`RejectedCandidate` is "to review" by definition, every row gets queued;
an `EntityTypeProposal` is NOT -- `source=="MATCHED_KNOWN_ARTIST_ROSTER"`
means an already-verified fact (`needs_verification=False`), and queueing
it next to real doubts would be noise, not signal. Filtering on
`needs_verification` is done HERE, inside the queue boundary, because it
is the queue's own definition of what belongs in it -- not a kind of
rejection the caller must compute separately.

Non-negotiable boundary, decided with the user, not a design gap: this
module NEVER decides anything by itself -- no entity type promotion, no
fuzzy "same-ish name" dedup ("Le Stanze della Fotografia" proposed once
as EXHIBITION and once as INSTITUTION stays two separate summary groups,
both visible for a human to notice the conflict). It only accumulates
and summarizes, for a human who then decides.

Why JSONL and not a table: `tests/test_sqlite_connection_boundary.py`
whitelists exactly two production owners of `sqlite3.connect`
(gmv_core/database.py, gmv_crawler_fulltext_index.py) and
`tests/test_write_authorization.py` pins the DML site matrix to an
exact, user-approved set; adding a new connection/writer owner for a
read-and-triage tool would be disproportionate security scope. A plain
text file, one JSON object per line, path supplied explicitly by the
caller (no hardcoded default path here -- the `run_dir`/`bundle_dir`
pattern of gmv_notion_projection_adapter.py).

Explicit non-goals, so none gets silently "fixed" later: no
rotation/purging/size limit (a file growing without bound is a later
step's problem); no handling of malformed lines (this file is written
only by `append_entity_proposals()` in this module, so well-formed lines
are a correct assumption, not a generic "never-validate-input"); this
queue stays SEPARATE from Task 7's rejection queue -- same JSONL
pattern, two different files for two different concerns (rejected
predicates vs. entities awaiting verification), never merged into one.

`source` is written to every line (not assumed-away as always
"MODEL_INFERENCE"): if the resolver is ever extended with a second
unverified source, previously queued rows stay self-describing instead
of silently assuming a value the queue never verified.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_entity_resolver import EntityTypeProposal  # noqa: E402 -- input type, not modified

#: Exactly the JSON keys each queued line carries, in this order. `source`
#: is deliberately part of the record (not assumed to always be
#: "MODEL_INFERENCE"): if the resolver ever gains a second unverified
#: source, old rows remain self-describing.
_QUEUE_KEYS = ("entity_name", "entity_type", "confidence", "source")

#: Declared importance order for the `confidence_counts` tie-break. NOT
#: alphabetical: the sorted order of ("HIGH","MEDIUM","LOW") is
#: "HIGH","LOW","MEDIUM", which is NOT the order of importance. Every
#: sort key in this module resolves through this rank -- never through
#: raw "str" comparison of the levels.
_CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")
_CONFIDENCE_RANK = {level: rank for rank, level in enumerate(_CONFIDENCE_LEVELS)}


def append_entity_proposals(
    proposals: Sequence[EntityTypeProposal], queue_path: Path, *, now: str
) -> int:
    """Append the `needs_verification=True` proposals, one JSON line each.

    Filters FIRST, before any filesystem side effect: proposals with
    `needs_verification=False` (the already-verified
    MATCHED_KNOWN_ARTIST_ROSTER facts) are dropped here, silently with
    respect to the file -- that is correct behavior by definition, not
    an error. Returns the number of lines actually written, so a caller
    can know how many were filtered without recomputing it itself (NOT
    `len(proposals)`).

    When nothing survives the filter the file is NOT created and any
    existing file is left completely untouched: "nothing to record" is a
    legitimate, common state, the same invariant
    `test_write_authorization.py:611 test_no_log_file_created_without_any_violation`
    pins for the authorization log. Documented choice, not implied:
    the queue exists iff at least one unverified proposal was ever
    enqueued, which is also why `summarize_entity_proposal_queue()` on
    an absent path is the empty tuple, not an error.

    Otherwise creates the file and any missing parent directories
    (append, never overwrite -- a second scan appends after the first,
    it does not replace it). Each line is `json.dumps({...},
    ensure_ascii=False) + "\\n"` with exactly the four `EntityTypeProposal`
    fields `entity_name`/`entity_type`/`confidence`/`source` taken
    verbatim plus `queued_at=now` -- the moment THIS proposal was
    enqueued, not a field of `EntityTypeProposal` (Task 8 deliberately
    gives that class no timestamp field; it stays separate here, on the
    envelope, exactly as Task 7 keeps `queued_at` outside
    `RejectedCandidate`).
    """
    to_write = [proposal for proposal in proposals if proposal.needs_verification]
    if not to_write:
        return 0
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as stream:
        for proposal in to_write:
            payload = {key: getattr(proposal, key) for key in _QUEUE_KEYS}
            payload["queued_at"] = now
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return len(to_write)


@dataclass(frozen=True)
class EntityProposalQueueSummaryEntry:
    """One row of the human-readable summary: a single EXACT
    `(entity_name, entity_type)` group counted across the whole file."""

    entity_name: str
    entity_type: str
    confidence_counts: tuple[tuple[str, int], ...]  # e.g. (("HIGH", 3), ("MEDIUM", 1))
    count: int
    first_queued_at: str
    last_queued_at: str


def summarize_entity_proposal_queue(
    queue_path: Path,
) -> tuple[EntityProposalQueueSummaryEntry, ...]:
    """Frequency-ordered summary of every group in `queue_path`.

    An absent file is a legitimate, common state (right after creating
    this module, before the first scan), not a caller bug -> empty
    tuple, no exception -- and it is consistent with the append side: a
    queue that never had anything to write simply does not exist.

    Groups are keyed by the EXACT `(entity_name, entity_type)` pair --
    NOT `entity_name` alone. The same name proposed once as EXHIBITION
    and once as INSTITUTION across scans is a real inconsistency signal
    (e.g. "Le Stanze della Fotografia"), and mashing those rows together
    would hide it; they stay two separate groups, both visible, and it
    is the human reader who decides the two rows are the same entity --
    never this module. Rows with the same name AND exact type accumulate
    into one group, and their `confidence_counts` tuple keeps HOW OFTEN
    each of HIGH/MEDIUM/LOW occurred (gemma4:12b is not deterministic
    between scans; collapsing to a single aggregate confidence would
    lose real signal), ordered by count descending then by the declared
    HIGH/MEDIUM/LOW rank via `_CONFIDENCE_RANK` -- an explicit sort,
    never Counter's insertion order, never alphabetical.

    `first_queued_at`/`last_queued_at` are the min/max `queued_at` in
    the group -- because every crawler `now` in this repository is an
    ISO-8601-with-Z string (verified in
    tests/test_gmv_crawler_registry.py: NOW_1..NOW_3), plain
    lexicographic min/max is correct, no date parsing.

    Result order is ALWAYS the explicit sort `count` descending, then
    `(entity_name, entity_type)` ascending -- deterministic on
    identical input, independent of whichever dict/iteration order the
    aggregation happened to use.
    """
    if not queue_path.exists():
        return ()
    aggregate: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        aggregate.setdefault((record["entity_name"], record["entity_type"]), []).append(
            (record["confidence"], record["queued_at"])
        )
    entries: list[EntityProposalQueueSummaryEntry] = []
    for (entity_name, entity_type), rows in aggregate.items():
        counts = Counter(confidence for confidence, _ in rows)
        confidence_counts = tuple(
            sorted(
                counts.items(),
                key=lambda item: (-item[1], _CONFIDENCE_RANK[item[0]]),
            )
        )
        queued_at = [queued for _, queued in rows]
        entries.append(
            EntityProposalQueueSummaryEntry(
                entity_name=entity_name,
                entity_type=entity_type,
                confidence_counts=confidence_counts,
                count=len(rows),
                first_queued_at=min(queued_at),
                last_queued_at=max(queued_at),
            )
        )
    entries.sort(key=lambda entry: (-entry.count, entry.entity_name, entry.entity_type))
    return tuple(entries)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "usage: python gmv_crawler_entity_proposal_queue.py <queue_path>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    for entry in summarize_entity_proposal_queue(Path(sys.argv[1])):
        most_common = entry.confidence_counts[0][0] if entry.confidence_counts else "-"
        print(f"{entry.count}\t{entry.entity_name}\t{entry.entity_type}\t{most_common}")