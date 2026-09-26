#!/usr/bin/env python3
"""GMV Crawler — review queue for UNRESOLVED entity identity proposals.

Consumes the output of `propose_entity_identity()` (10_API/gmv_crawler_entity_resolver.py):
an `EntityIdentityProposal` is a name the resolver could not map to a stable
`gmv_id`, waiting for a human. This module READS `EntityIdentityProposal`;
it never modifies `gmv_crawler_entity_resolver.py` in any way, and nothing
in the resolver calls it: appending stays the caller's decision, by design
-- the exact same decoupling the type-proposal queue states for
`classify_entity_types()`.

**Same JSONL pattern as `gmv_crawler_entity_proposal_queue.py`, different
file, different concern, never merged into one.** That queue's own module
docstring says so of itself: "this queue stays SEPARATE from Task 7's
rejection queue -- same JSONL pattern, two different files for two
different concerns ... never merged into one". The same reasoning applies
one level up, and it is a stronger reason here, not a stylistic one:
`append_entity_proposals()` is hard-coded to the exact four fields of
`EntityTypeProposal` (`entity_name`/`entity_type`/`confidence`/`source`)
and filters on `needs_verification`, a field `EntityIdentityProposal` does
not have and must not grow (an identity proposal is unverified by
construction -- there is no verified case to filter out). Widening the
existing module to accept a second record shape would either break its
`_QUEUE_KEYS` guarantee or make it generic, and a generic queue is a
component nobody has a real caller for yet.

Non-negotiable boundary: **nothing in this module writes to the entity
registry, ever.** A queued line is a proposal in a plain text file; the
only thing that can turn one into a real `gmv_id` is a human calling
`confirm_new_entity()`/`confirm_entity_alias()` in
`gmv_crawler_entity_resolver.py`, mirroring the read-check-append-write of
`automation/gmv_crawler_review_tool.py::confirm_institution()`. That is
the same separation already in force for predicate mappings
(`crawler_predicate_text_mapping.json`) and institutions
(`area35_known_institutions.json`): queue now, confirm later, only then
written.

Also non-negotiable, and NOT built here: no similarity, no
near-duplicate detection, no "did you mean", no grouping. A name queued by
two documents is two lines, and whether those are one real entity is
exactly the judgement
`GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` §2 Q2 (2026-09-26) assigns to
the deliberately-unbuilt Layer 2. A "helpfully" deduplicating queue would
make that unbuilt decision silently, in the one place a human is supposed
to be looking at every row.

Why JSONL and not a table: the same reason
`gmv_crawler_entity_proposal_queue.py` gives, unchanged and re-verified
here rather than assumed -- `tests/test_sqlite_connection_boundary.py`
whitelists exactly two production owners of `sqlite3.connect`, and
`tests/test_write_authorization.py` pins the DML site matrix to an exact,
user-approved set. A read-and-triage tool does not justify new security
scope.

Conventions copied from that module deliberately, not reinvented: one JSON
object per line; `queued_at` on the ENVELOPE, never a field of the
dataclass (Task 8's `EntityIdentityProposal` has no timestamp field, and
adding one would make the "when was this proposed" answer depend on the
extractor's clock rather than the queue's); the file and its parent
directories are created only if there is at least one line to write, so an
empty call leaves any existing file untouched; append, never overwrite;
`json.dumps(..., ensure_ascii=False)`; the path is supplied by the caller
with no hardcoded default here.

Explicit non-goals, so none gets silently "fixed" later: no
rotation/purging/size limit; no handling of malformed lines (this file is
written only by `append_entity_identity_proposals()` in this module, so
well-formed lines are a correct assumption, not a generic
"never-validate-input"); and deliberately NO summary/read-back function --
`gmv_crawler_entity_proposal_queue.py` has one because the type queue
accumulates rows needing frequency grouping, and nothing here does that
job. A future caller that needs to read the queue back should add the
function when it has a real reader, not now, on the assumption that one
is coming.

`suggested_entity_type` is queued even when it is `""` (the caller had no
type available). It is written rather than omitted on purpose: a line
saying "no type was available" is a real, actionable review state, while a
line missing the key reads as an incomplete write.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_entity_resolver import EntityIdentityProposal  # noqa: E402 -- input type, not modified

#: Exactly the JSON keys each queued line carries, in this order -- the four
#: `EntityIdentityProposal` fields verbatim, mirroring `_QUEUE_KEYS` in
#: gmv_crawler_entity_proposal_queue.py. `suggested_entity_type` is present
#: even when empty, for the reason in the module docstring.
_QUEUE_KEYS = ("raw_name", "suggested_entity_type", "source_id", "evidence_excerpt")


def append_entity_identity_proposals(
    proposals: Sequence[EntityIdentityProposal], queue_path: Path, *, now: str
) -> int:
    """Append each proposal as one JSON line, and return the number of lines
    written.

    There is no filter here, and that is deliberate rather than an
    omission: `gmv_crawler_entity_proposal_queue.append_entity_proposals()`
    drops `needs_verification=False` rows because they are already-verified
    roster facts and queueing them would be noise. Every
    `EntityIdentityProposal` reaching this function is by construction a
    name that did NOT resolve, so every one of them is a real review item.
    The consequence is that the returned count equals `len(proposals)`
    whenever the input is non-empty -- stated here so a caller does not
    have to guess whether something was dropped.

    An EMPTY `proposals` creates nothing and leaves any existing file
    completely untouched: "nothing to record" is a legitimate, common state
    (every document in which every name already resolves), the same
    invariant `append_entity_proposals()` already relies on and that
    `test_write_authorization.py:611
    test_no_log_file_created_without_any_violation` pins for the
    authorization log. Returns 0 in that case, having touched no
    filesystem at all.

    Otherwise creates the file and any missing parent directories and
    appends -- never overwrites, so a second scan's rows land after the
    first scan's rather than replacing them. Each line is
    `json.dumps({...}, ensure_ascii=False) + "\\n"` with exactly the four
    `EntityIdentityProposal` fields taken verbatim plus `queued_at=now`
    on the envelope: the moment THIS proposal was enqueued, supplied by
    the caller (every crawler `now` in this repository is an
    ISO-8601-with-Z string) rather than read from a clock here, which is
    what makes a queued line reproducible in a test.
    """
    if not proposals:
        return 0
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as stream:
        for proposal in proposals:
            payload = {key: getattr(proposal, key) for key in _QUEUE_KEYS}
            payload["queued_at"] = now
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return len(proposals)
