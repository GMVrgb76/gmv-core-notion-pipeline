#!/usr/bin/env python3
"""Real-estate fact extraction via NuExtract3, built on top of the generic
gmv_evidence_pipeline.nuextract_extract(). Implements the SOGGETTO/PREDICATO/
OGGETTO fact shape defined in 00_CONFIG/GMV_ONTOLOGY_REGISTRY_REALESTATE_v0.1.json's
`fact_extraction_contract` (user proposal, 2026-09-28): one uniform template
across every document type (no per-document-type template, no separate
classification pass -- `ha_tipo_documento` is just one of the extracted facts),
with the model's own `predicato` field constrained by an enum built FROM the
registry, so an ungoverned predicate cannot even be emitted, let alone silently
governed -- reuse-before-invention enforced mechanically, not just by convention.

Every fact is defensively re-validated against the registry after parsing
(never trust that enum-constrained decoding alone is airtight -- this project's
own history today includes NuExtract3 not respecting a required-field
constraint without explicit `format`). A fact with an ungoverned predicate is
dropped, not silently kept or coerced.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gmv_evidence_pipeline import nuextract_extract  # noqa: E402
from gmv_ontology_check import predicate_is_governed  # noqa: E402

DEFAULT_AMBITO_ENUM = ["immobile", "unita", "quota_individuale", "intero_condominio", "conto_corrente"]
STATO_EVIDENZA_ENUM = ["esplicito", "inferito"]

# qualifiers carried through resolve_claims()/consolidate_claims() unchanged (both
# already copy/forward an unrecognized "qualifiers" key -- no changes needed there).
QUALIFIER_FIELDS = ("valuta", "ambito", "pagina", "data_documento", "competenza_da", "competenza_a")


def build_fact_template(registry: dict) -> dict:
    """Builds the NuExtract3 template from the registry's own governed predicate
    list -- never hardcoded, so a newly-promoted predicate is usable the moment
    it's added to the registry, with no second place to update."""
    predicate_ids = sorted(p["predicate_id"] for p in registry["predicates"])
    ambito_enum = registry.get("proposed_vocabulary_v0_1", {}).get("ambito_enum", DEFAULT_AMBITO_ENUM)
    return {
        "fatti": [{
            "soggetto": "verbatim-string",
            "predicato": predicate_ids,
            "oggetto": "verbatim-string",
            "valuta": "verbatim-string",
            "ambito": ambito_enum,
            "pagina": "integer",
            "testo_evidenza": "verbatim-string",
            "data_documento": "date-time",
            "competenza_da": "date-time",
            "competenza_a": "date-time",
            "stato_evidenza": STATO_EVIDENZA_ENUM,
        }]
    }


def extract_facts(record: dict, registry: dict, *, endpoint: str, model: str = "numind/nuextract3:q4_k_m",
                  timeout: int = 120, num_predict: int = 4096) -> dict:
    """Runs the fact template against one already-extracted document record.
    Returns {"file_id", "facts": [...governed facts...], "rejected_facts": [...],
    "_runtime": {...}}. `rejected_facts` is never silently dropped from the
    return value -- a caller that ignores it is choosing to, not forced to.

    num_predict defaults higher (4096) than nuextract_extract()'s own default
    (2048) -- the fact envelope is verbose (11 fields per fact), and 2048 was
    live-observed to truncate on a real document (see project memory)."""
    template = build_fact_template(registry)
    result = nuextract_extract(record, endpoint=endpoint, model=model, template=template, timeout=timeout, num_predict=num_predict)
    raw_facts = result["extracted"].get("fatti", [])
    facts, rejected = [], []
    for fact in raw_facts if isinstance(raw_facts, list) else []:
        if not isinstance(fact, dict) or not predicate_is_governed(fact.get("predicato"), registry):
            rejected.append(fact)
            continue
        facts.append(fact)
    return {"file_id": record["file_id"], "facts": facts, "rejected_facts": rejected,
            "truncated_source": result.get("truncated_source", False), "_runtime": result.get("_runtime", {})}


def fact_to_raw_claim(fact: dict, file_id: str) -> dict | None:
    """Projects one governed fact into the raw-claim shape resolve_claims()/
    consolidate_claims() already expect (both unchanged). Returns None (not a
    claim) if the fact is missing a mandatory field -- never emits a claim
    without a real subject/predicate/object/evidence quadruple, same discipline
    as gmv_property_claims.signal_to_raw_claims()."""
    soggetto, predicato, oggetto, testo = fact.get("soggetto"), fact.get("predicato"), fact.get("oggetto"), fact.get("testo_evidenza")
    if not soggetto or not predicato or not oggetto or not testo:
        return None
    status = "INFERRED" if fact.get("stato_evidenza") == "inferito" else "SUPPORTED_BY_ARCHIVE"
    qualifiers = {k: fact[k] for k in QUALIFIER_FIELDS if fact.get(k) not in (None, "")}
    return {
        "file_id": file_id,
        "subject_raw": soggetto,
        "predicate": predicato,
        "object_raw": oggetto,
        "evidence_excerpt": testo,
        "status": status,
        "qualifiers": qualifiers,
    }


def facts_to_raw_claims(facts: list[dict], file_id: str) -> list[dict]:
    return [claim for fact in facts if (claim := fact_to_raw_claim(fact, file_id)) is not None]
