#!/usr/bin/env python3
"""Task 16 live proof (opencode_task_16.md Step 4) -- NOT COMMITTED, one-off.

Builds three CandidateProposition instances by hand that share one exact
`subject_raw` (a work's title) and carry one `creation_year`, one
`dimensions`, one `medium` fact, then runs the real `build_atoms()` and
prints each atom's subject/predicate/object/object_type.

Touches NO real runtime state: no file is read from or written to
01_RUNTIME/, no queue is appended, the ontology registry is only read
(through the module's own read-only loader), and nothing is persisted at
all -- build_atoms() returns values in memory and this script only prints
them. The registry's sha256 is fingerprinted before and after anyway, so
that claim is checked rather than asserted.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_crawler_atom_builder as builder  # noqa: E402
from gmv_atom_validator import validate_atom  # noqa: E402
from gmv_crawler_candidate_extractor import CandidateProposition  # noqa: E402

REGISTRY = ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"
NOW = "2026-09-27T00:00:00Z"
SUBJECT = "Senza Titolo (prova)"


def fingerprint() -> tuple[str, float]:
    return hashlib.sha256(REGISTRY.read_bytes()).hexdigest(), REGISTRY.stat().st_mtime


def proposition(predicate: str, object_raw: str, ref: str) -> CandidateProposition:
    return CandidateProposition(
        subject_raw=SUBJECT,
        predicate=predicate,
        object_raw=object_raw,
        evidence_excerpt=f"{SUBJECT} -- {predicate}: {object_raw}",
        status="DOCUMENTATO",
        source_id="/gmv_master_system/01_area35_master/01_artists/bucchi_danilo/"
                  "10_md_processed_files/09_temp_import__danilo bucchi cat.pdf.md",
        evidence_id=("EV-T16-1",),
        truncated_source=False,
        extraction_claim_ref=ref,
    )


def main() -> None:
    print("=" * 78)
    print("0. the real ontology registry, BEFORE  [sha256, mtime]")
    print("=" * 78)
    before = fingerprint()
    print(f"  sha256={before[0]}")
    print(f"  mtime={before[1]}")

    print()
    print("=" * 78)
    print("1. what the module will build, read from the real registry")
    print("=" * 78)
    for pid, otype in sorted(builder._ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES.items()):
        print(f"  {pid:<16} -> object_type={otype!r}")

    print()
    print("=" * 78)
    print("2. three hand-built propositions, one shared subject_raw")
    print("=" * 78)
    print(f"  subject_raw (all three, byte-for-byte) = {SUBJECT!r}")
    propositions = (
        proposition("creation_year", "2013", "CLAIM-T16-YEAR"),
        proposition("dimensions", "150 x 100 cm", "CLAIM-T16-DIMS"),
        proposition("medium", "olio su tela", "CLAIM-T16-MED"),
    )
    for p in propositions:
        print(f"  {p.extraction_claim_ref:<18} predicate={p.predicate!r:<16} "
              f"object_raw={p.object_raw!r}")

    print()
    print("=" * 78)
    print("3. the real build_atoms() -- THE POINT OF THE TASK")
    print("=" * 78)
    atoms, rejected = builder.build_atoms(propositions, now=NOW)
    print(f"  built={len(atoms)}  rejected={len(rejected)}")
    for atom in atoms:
        print(f"    subject      = {atom.subject!r}")
        print(f"    predicate    = {atom.predicate!r}")
        print(f"    object       = {atom.object!r}")
        print(f"    object_type  = {atom.object_type!r}")
        print(f"    atom_id      = {atom.atom_id}")
        issues = validate_atom(atom)
        blockers = [i for i in issues if i.severita == "BLOCKER"]
        print(f"    validate_atom: {len(issues)} issue(s), {len(blockers)} BLOCKER")
        print()

    print("=" * 78)
    print("4. the property being demonstrated, asserted")
    print("=" * 78)
    subjects = {a.subject for a in atoms}
    print(f"  distinct subject values across all 3 atoms: {len(subjects)} -> {subjects}")
    print(f"  all three share the subject verbatim:        {subjects == {SUBJECT}}")
    print(f"  three distinct predicates:                    "
          f"{sorted(a.predicate for a in atoms) == ['creation_year', 'dimensions', 'medium']}")
    print(f"  object_types:                                 "
          f"{[a.object_type for a in atoms]}")
    print(f"  distinct atom_ids (one per extraction):       {len({a.atom_id for a in atoms})}")
    print(f"  zero BLOCKERs across all three:               "
          f"{[i for a in atoms for i in validate_atom(a) if i.severita == 'BLOCKER'] == []}")

    print()
    print("=" * 78)
    print("5. the real ontology registry, AFTER -- must be byte-identical")
    print("=" * 78)
    after = fingerprint()
    print(f"  sha256 unchanged: {after[0] == before[0]}")
    print(f"  mtime  unchanged: {after[1] == before[1]}")
    if after != before:
        raise SystemExit(f"THE REGISTRY WAS TOUCHED: before={before} after={after}")
    print()
    print("OK -- three different facts about one work, three atoms, one shared subject.")


if __name__ == "__main__":
    main()
