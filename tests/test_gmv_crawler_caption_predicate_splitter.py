"""Tests for `gmv_crawler_caption_predicate_splitter.py` (opencode task 17).

Every fixture below is a LITERAL copy of a real row from the live
`01_RUNTIME/gmv_crawler/rejection_queue.jsonl` (re-read read-only while
writing this file, never re-derived at test time -- a test that re-derives
its own inputs from the live runtime file would fail whenever the queue
grows, which is not what any of these tests is checking). The real rows
this file reproduces, all `reason_code == "PREDICATE_TEXT_NOT_MAPPED"`, all
from the same real Davide Genna catalogue PDF:

| fixture | what it pins |
|---|---|
| the 5 caption cases | the rescue itself (rescued) |
| 2 multi-panel / dimensioni ambientali / ASSOLO 002 | deliberate non-rescue |
| a non-`UNKNOWN_PREDICATE` code | the function's own filter |
| blank subject / blank predicate text | not constructible, not rescued |
| an unknown `extraction_claim_ref` | not rescued, no exception |

The guarantees these tests try to BREAK, deliberately:
  G1 "only an UNKNOWN_PREDICATE rejection whose object_raw is a PURE
      dimension expression is rescued, and it becomes exactly two
      propositions carrying the real text verbatim"
      -> test_all_five_real_caption_cases_produce_exactly_two_verbatim_propositions
  G2 "a non-pure-dimension object is NOT rescued" -- the three real
      non-rescues, plus the adversarial near-misses a loosened regex would
      swallow
      -> test_deliberately_excluded_real_shapes_produce_nothing
      -> test_near_miss_dimension_shapes_are_not_rescued
  G3 "a non-UNKNOWN_PREDICATE rejection is not even considered"
      -> test_other_reason_codes_are_never_considered
  G4 "the input is never mutated and an unmatched ref is not an error"
      -> test_unmatched_extraction_claim_ref_rescues_nothing_without_raising
  G5 "evidence_id/status/truncated_source come from the REAL original
      proposition, never from an invented value" -- the brief's own flagged
      open question
      -> test_provenance_fields_are_copied_from_the_real_original_proposition
  G6 "the regex is exactly as strict as specified" (pinned as a literal,
      so a future loosening fails loudly here)
      -> test_dimension_pattern_rejects_a_trailing_newline_anchors_only_with_fullmatch
  G7 "the claim must arrive with build_atoms()'s FIRST-stage reason code
      (UNKNOWN_PREDICATE), not the PREDICATE_TEXT_NOT_MAPPED the live
      queue actually stores" -- found by running the live proof, which
      produced zero propositions until this was understood
      -> test_real_queue_rows_are_rescued_after_the_real_first_stage_rejection
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "10_API"))

from gmv_crawler_atom_builder import RejectedCandidate  # noqa: E402
from gmv_crawler_caption_predicate_splitter import (  # noqa: E402
    _DIMENSION_WITH_UNIT,
    _base_claim_ref,
    split_medium_dimensions_captions,
)
from gmv_crawler_candidate_extractor import CandidateProposition  # noqa: E402

# The real source locator every one of the 5 real rows carries.
REAL_SOURCE = (
    "/gmv_master_system/01_area35_master/01_artists/genna_davide/10_md_processed_files/"
    "07_career__05_monographs__cataloghi__2025_03_21_davide genna_portfolio lavori al 2025.pdf.md"
)


def _real_proposition(
    subject: str, predicate: str, obj: str, excerpt: str, ref_suffix: str,
    *, status: str = "DOCUMENTATO", evidence_id: tuple[str, ...] = ("EV-DOC-1",),
    truncated: bool = False,
) -> CandidateProposition:
    """The ORIGINAL `CandidateProposition` the real extractor produced --
    the one `extract_candidates()` turned into the RejectedCandidate below.
    Its `status`/`evidence_id`/`truncated_source` are deliberately set to
    values no default would reproduce, so a test can prove they are copied
    rather than filled in."""
    return CandidateProposition(
        subject_raw=subject, predicate=predicate, object_raw=obj,
        evidence_excerpt=excerpt, status=status, source_id=REAL_SOURCE,
        evidence_id=evidence_id, truncated_source=truncated,
        extraction_claim_ref=f"{REAL_SOURCE}#{ref_suffix}",
    )


def _rejected(
    proposition: CandidateProposition, *, reason_code: str = "UNKNOWN_PREDICATE",
) -> RejectedCandidate:
    """Exactly what `build_atom()` returns for that proposition -- same
    fields, same order, built by hand rather than by running the real
    builder, so this file's tests stay independent of `build_atoms()`."""
    return RejectedCandidate(
        source_id=proposition.source_id,
        extraction_claim_ref=proposition.extraction_claim_ref,
        raw_predicate=proposition.predicate,
        reason_code=reason_code,
        detail="fixture",
        subject_raw=proposition.subject_raw,
        object_raw=proposition.object_raw,
        evidence_excerpt=proposition.evidence_excerpt,
    )


# The 5 real caption cases, verbatim from the live rejection queue.
REAL_CAPTION_CASES = (
    (
        "Il bacio", "smalto, unghie, alluminio e carta su tavola", "90 x 60 x 5 cm",
        "***Il bacio*** – 2020 smalto, unghie, alluminio e carta su tavola 90 x 60 x 5 cm",
        "0:1",
    ),
    (
        "Voodoo children", "crossage su tavola", "150 x 150 x 5 cm",
        "### Voodoo children -2024 About a deposition and blue- 2015",
        "0:4",
    ),
    (
        "Voodoo children", "arazzo e collage di tessuti su cartoncino", "215 x 210 cm",
        "### Voodoo children -2024 About a deposition and blue- 2015",
        "0:5",
    ),
    (
        "Nuvole", "metallo, legno e acrilico", "175 x 58 cm",
        "*Nuvole- 2013 metallo, legno e acrilico 175 x 58 cm",
        "0:7",
    ),
    (
        "Chi è la mamma del sole", "smalto e acrilico su tavola", "160 x 110 cm",
        "***Chi è la mamma del sole***- 2014 smalto e acrilico su tavola 160 x 110 cm",
        "0:12",
    ),
)


def test_all_five_real_caption_cases_produce_exactly_two_verbatim_propositions() -> None:
    """G1, over the real data verbatim: 5 claims in, 10 propositions out,
    `medium` first then `dimensions` per claim, and every real field copied
    byte-for-byte. The `object` values are asserted with `in` (not
    equality against a hand-normalized string) precisely because the
    guarantee is "verbatim", and a normalizing implementation would still
    satisfy `in` -- so each side is ALSO asserted to be exactly the
    original."""
    originals = tuple(
        _real_proposition(subject, predicate, obj, excerpt, ref)
        for subject, predicate, obj, excerpt, ref in REAL_CAPTION_CASES
    )
    rejected = tuple(_rejected(proposition) for proposition in originals)

    emitted = split_medium_dimensions_captions(rejected, originals)

    assert len(emitted) == 10
    for index, (subject, predicate, obj, excerpt, ref) in enumerate(REAL_CAPTION_CASES):
        medium, dimensions = emitted[2 * index], emitted[2 * index + 1]
        base = f"{REAL_SOURCE}#{ref}"
        # medium: the raw predicate text, verbatim, as the OBJECT.
        assert medium.predicate == "medium"
        assert medium.object_raw == predicate
        assert medium.extraction_claim_ref == f"{base}#medium"
        # dimensions: the dimension text, verbatim, as the OBJECT.
        assert dimensions.predicate == "dimensions"
        assert dimensions.object_raw == obj
        assert dimensions.extraction_claim_ref == f"{base}#dimensions"
        # Both share the real work's title as subject, and the real quote.
        for proposition in (medium, dimensions):
            assert proposition.subject_raw == subject
            assert proposition.evidence_excerpt == excerpt
            assert proposition.source_id == REAL_SOURCE
    # The two refs of a pair are distinct, so build_atoms()'s
    # sha256(source_id|extraction_claim_ref) atom ids cannot collide.
    assert len({p.extraction_claim_ref for p in emitted}) == 10


@pytest.mark.parametrize(
    ("subject", "predicate", "obj", "reason"),
    [
        # Multi-panel: "cm" on the last part only. Deciding whether it
        # governs every part is a corpus-reading call this module refuses.
        ("Vocazione sognante", "tessuti e carta su tavola", "45 x 55, 45 x 60 cm", "multi-panel"),
        ("Half end of the west", "tessuti e carta su tavola", "150 x 100, 166 x 112 cm", "multi-panel"),
        # "dimensioni ambientali": arguably a valid free-text dimensions
        # value, but a content/governance judgement, not a pattern match.
        ("Fulmine a ciel notturno", "carta, dimensioni ambientali", "dimensioni ambientali", "environmental"),
        # 3-way compound: year + medium + dimensions in one object_raw.
        ("ASSOLO 002", "present", "2014 enamel on paper 150x100 cm", "compound"),
    ],
)
def test_deliberately_excluded_real_shapes_produce_nothing(
    subject: str, predicate: str, obj: str, reason: str,
) -> None:
    """G2's real half: the four shapes the task brief names as DELIBERATELY
    excluded. Each is a literal real queue row. None produces even one
    proposition -- the exclusion is the feature, not a gap, and a future
    edit that starts accepting them must fail here rather than silently
    change what the pipeline asserts about the corpus."""
    original = _real_proposition(subject, predicate, obj, "excerpt", "0:0")
    assert split_medium_dimensions_captions((_rejected(original),), (original,)) == (), reason


@pytest.mark.parametrize(
    "obj",
    [
        "90 x 60",                     # no unit at all
        "90 x 60 cm x 3",              # trailing part is not a dimension
        "90 x 60 cm, alto 80 cm",      # one part of two is a dimension
        "cm",                          # unit with no number
        "90 60 cm",                    # missing the x separator
        "90 x 60 cm²",                 # a squared unit is not this shape
        "90x60cm",                     # no spaces: matched, see below
        "circa 90 x 60 cm",            # a qualifier, not a bare measurement
        "90 x 60 cm (diptych)",        # trailing annotation
    ],
)
def test_near_miss_dimension_shapes_are_not_rescued(obj: str) -> None:
    """G2's adversarial half. These are NOT real queue rows -- they are
    built specifically to find the boundary a loosened pattern would
    cross. `90x60cm` (no spaces) is the one near-miss that IS a real
    dimension and is deliberately accepted, asserted separately below so
    the accepted direction is pinned too, not just the rejected ones."""
    original = _real_proposition("Some Work", "metallo", obj, "excerpt", "0:0")
    emitted = split_medium_dimensions_captions((_rejected(original),), (original,))
    if obj == "90x60cm":
        assert [p.predicate for p in emitted] == ["medium", "dimensions"]
    else:
        assert emitted == (), obj


def test_other_reason_codes_are_never_considered() -> None:
    """G3. A dimension-shaped `object_raw` on a rejection that DID resolve
    to a governed predicate means something else entirely -- e.g. an
    `OBJECT_NOT_INTEGER` failure where the object is a medium string. The
    function re-checks the reason code itself, so this holds even if a
    future caller forgets to filter."""
    original = _real_proposition("Some Work", "metallo", "90 x 60 cm", "excerpt", "0:0")
    for reason_code in ("PREDICATE_NOT_YET_SUPPORTED", "OBJECT_NOT_INTEGER", "VALIDATION_FAILED"):
        assert split_medium_dimensions_captions(
            (_rejected(original, reason_code=reason_code),), (original,),
        ) == (), reason_code


def test_blank_subject_or_predicate_text_is_not_rescued() -> None:
    """A blank `subject_raw`/`raw_predicate` makes the corresponding
    `CandidateProposition` unconstructible (`__post_init__` raises), and a
    "caption" with no technique text is not the shape this module is for.
    Neither must raise here, and neither may be rescued into a
    placeholder."""
    for subject, predicate in (("   ", "metallo"), ("Some Work", "   ")):
        original = _real_proposition("placeholder", "placeholder", "90 x 60 cm", "excerpt", "0:0")
        blank = CandidateProposition(
            subject_raw=subject or "x", predicate=predicate, object_raw="90 x 60 cm",
            evidence_excerpt="excerpt", status="DOCUMENTATO", source_id=REAL_SOURCE,
            evidence_id=("EV-DOC-1",), truncated_source=False,
            extraction_claim_ref=f"{REAL_SOURCE}#0:0",
        )
        # Build the RejectedCandidate by hand: _rejected() copies from a
        # real proposition, and these two are deliberately blank.
        broken = RejectedCandidate(
            source_id=blank.source_id, extraction_claim_ref=blank.extraction_claim_ref,
            raw_predicate=predicate, reason_code="UNKNOWN_PREDICATE", detail="fixture",
            subject_raw=subject, object_raw=blank.object_raw,
            evidence_excerpt=blank.evidence_excerpt,
        )
        assert split_medium_dimensions_captions((broken,), (original,)) == (), (subject, predicate)


def test_unmatched_extraction_claim_ref_rescues_nothing_without_raising() -> None:
    """G4. A rejected candidate whose original proposition is not supplied
    cannot be truthfully rescued (its real `evidence_id` is unreachable),
    so it is skipped -- not rescued into a placeholder, and not a raised
    exception that would destroy the rest of the document. Its rejection
    accounting is the caller's and is untouched either way."""
    original = _real_proposition("Some Work", "metallo", "90 x 60 cm", "excerpt", "0:0")
    assert split_medium_dimensions_captions((_rejected(original),), ()) == ()
    # And the other direction: propositions supplied that were never
    # rejected change nothing.
    assert split_medium_dimensions_captions((), (original,)) == ()


def test_provenance_fields_are_copied_from_the_real_original_proposition() -> None:
    """G5, the brief's own flagged open question. `RejectedCandidate` does
    not carry `evidence_id`/`status`/`truncated_source`, and
    `_validate_evidence_id` rejects an empty tuple, so the only truthful
    source is the real original proposition -- and the values used here
    ("EXTRACTED_UNVERIFIED", a two-element evidence tuple, truncated=True)
    are ones no plausible default or placeholder would produce."""
    original = _real_proposition(
        "Il bacio", "metallo, legno e acrilico", "175 x 58 cm", "excerpt", "0:7",
        status="EXTRACTED_UNVERIFIED", evidence_id=("EV-PASS-1", "EV-PASS-2"), truncated=True,
    )
    emitted = split_medium_dimensions_captions((_rejected(original),), (original,))
    assert len(emitted) == 2
    for proposition in emitted:
        assert proposition.status == "EXTRACTED_UNVERIFIED"
        assert proposition.evidence_id == ("EV-PASS-1", "EV-PASS-2")
        assert proposition.truncated_source is True


def test_input_sequences_are_never_mutated() -> None:
    """A pure function, checked rather than asserted in prose: the two
    sequences handed in come back structurally identical (frozen
    dataclasses, so this is really a check that nothing is rebound or
    consumed), and calling it twice returns equal results."""
    originals = tuple(
        _real_proposition(subject, predicate, obj, excerpt, ref)
        for subject, predicate, obj, excerpt, ref in REAL_CAPTION_CASES
    )
    rejected = tuple(_rejected(proposition) for proposition in originals)
    first = split_medium_dimensions_captions(rejected, originals)
    second = split_medium_dimensions_captions(rejected, originals)
    assert first == second
    assert len(rejected) == 5, "the input rejection tuple must be unchanged in size"
    assert all(isinstance(candidate, RejectedCandidate) for candidate in rejected)


def test_base_claim_ref_strips_only_the_synthetic_suffix() -> None:
    """The orchestrator derives each rescued ref by stripping the synthetic
    suffix. The real ref shape is `"{source_id}#{chunk_id}:{index}"` --
    which itself contains a `#` -- so this pins that only the LAST
    `#`-delimited segment is removed, not the first.

    Also pins the function's actual precondition, found by running it
    rather than by assuming: given a ref that carries NO synthetic suffix
    it strips a real segment instead. That is correct for every call site
    (both the orchestrator and this function only ever apply it to a ref
    this module itself suffixed), and pinning it stops a future caller
    from passing a bare ref here and silently losing a chunk index.
    """
    assert _base_claim_ref("/real/file.md#0:1#medium") == "/real/file.md#0:1"
    assert _base_claim_ref(f"{REAL_SOURCE}#0:12#dimensions") == f"{REAL_SOURCE}#0:12"
    assert _base_claim_ref("CLAIM-1#medium") == "CLAIM-1"
    # No suffix -> the last real segment goes. Not a use case, pinned on
    # purpose so the precondition is visible rather than assumed.
    assert _base_claim_ref("/real/file.md#0:1") == "/real/file.md"


def test_dimension_pattern_rejects_a_trailing_newline_anchors_only_with_fullmatch() -> None:
    """G6. The pattern is applied with `.fullmatch()`, not `.match()`:
    `$` alone would let a trailing newline through, so a `"90 x 60 cm\\n"`
    object would silently become a governed `dimensions` value that no real
    caption ends with. Pinned here because the difference between the two
    match methods is invisible in the pattern itself."""
    assert _DIMENSION_WITH_UNIT.fullmatch("90 x 60 x 5 cm") is not None
    assert _DIMENSION_WITH_UNIT.match("90 x 60 x 5 cm\n") is not None
    assert _DIMENSION_WITH_UNIT.fullmatch("90 x 60 x 5 cm\n") is None
    # And the anchored form the module actually documents, verbatim.
    assert _DIMENSION_WITH_UNIT.pattern == (
        r"^\d+[.,]?\d*\s*[xX×]\s*\d+[.,]?\d*(\s*[xX×]\s*\d+[.,]?\d*)?\s*cm\.?$"
    )


def test_real_queue_rows_are_rescued_after_the_real_first_stage_rejection() -> None:
    """The coupling the live proof found the hard way, pinned so it is
    never re-broken: the live rejection queue stores only the FINAL reason
    code, `PREDICATE_TEXT_NOT_MAPPED` (logged by `build_relation_atoms()`),
    while this module keys on the FIRST-stage code, `UNKNOWN_PREDICATE`
    (returned by `build_atoms()`). The claim is the same one; the queue
    simply never recorded the earlier code -- so a caller must feed it
    `build_atoms()`'s output, never the raw queue row.

    This test therefore drives the 5 real claims through the REAL
    `build_atoms()` (not a hand-built `RejectedCandidate`) and asserts the
    first-stage code is `UNKNOWN_PREDICATE` and that the splitter then
    rescues all 5. It is the end-to-end form of the live proof, and it
    would fail loudly if either builder ever changed which code it
    returns."""
    from gmv_crawler_atom_builder import build_atoms

    originals = tuple(
        _real_proposition(subject, predicate, obj, excerpt, ref)
        for subject, predicate, obj, excerpt, ref in REAL_CAPTION_CASES
    )
    _, first_stage = build_atoms(originals, now="2026-09-17T12:00:00Z")
    assert len(first_stage) == 5
    assert {candidate.reason_code for candidate in first_stage} == {"UNKNOWN_PREDICATE"}

    emitted = split_medium_dimensions_captions(first_stage, originals)
    assert len(emitted) == 10
    assert [p.predicate for p in emitted] == ["medium", "dimensions"] * 5

    # And the real second builder, on the same claims, is what produced the
    # code the live queue actually stores -- the two are different stages
    # of the same claim, which is the whole reason for the assertion above.
    from gmv_crawler_relation_atom_builder import build_relation_atoms

    _, second_stage = build_relation_atoms(
        originals, (), now="2026-09-17T12:00:00Z",
    )
    assert {candidate.reason_code for candidate in second_stage} == {"PREDICATE_TEXT_NOT_MAPPED"}
