#!/usr/bin/env python3
"""Projects gmv_property_signals.py output into governed raw claims
(subject_raw/predicate/object_raw/evidence_excerpt/file_id), validated against
00_CONFIG/GMV_ONTOLOGY_REGISTRY_REALESTATE_v0.1.json, feeding the existing
gmv_evidence_pipeline.resolve_claims()/consolidate_claims() unchanged.

This is a representation layer on top of gmv_property_signals.py's extraction
layer, not a replacement -- same two-level split already established for the
Area35 evidence pipeline (scan/extract -> semantic_extract_batch ->
resolve_claims/consolidate_claims). gmv_property_signals.py is not modified by
this module and does not depend on it.

v1 scope, per explicit user decision 2026-09-28: only `mentions_deadline`
(the validated 14/14 scadenza_presente signal) is projected into a claim.
`rischio_alto` (validated recall only 2/4) stays a consultative field inside
gmv_property_signals.py's own output and is deliberately NOT projected into a
governed claim here -- see the registry's own note_on_scope_v1.

Known limitation, disclosed not hidden: gmv_evidence_pipeline.resolve_claims()
was designed for entity-to-entity predicates (both subject_raw and object_raw
looked up against notion_rows). mentions_deadline's object_raw is a literal
evidence-text string, not an entity name, so it will almost never match an
existing row and resolves as a synthetic "new:<hash>" id (NEW_ENTITY state,
not blocking) rather than a typed literal. Functionally harmless for a single
ATTRIBUTE-class predicate, but not a structurally correct literal-value
representation -- acceptable for v1, not a design endorsement for future
ATTRIBUTE predicates with more of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from gmv_evidence_pipeline import norm  # noqa: E402
from gmv_ontology_check import validate_claim  # noqa: E402

PREDICATE_MENTIONS_DEADLINE = "mentions_deadline"
SUBJECT_ENTITY_TYPE = "PROPERTY"


def load_property_rows(portfolio_root: Path) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Reads <portfolio_root>/<PROPERTY>/OBJECT.yaml (gmv_id/name/aliases) into
    the notion_rows/aliases shape gmv_evidence_pipeline.resolve_claims() already
    expects. As of 2026-09-28, only 1 of 6 real property folders under
    02_IMMOBILI/01_PORTFOLIO/ actually has an OBJECT.yaml (GERMIGNAGA) -- a
    folder without one falls back to using the folder name itself as both id
    and titolo, so resolution still works (at lower identity quality) instead
    of silently dropping 5 of 6 real properties."""
    portfolio_root = portfolio_root.expanduser().resolve()
    rows: list[dict] = []
    aliases: dict[str, str] = {}
    if not portfolio_root.is_dir():
        return {"property": rows}, aliases
    for folder in sorted(p for p in portfolio_root.iterdir() if p.is_dir()):
        object_yaml = folder / "OBJECT.yaml"
        data = None
        if object_yaml.is_file():
            try:
                data = yaml.safe_load(object_yaml.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError, UnicodeError):
                # A malformed OBJECT.yaml for one property must not drop every
                # other property from resolution -- same isolated-failure
                # discipline gmv_evidence_pipeline.extract() already uses per
                # file (a single bad record never aborts the whole batch).
                data = None
        if data is not None:
            gmv_id = data.get("gmv_id") or folder.name
            name = data.get("name") or folder.name
            rows.append({"id": gmv_id, "titolo": name})
            for alias in data.get("aliases") or []:
                aliases[norm(alias)] = norm(name)
        else:
            rows.append({"id": folder.name, "titolo": folder.name})
    return {"property": rows}, aliases


def signal_to_raw_claims(file_id: str, property_subject_raw: str, signal_record: dict, registry: dict) -> list[dict]:
    """Projects one gmv_property_signals.py record into 0 or 1 raw claims.
    Fail-closed: raises (does not silently skip) on an ungoverned predicate or
    domain mismatch, mirroring gmv_evidence_pipeline's own CLAIM_WITHOUT_EVIDENCE
    guard -- a claim without a governed predicate/evidence must never pass
    through quietly."""
    if signal_record.get("signal_status") != "SUCCESS":
        return []
    scadenza = signal_record.get("scadenza_presente") or {}
    if not scadenza.get("value"):
        return []
    excerpt = scadenza.get("evidence_excerpt")
    if not excerpt:
        return []

    validate_claim(SUBJECT_ENTITY_TYPE, PREDICATE_MENTIONS_DEADLINE, registry)
    return [{
        "file_id": file_id,
        "subject_raw": property_subject_raw,
        "predicate": PREDICATE_MENTIONS_DEADLINE,
        "object_raw": excerpt,
        "evidence_excerpt": excerpt,
        "status": "SUPPORTED_BY_ARCHIVE",
    }]
