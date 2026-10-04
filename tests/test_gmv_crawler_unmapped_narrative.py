"""GMV Crawler — PUBLIC narrative from propositions no governed predicate
fits (`gmv_crawler_unmapped_narrative.py`).

The two grounding tests at the bottom matter more than the rest: this
module's whole eligibility rule is one string, and the discipline
GMV_CRAWLER_HANDOFF.md's process-improvement item 7 asks for is that a
claim a literal "matches" a real value is only true if the cited
location is the same field on the same concept. So `UNMAPPED_PREDICATE_
REASON_CODE` is checked twice against the real world: once by EXECUTING
`build_relation_atoms()` (the real producer) with a real unmapped
predicate and comparing the `reason_code` it really writes, and once
against the committed real Garibaldi rejection snapshot's own
`reason_code` field. Neither check is a substring search over a file.
"""
from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_crawler_atom_builder import RejectedCandidate  # noqa: E402
from gmv_crawler_candidate_extractor import (  # noqa: E402
    CandidateEntity,
    CandidateProposition,
)
from gmv_crawler_relation_atom_builder import build_relation_atoms  # noqa: E402
from gmv_crawler_unmapped_narrative import (  # noqa: E402
    PARAGRAPH_SEPARATOR,
    UNMAPPED_PREDICATE_REASON_CODE,
    compose_unmapped_narrative,
)

NOW = "2026-10-04T09:00:00Z"
SNAPSHOT = ROOT / "00_CONFIG" / "crawler_snapshots" / "rejection_queue_2026-09-17_garibaldi.jsonl"

# Real excerpt texts, taken from the shapes Task 28 measured on the real
# corpus (practice-description-shaped and biographical sentences with no
# governed predicate), used here verbatim so the joined output can be
# judged for readability the way the real output will be.
PRACTICE = "His work explores the relationship between memory and landscape."
BIOGRAPHICAL = "Federico Garibaldi was born in Nice in 1807."
RECOGNITION = "He earned international recognition for his political commitment."


def make_rejected(**overrides) -> RejectedCandidate:
    """A real `RejectedCandidate`, built from its own dataclass fields
    read at runtime (`test_fixture_mirrors_the_real_dataclass_fields`
    below) rather than a hand-copied list that could drift."""
    values = {
        "source_id": "2026_06_17_MUTUALART_BIOGRAPHY.md",
        "extraction_claim_ref": "2026_06_17_MUTUALART_BIOGRAPHY.md#0:3",
        "raw_predicate": "explores",
        "reason_code": UNMAPPED_PREDICATE_REASON_CODE,
        "detail": "raw predicate 'explores' is not in the curated text->predicate mapping",
        "subject_raw": "Federico Garibaldi",
        "object_raw": "memory and landscape",
        "evidence_excerpt": PRACTICE,
    }
    values.update(overrides)
    return RejectedCandidate(**values)


def make_proposition(predicate: str, *, ref: str) -> CandidateProposition:
    return CandidateProposition(
        subject_raw="Federico Garibaldi",
        predicate=predicate,
        object_raw="memory and landscape",
        evidence_excerpt="the biography states a real sentence",
        status="DOCUMENTATO",
        source_id="SRC-GARIBALDI",
        evidence_id=("EV-1",),
        truncated_source=False,
        extraction_claim_ref=ref,
    )


# --- the four behaviours the task brief mandates ---

def test_multiple_real_excerpts_are_joined_in_order_with_a_blank_line_between() -> None:
    rejected = (
        make_rejected(evidence_excerpt=PRACTICE),
        make_rejected(evidence_excerpt=BIOGRAPHICAL, raw_predicate="was born in"),
        make_rejected(evidence_excerpt=RECOGNITION, raw_predicate="earned"),
    )
    assert compose_unmapped_narrative(rejected) == (
        f"{PRACTICE}\n\n{BIOGRAPHICAL}\n\n{RECOGNITION}"
    )


def test_exact_duplicate_excerpts_collapse_to_one() -> None:
    rejected = (
        make_rejected(evidence_excerpt=PRACTICE, extraction_claim_ref="SRC#0:1"),
        make_rejected(evidence_excerpt=PRACTICE, extraction_claim_ref="SRC#0:2"),
        make_rejected(evidence_excerpt=BIOGRAPHICAL, extraction_claim_ref="SRC#0:3"),
        make_rejected(evidence_excerpt=PRACTICE, extraction_claim_ref="SRC#0:4"),
    )
    assert compose_unmapped_narrative(rejected) == f"{PRACTICE}\n\n{BIOGRAPHICAL}"


def test_a_validation_failed_rejection_never_reaches_the_output() -> None:
    """The mandatory guarantee: a rejection that means "a real governed
    predicate failed to build" must not be republished as if it were
    fine unvalidated prose. Its excerpt text here is unique, so there is
    no eligible twin that could legitimately produce it."""
    rejected = (
        make_rejected(
            reason_code="VALIDATION_FAILED",
            raw_predicate="was held at",
            object_raw="Le Stanze della Fotografia, Venice (2025)",
            evidence_excerpt="His solo show was held at Le Stanze della Fotografia, Venice (2025).",
        ),
    )
    assert compose_unmapped_narrative(rejected) == ""
    assert "Le Stanze della Fotografia" not in compose_unmapped_narrative(rejected)


def test_empty_input_returns_the_empty_string_not_an_error() -> None:
    assert compose_unmapped_narrative(()) == ""


# --- every other real reason code stays out, not just the one named ---

def test_only_the_unmapped_reason_code_is_eligible() -> None:
    for reason_code in (
        "UNKNOWN_PREDICATE",
        "PREDICATE_NOT_YET_SUPPORTED",
        "OBJECT_NOT_LINKED_TO_KNOWN_ENTITY",
        "VALIDATION_FAILED",
    ):
        assert compose_unmapped_narrative(
            (make_rejected(reason_code=reason_code, evidence_excerpt="a real sentence"),)
        ) == "", reason_code
    # ...and an unrecognised future code is excluded too, not passed
    # through by default: this module reads exactly one code.
    assert compose_unmapped_narrative(
        (make_rejected(reason_code="SOME_FUTURE_CODE", evidence_excerpt="a real sentence"),)
    ) == ""


def test_an_ineligible_row_cannot_suppress_the_eligible_row_that_shares_its_text() -> None:
    """The adversarial ordering case, and the reason the module filters
    BEFORE deduplicating. If it deduplicated first, the
    `VALIDATION_FAILED` row (first in the sequence) would claim the slot
    and be dropped by the eligibility filter, taking the legitimate
    `PREDICATE_TEXT_NOT_MAPPED` row's real sentence out of the output
    with it. Both orders are exercised."""
    eligible = make_rejected(evidence_excerpt=PRACTICE)
    ineligible = make_rejected(
        reason_code="VALIDATION_FAILED",
        raw_predicate="was held at",
        evidence_excerpt=PRACTICE,
    )
    assert compose_unmapped_narrative((eligible, ineligible)) == PRACTICE
    assert compose_unmapped_narrative((ineligible, eligible)) == PRACTICE


# --- verbatim means we do not transform it ---

def test_nothing_is_added_removed_or_relabelled_around_an_excerpt() -> None:
    """No bullet marker, no label, no subject prefix, no trailing period
    this function did not receive: the output is the excerpts and the
    separator, nothing else. The excerpt below deliberately carries
    surrounding whitespace -- the point is that even THAT survives, so
    the published string is byte-identical to the one on the record."""
    excerpt = "  His work explores memory, landscape  and  exile.  "
    out = compose_unmapped_narrative((make_rejected(evidence_excerpt=excerpt),))
    assert out == excerpt
    assert out.startswith(" ")
    assert out.endswith("  ")
    assert not out.startswith(("-", "*", "•", "|"))
    assert out.count("\n") == 0
    # Double internal spaces are equally preserved.
    doubled = "He explored  memory."
    assert compose_unmapped_narrative(
        (make_rejected(evidence_excerpt=doubled),)
    ) == doubled


def test_internal_line_breaks_inside_an_excerpt_survive_unchanged() -> None:
    excerpt = "His early work:\n\noil on canvas, then photography."
    assert compose_unmapped_narrative((make_rejected(evidence_excerpt=excerpt),)) == excerpt


def test_order_is_first_appearance_not_sorted() -> None:
    """A deliberate divergence from `render_public_text()`'s sort by
    `atom_id`: the input sequence is already the document/extraction
    order, and sorting paragraphs by a sha-derived claim ref would make
    the output unreadable, which is the thing this module exists to
    avoid. Pinned so a future "make it deterministic like the other one"
    edit has to be a deliberate change."""
    rejected = (
        make_rejected(evidence_excerpt="zebra sentence"),
        make_rejected(evidence_excerpt="apple sentence"),
    )
    assert compose_unmapped_narrative(rejected) == "zebra sentence\n\napple sentence"


# --- deduplication is exact, never fuzzy ---

def test_dedup_is_exact_string_equality_and_never_folds_case_or_whitespace() -> None:
    """Two directions of "not fuzzy", both pinned.

    Case: two sentences differing only in capitalization are two distinct
    sentences; collapsing them would be fuzzy matching, which every
    exact-match function in this subsystem refuses to do."""
    lower = "his work explores memory."
    upper = "His work explores memory."
    assert compose_unmapped_narrative((
        make_rejected(evidence_excerpt=lower),
        make_rejected(evidence_excerpt=upper),
    )) == f"{lower}\n\n{upper}"

    # Whitespace: rows that differ by surrounding whitespace are NOT the
    # same string, so they are NOT collapsed. A deliberate, disclosed
    # consequence of emitting the stored value unmodified -- see the
    # module docstring's deduplication section. Measured on the real
    # Garibaldi document, no real excerpt has surrounding whitespace at
    # all, so this branch is currently unreachable from real data; it is
    # pinned anyway so that a future "normalise before dedup" edit has to
    # be a deliberate, visible change rather than a silent one.
    assert compose_unmapped_narrative((
        make_rejected(evidence_excerpt=PRACTICE),
        make_rejected(evidence_excerpt=f"  {PRACTICE}\n"),
    )) == f"{PRACTICE}\n\n  {PRACTICE}\n"


def test_two_different_sentences_are_never_merged() -> None:
    rejected = (
        make_rejected(evidence_excerpt="He explored memory."),
        make_rejected(evidence_excerpt="He explored landscape."),
    )
    assert compose_unmapped_narrative(rejected) == "He explored memory.\n\nHe explored landscape."


# --- excerpts that carry no text ---

def test_whitespace_only_and_empty_excerpts_contribute_no_empty_paragraph() -> None:
    """Genuinely constructible, not a hypothetical: `RejectedCandidate`
    has no `__post_init__` at all, and `CandidateProposition`'s only
    rejects a FALSY excerpt, so a whitespace-only one builds fine."""
    rejected = (
        make_rejected(evidence_excerpt=PRACTICE),
        make_rejected(evidence_excerpt="   \n\t "),
        make_rejected(evidence_excerpt=""),
        make_rejected(evidence_excerpt=BIOGRAPHICAL),
    )
    assert compose_unmapped_narrative(rejected) == f"{PRACTICE}\n\n{BIOGRAPHICAL}"


def test_all_blank_excerpts_return_the_empty_string() -> None:
    rejected = (
        make_rejected(evidence_excerpt="  "),
        make_rejected(evidence_excerpt=""),
    )
    assert compose_unmapped_narrative(rejected) == ""


# --- grounding: the literal is the one the real producer writes ---

def test_reason_code_constant_is_what_the_real_producer_actually_writes() -> None:
    """Executes the real `build_relation_atoms()` (the only production
    writer of this reason code) with a real unmapped predicate. Needs no
    network: an unmapped predicate is rejected in pass 1, before
    `classify_entity_types()` is reachable, and the entities argument is
    empty so there is nothing to classify even if it were."""
    built, rejected = build_relation_atoms(
        (make_proposition("was born in", ref="SRC#0:9"),),
        (),
        now=NOW,
    )
    assert built == ()
    assert len(rejected) == 1
    assert rejected[0].reason_code == UNMAPPED_PREDICATE_REASON_CODE
    assert rejected[0].raw_predicate == "was born in"


def test_reason_code_constant_matches_the_committed_real_rejection_snapshot() -> None:
    """The committed real-data cross-check: the 8 real Garibaldi rows in
    `00_CONFIG/crawler_snapshots/` name exactly two reason codes, and
    every eligible one of them carries this module's constant. Compared
    field by field, not by searching the file for the string."""
    rows = [
        json.loads(line)
        for line in SNAPSHOT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 8
    codes = {row["reason_code"] for row in rows}
    assert codes == {UNMAPPED_PREDICATE_REASON_CODE, "VALIDATION_FAILED"}
    eligible = [row for row in rows if row["reason_code"] == UNMAPPED_PREDICATE_REASON_CODE]
    assert len(eligible) == 7
    assert compose_unmapped_narrative(()) == ""  # snapshot rows carry no excerpt field


# --- fixture fidelity ---

def test_fixture_mirrors_the_real_dataclass_fields() -> None:
    """The fixtures above must construct the REAL `RejectedCandidate`
    (8 fields, read here from the class itself), not a stand-in with the
    same attribute names, or none of these tests would be testing
    anything."""
    assert tuple(field.name for field in fields(RejectedCandidate)) == (
        "source_id",
        "extraction_claim_ref",
        "raw_predicate",
        "reason_code",
        "detail",
        "subject_raw",
        "object_raw",
        "evidence_excerpt",
    )
    assert make_rejected().reason_code == UNMAPPED_PREDICATE_REASON_CODE


def test_separator_constant_is_a_blank_line_and_is_the_only_structure_added() -> None:
    assert PARAGRAPH_SEPARATOR == "\n\n"
    rejected = (make_rejected(), make_rejected(evidence_excerpt=BIOGRAPHICAL))
    assert compose_unmapped_narrative(rejected).count(PARAGRAPH_SEPARATOR) == 1


def test_candidate_entities_are_never_consulted() -> None:
    """Not a behaviour test but a scope test: this module's input is
    rejections only. An entity of the same name appearing in the same
    batch changes nothing, because nothing reads the entity list."""
    entity = CandidateEntity(
        name="Federico Garibaldi",
        evidence_excerpt=PRACTICE,
        status="DOCUMENTATO",
        source_id="SRC-GARIBALDI",
        evidence_id=("EV-1",),
    )
    assert compose_unmapped_narrative((make_rejected(),)) == PRACTICE
    assert entity.name not in compose_unmapped_narrative((make_rejected(),))