"""GMV Crawler — Task 13: review queue for UNRESOLVED entity identity proposals.

Pins the resolve -> propose -> queue chain of
`propose_entity_identity()` (10_API/gmv_crawler_entity_resolver.py) into
this queue, and the module's stated non-goals, each attacked directly:

  Q1 "an empty input creates nothing and leaves an existing file
      untouched"  -> test_empty_proposals_create_nothing_and_touch_nothing
  Q2 "one JSON line per proposal, exactly 5 keys, queued_at on the
      ENVELOPE"  -> test_queued_line_carries_exactly_the_five_keys
  Q3 "the 4 fields verbatim, not normalized"
      -> test_queued_fields_are_verbatim_never_normalized
  Q4 "append, never overwrite"      -> test_two_calls_accumulate_not_overwrite
  Q5 "creates the parent directories"
      -> test_parent_directories_are_created_on_demand
  Q6 "no deduplication -- a name queued twice is TWO review items"
      -> test_identical_proposals_are_never_deduplicated
  Q7 "this queue is a PARALLEL file, never the type queue, and its key
      set is exactly its own dataclass's fields"
      -> test_queue_is_a_parallel_file_with_its_own_exact_key_set
  Q8 "the return value equals the number of lines written"
      -> test_returned_count_is_the_number_of_lines_written
  Q9 "queueing never writes the entity registry, and never needs it"
      -> test_queueing_never_touches_the_entity_registry
"""
from __future__ import annotations

import ast
import json
import sys
from dataclasses import fields
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_crawler_entity_identity_proposal_queue as identity_queue  # noqa: E402
import gmv_crawler_entity_proposal_queue as type_queue  # noqa: E402
from gmv_crawler_entity_identity_proposal_queue import (  # noqa: E402
    append_entity_identity_proposals,
)
from gmv_crawler_entity_resolver import (  # noqa: E402
    EntityIdentityProposal,
    EntityTypeProposal,
    propose_entity_identity,
    resolve_entity_gmv_id,
)

NOW_1 = "2026-09-26T12:00:00Z"
NOW_2 = "2026-09-26T13:30:00Z"

REAL_REGISTRY_PATH = ROOT / "00_CONFIG" / "gmv_entity_registry.json"
UNKNOWN_NAME = "Danilo Bucchi"  # real artist, deliberately NOT in gmv_entity_registry.json


def make_proposal(
    raw_name: str = UNKNOWN_NAME,
    *,
    suggested_entity_type: str = "ARTIST",
    source_id: str = "/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/BUCCHI_Danilo/doc.md",
    evidence_excerpt: str = "Danilo Bucchi (Roma 1978) studied in Rome",
) -> EntityIdentityProposal:
    return EntityIdentityProposal(
        raw_name=raw_name,
        suggested_entity_type=suggested_entity_type,
        source_id=source_id,
        evidence_excerpt=evidence_excerpt,
    )


def _empty_registry() -> dict:
    return {"note": "test fixture", "entities": []}


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- Q1: nothing to record is a legitimate state, and it touches nothing ---

def test_empty_proposals_create_nothing_and_touch_nothing(tmp_path: Path) -> None:
    """Q1, both halves. An empty call must create NEITHER the file NOR its
    parent directories (the "queue exists iff something was enqueued"
    invariant gmv_crawler_entity_proposal_queue.py already relies on), and
    must leave an ALREADY EXISTING queue byte-identical -- a caller that
    processes a document in which every name already resolves must not
    rewrite, reorder or truncate anything a human is reading."""
    fresh_path = tmp_path / "does" / "not" / "exist.jsonl"
    assert append_entity_identity_proposals((), fresh_path, now=NOW_1) == 0
    assert not fresh_path.exists()
    assert not fresh_path.parent.exists()

    existing = tmp_path / "queue.jsonl"
    assert append_entity_identity_proposals((make_proposal(),), existing, now=NOW_1) == 1
    before = existing.read_bytes()
    assert append_entity_identity_proposals((), existing, now=NOW_2) == 0
    assert existing.read_bytes() == before


# --- Q2/Q3: the exact line shape, verbatim fields ---

def test_queued_line_carries_exactly_the_five_keys() -> None:
    """Q2: exactly the four `EntityIdentityProposal` fields plus
    `queued_at`, and `queued_at` is on the ENVELOPE -- the dataclass has no
    timestamp field, and adding one would make "when was this proposed"
    depend on the extractor instead of the queue. The key ORDER is the
    module's declared `_QUEUE_KEYS` order, not incidental."""
    path = Path("unused")  # never opened: nothing is written in this test
    del path
    assert identity_queue._QUEUE_KEYS == (
        "raw_name", "suggested_entity_type", "source_id", "evidence_excerpt",
    )
    assert set(identity_queue._QUEUE_KEYS) == {f.name for f in fields(EntityIdentityProposal)}


def test_queued_line_is_one_json_object_with_the_envelope_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "queue.jsonl"
    assert append_entity_identity_proposals((make_proposal(),), path, now=NOW_1) == 1
    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert len(raw.splitlines()) == 1
    (row,) = read_lines(path)
    assert list(row) == [*identity_queue._QUEUE_KEYS, "queued_at"]
    assert row["queued_at"] == NOW_1
    assert not hasattr(EntityIdentityProposal, "queued_at")


def test_queued_fields_are_verbatim_never_normalized(tmp_path: Path) -> None:
    """Q3: every field lands byte-for-byte as it was proposed. A
    lower-cased or stripped name would point at a string the resolver can
    never be handed again; a normalized locator would point at a Dropbox
    path that does not exist. And `suggested_entity_type` is queued even
    when it is "" -- "no type was available" is a real, actionable review
    state, while a MISSING key reads as an incomplete write."""
    path = tmp_path / "queue.jsonl"
    raw = "  DANILO  Bucchi\t"
    assert append_entity_identity_proposals(
        (
            make_proposal(raw, suggested_entity_type="ARTIST"),
            make_proposal("Altro", suggested_entity_type=""),
        ),
        path,
        now=NOW_1,
    ) == 2
    first, second = read_lines(path)
    assert first["raw_name"] == raw
    assert first["suggested_entity_type"] == "ARTIST"
    assert "suggested_entity_type" in second
    assert second["suggested_entity_type"] == ""
    # Non-ASCII survives round-trip: ensure_ascii=False, like the type queue.
    accented = make_proposal("Giorgio de Chirico", evidence_excerpt="mostra a Roma, città")
    assert append_entity_identity_proposals((accented,), path, now=NOW_2) == 1
    assert "città" in path.read_text(encoding="utf-8")
    assert "\\u" not in path.read_text(encoding="utf-8")


# --- Q4/Q5: file mechanics ---

def test_two_calls_accumulate_not_overwrite(tmp_path: Path) -> None:
    """Q4: a second scan's rows land AFTER the first scan's, in the order
    they were given, with their own timestamps. Overwriting would destroy
    the history a human needs to see that a name keeps recurring."""
    path = tmp_path / "queue.jsonl"
    assert append_entity_identity_proposals((make_proposal("Uno"),), path, now=NOW_1) == 1
    assert append_entity_identity_proposals(
        (make_proposal("Due"), make_proposal("Tre")), path, now=NOW_2,
    ) == 2
    rows = read_lines(path)
    assert [row["raw_name"] for row in rows] == ["Uno", "Due", "Tre"]
    assert [row["queued_at"] for row in rows] == [NOW_1, NOW_2, NOW_2]


def test_parent_directories_are_created_on_demand(tmp_path: Path) -> None:
    """Q5: the path is supplied entirely by the caller -- this module has
    no hardcoded default, the `run_dir`/`bundle_dir` pattern of
    gmv_notion_projection_adapter.py -- so a caller-chosen nested runtime
    path must work without pre-creating anything."""
    path = tmp_path / "01_RUNTIME" / "gmv_crawler" / "identity" / "queue.jsonl"
    assert not path.parent.exists()
    assert append_entity_identity_proposals((make_proposal(),), path, now=NOW_1) == 1
    assert path.exists()


# --- Q6: no dedup, no similarity, no grouping ---

def test_identical_proposals_are_never_deduplicated(tmp_path: Path) -> None:
    """Q6: the same name from two documents is TWO review items, and even
    the SAME proposal object queued twice is two lines. A queue that
    deduplicated would be silently deciding that repeated sightings are one
    real entity -- the Layer-2 judgement
    GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md §2 Q2 explicitly leaves
    unbuilt. A human sees the repetition and decides."""
    path = tmp_path / "queue.jsonl"
    proposal = make_proposal()
    assert append_entity_identity_proposals((proposal, proposal, proposal), path, now=NOW_1) == 3
    assert len(read_lines(path)) == 3
    assert append_entity_identity_proposals(
        (proposal, make_proposal(UNKNOWN_NAME.lower())), path, now=NOW_2,
    ) == 2
    rows = read_lines(path)
    assert len(rows) == 5
    # A case-variant is a DIFFERENT line, not a merge with the first one.
    assert rows[3]["raw_name"] == UNKNOWN_NAME
    assert rows[4]["raw_name"] == UNKNOWN_NAME.lower()


# --- Q7: parallel file, parallel key set, never merged ---

def test_queue_is_a_parallel_file_with_its_own_exact_key_set() -> None:
    """Q7, the module's central non-goal, pinned mechanically. The two
    queues cover two different dataclasses, and the two key sets are
    DISJOINT -- so they cannot have been merged or widened into one record
    shape, which is what `gmv_crawler_entity_proposal_queue.py`'s own
    docstring forbids ("two different files for two different concerns
    ... never merged into one").

    The identity queue's key set is exactly ALL of
    `EntityIdentityProposal`'s fields: it has no filter, so there is no
    constant-true field to leave out. The type queue's key set is
    `EntityTypeProposal`'s fields MINUS `needs_verification` -- asserted
    explicitly rather than papered over, because that omission is real and
    deliberate over there (every queued row is a `needs_verification=True`
    row by that module's own filter, so the field would be a constant).
    Two different key sets for two different records, not one generic
    shape trying to serve both."""
    type_keys = set(type_queue._QUEUE_KEYS)
    identity_keys = set(identity_queue._QUEUE_KEYS)
    assert identity_keys == {f.name for f in fields(EntityIdentityProposal)}
    assert type_keys == {f.name for f in fields(EntityTypeProposal)} - {"needs_verification"}
    assert type_keys & identity_keys == set()
    assert "raw_name" in identity_keys and "entity_name" in type_keys
    # And the second module does not even import the first: it reads
    # EntityIdentityProposal and nothing else from the resolver. Checked
    # through `ast` rather than a substring search, because this module's
    # own docstring names `gmv_crawler_entity_proposal_queue.py` and
    # `append_entity_proposals()` ON PURPOSE, to record why they are not
    # reused -- a naive `in source` scan would flag that documentation as
    # a dependency.
    tree = ast.parse(
        (ROOT / "10_API" / "gmv_crawler_entity_identity_proposal_queue.py").read_text(
            encoding="utf-8"
        )
    )
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert "gmv_crawler_entity_proposal_queue" not in imported
    assert "gmv_crawler_entity_resolver" in imported


def test_returned_count_is_the_number_of_lines_written(tmp_path: Path) -> None:
    """Q8: the count is what a caller needs to know how much is pending.
    Unlike the type queue's filtered count (which is NOT len(proposals)),
    this one has no filter, so the count is exactly len(proposals) --
    stated in the docstring, and pinned here so a future filter cannot
    change the contract silently. The count=0 case is included and leaves
    no file behind at all, so the line count is checked only once
    something has actually been written."""
    path = tmp_path / "queue.jsonl"
    expected_lines = 0
    for count in (0, 1, 2, 5):
        batch = tuple(make_proposal(f"Name {i}") for i in range(count))
        assert append_entity_identity_proposals(batch, path, now=NOW_1) == count
        expected_lines += count
        if expected_lines:
            assert len(read_lines(path)) == expected_lines
        else:
            assert not path.exists()


# --- Q9: queueing is not writing ---

def test_queueing_never_touches_the_entity_registry(tmp_path: Path) -> None:
    """Q9, the whole point of the split. A queued line is a proposal in a
    text file: it must not create, touch or even require an entity
    registry. `propose_entity_identity()` is called here with a registry
    that is then asserted unchanged, and the committed governance file is
    byte-identical afterwards -- turning a queued line into a real
    `gmv_id` is `confirm_new_entity()`, an explicit human action, reached
    from nowhere in this test."""
    committed_before = REAL_REGISTRY_PATH.read_bytes()
    registry = {"note": "test fixture", "entities": []}
    registry_before = json.dumps(registry, sort_keys=True)

    path = tmp_path / "queue" / "entity_identity_proposal_queue.jsonl"
    written = append_entity_identity_proposals(
        (propose_entity_identity(
            UNKNOWN_NAME, registry, source_id="SRC-1", evidence_excerpt="cited",
            suggested_entity_type="ARTIST",
        ),),
        path,
        now=NOW_1,
    )
    assert written == 1
    assert json.dumps(registry, sort_keys=True) == registry_before
    assert REAL_REGISTRY_PATH.read_bytes() == committed_before
    # The queued name still does not resolve -- queuing resolved nothing.
    (row,) = read_lines(path)
    assert row["raw_name"] == UNKNOWN_NAME
    assert resolve_entity_gmv_id(row["raw_name"], registry) is None
    assert "gmv_id" not in row  # no id is invented at proposal time


def test_propose_returns_none_for_a_known_name_so_nothing_is_queued(tmp_path: Path) -> None:
    """The chain's other end, on the real committed registry: a name that
    already resolves produces NO proposal, so there is nothing to queue
    and the queue file is never created. This is what keeps a nightly run
    from filling the queue with names it already knows."""
    data = json.loads(REAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    known = data["entities"][0]["canonical_name"]
    path = tmp_path / "queue.jsonl"
    assert propose_entity_identity(
        known, data, source_id="SRC-1", evidence_excerpt="cited"
    ) is None
    assert append_entity_identity_proposals((), path, now=NOW_1) == 0
    assert not path.exists()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
