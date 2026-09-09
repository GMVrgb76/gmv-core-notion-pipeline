#!/usr/bin/env python3
"""Multi-entity Notion candidate fan-out.

Given claims already extracted/consolidated for a primary entity (e.g. an
artist), discovers other entities mentioned (mostra/persona/istituzione/
opera/sponsor), compares each against the real Notion export and proposes
CREATE/UPDATE/KEEP per entity -- dry-run only, never writes to Notion, never
sets Verificata/Pubblicabile, never splits a compound claim object across
multiple fields.

Deliberately does not touch gmv_notion_candidate.py: build_incremental_patch
has no relation-target resolution and no synonym table, and stays the
correct path for a single, manually-specified entity. This module owns its
own routing logic (route_claim) instead of extending that one.

Next steps (not yet implemented, do not assume they exist):
- Web-retrieval pause/resume: when an entity's gate is INSUFFICIENT_EVIDENCE
  because a *pending* relation target isn't a real Notion page yet, this
  is the natural trigger point for the OpenClaw handoff designed earlier
  for gmv run (write pending_requests.json, resume with --web-claims).
  Not wired in here.
- Opera entities are never discovered from claims today: the semantic
  extraction step doesn't isolate individual artworks as distinct claims/
  entities (verified on the real "de profundis" case, where 3 named works
  with measurements exist in the source text but not in the claims). Needs
  a source-text pass, not a fix in this module.
- field_hints (Layer B, atomic property mapping) is intentionally almost
  empty: with the current free-text predicate style, most claims stay in
  the free-text body by design (see build_entity_body). Expand only with
  hints verified against real extracted predicates, not guessed ones --
  today's discovery_hints/relation_hints were already wrong twice on the
  first real run (see git history of this file) before being narrowed to
  exact, direction-aware matches.
- Not yet run against a second real artist; only validated on Paternò
  Castello (3 entities: artista/mostra/persona). Sponsor and istituzione
  paths are covered by unit tests only, never by real data.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from gmv_evidence_pipeline import (
    EvidenceError, compare_entity, gate, norm, notion_field_name, notion_relation_name,
    read_json, required_fields, write_json,
)

RELATION_TYPE_MAP = {
    "mostre": "mostra", "artisti": "artista", "opere": "opera",
    "persone": "persona", "persone_collegate": "persona", "istituzioni": "istituzione",
}
BODY_FALLBACK_SECTIONS = [
    "DOCUMENTAZIONE", "EVIDENZE E FONTI", "EVIDENZE", "DESCRIZIONE",
    "RUOLO NELLA STORIA DI AREA35", "RUOLO NELLA STORIA AREA35", "CONTRIBUTO",
]


def load_page_templates(path: Path) -> dict:
    return read_json(path, {})


def _predicate_matches(predicate: str, hints: list[str]) -> bool:
    """Exact match only, after normalization: a substring test would let a
    short hint ("is the author of") silently match a longer, distinct
    predicate ("is the author of the text for") it was never meant to cover."""
    p = norm(predicate)
    return any(norm(h) == p for h in hints)


def _best_hint(name: str, name_claims: list[dict], hints: dict[str, list[dict]]) -> str | None:
    """Longest matching hint phrase wins, so a more specific hint (persona's
    "is the author of the text for") is preferred over a shorter, broader one
    that happens to be a substring of it (mostra's "is the author of") instead
    of the two being treated as an unresolved tie. Each hint declares which
    side of the claim (subject or object) is the entity being proposed: "Myriam
    Zerbi is the author of the text for the exhibition" proposes Myriam Zerbi
    (the subject), not "the exhibition" (the object)."""
    n = norm(name)
    best_type, best_len = None, 0
    for typ, entries in hints.items():
        for entry in entries:
            hint_pred, anchor = entry["predicate"], entry["anchor"]
            if len(hint_pred) <= best_len:
                continue
            for claim in name_claims:
                if norm(str(claim.get(anchor, ""))) != n:
                    continue
                if _predicate_matches(claim.get("predicate", ""), [hint_pred]):
                    best_type, best_len = typ, len(hint_pred)
    return best_type


def discover_entities(claims: list[dict], rows: dict, page_templates: dict,
                       primary_name: str) -> list[dict]:
    """Every non-primary name mentioned as subject/object of a claim, classified as:
    - matched_existing_row: name matches a real Notion row (type is certain) -> generate.
    - hinted_not_confirmed: no existing match, but a direction-aware discovery_hint
      proposes one type -> generate, tagged unconfirmed for human review.
    - no_signal: no match, no hint -> listed only, never generated.
    """
    primary_norm = norm(primary_name)
    mentions: dict[str, list[dict]] = {}
    for claim in claims:
        for field in ("subject", "object"):
            name = str(claim.get(field, "")).strip()
            if not name or norm(name) == primary_norm:
                continue
            mentions.setdefault(name, []).append(claim)

    rows_by_norm: dict[str, tuple[str, dict]] = {}
    for typ, typ_rows in rows.items():
        for row in typ_rows:
            rows_by_norm.setdefault(norm(row.get("titolo", "")), (typ, row))

    hints = page_templates.get("discovery_hints", {})
    discovered = []
    for name, name_claims in mentions.items():
        claim_ids = [c.get("claim_id") for c in name_claims]
        match = rows_by_norm.get(norm(name))
        if match:
            typ, row = match
            discovered.append({"name": name, "entity_type": typ, "type_source": "matched_existing_row",
                               "notion_id": row.get("id"), "claim_ids": claim_ids, "generate": True})
            continue
        proposed = _best_hint(name, name_claims, hints)
        if proposed:
            discovered.append({"name": name, "entity_type": proposed,
                               "type_source": "hinted_not_confirmed", "notion_id": None,
                               "claim_ids": claim_ids, "generate": True})
        else:
            discovered.append({"name": name, "entity_type": None, "type_source": "no_signal",
                               "notion_id": None, "claim_ids": claim_ids, "generate": False})
    return discovered


def _relation_target(name: str, target_type: str, rows: dict, discovered_index: dict[str, dict]) -> dict:
    """Resolve a relation target to an existing Notion id, or to a pending
    marker pointing at the candidate this same run proposes for it. Never
    fabricates an id: an unresolved target stays unresolved and gate-blocking."""
    for row in rows.get(target_type, []):
        if norm(row.get("titolo", "")) == norm(name):
            return {"resolved": True, "notion_id": row.get("id"), "name": name}
    entry = discovered_index.get(norm(name))
    if entry and entry.get("entity_type") == target_type:
        return {"resolved": False, "pending_entity": name, "pending_type": target_type}
    return {"resolved": False, "pending_entity": name, "pending_type": None}


def route_claim(claim: dict, entity_type: str, page_templates: dict, rows: dict,
                 discovered_index: dict[str, dict]) -> dict:
    """Layer A (relation, matched against a known/candidate entity) takes
    priority over Layer B (explicit, conservative predicate->campo mapping,
    never for compound objects). Anything unmatched falls through to the
    free-text body -- never lost, never guessed."""
    spec = page_templates.get("entita", {}).get(entity_type, {})
    predicate = str(claim.get("predicate", ""))
    object_text = str(claim.get("object", ""))

    for rel_key, entries in spec.get("relation_hints", {}).items():
        for entry in entries:
            if not _predicate_matches(predicate, [entry["predicate"]]):
                continue
            target_type = RELATION_TYPE_MAP.get(rel_key, rel_key)
            target_name = str(claim.get(entry["anchor"], ""))
            target = _relation_target(target_name, target_type, rows, discovered_index)
            return {"layer": "relation", "relation_key": rel_key, "target": target}

    for hint_pred, campo_key in spec.get("field_hints", {}).items():
        if _predicate_matches(predicate, [hint_pred]):
            return {"layer": "field", "campo": campo_key, "value": object_text}

    return {"layer": "body"}


def build_entity_patch(name: str, entity_type: str, claims: list[dict], rows: dict,
                        config: dict, page_templates: dict, discovered_index: dict[str, dict]) -> dict:
    status, existing = compare_entity(name, entity_type, rows)
    existing_campi = (existing or {}).get("campi", {})
    existing_relazioni = (existing or {}).get("relazioni", {})
    operations, gate_claims = [], []
    for claim in claims:
        route = route_claim(claim, entity_type, page_templates, rows, discovered_index)
        if route["layer"] == "relation":
            relation_key, target = route["relation_key"], route["target"]
            property_name = notion_relation_name(config, entity_type, relation_key)
            # No relation-writer exists anywhere in this codebase today --
            # Notion relation properties are full-list-replace, and nothing
            # here merges against an existing relation list. RELATE always
            # stays CONFLICT, resolved or not, exactly like
            # build_incremental_patch's own unconditional relation CONFLICT
            # in gmv_notion_candidate.py.
            if property_name is None:
                reason = "RELATION_NOT_IN_ENTITY_SCHEMA"
            elif not target["resolved"]:
                reason = "RELATION_TARGET_ID_NOT_RESOLVED"
            else:
                reason = "RELATION_WRITE_NOT_SUPPORTED"
            operations.append({"action": "CONFLICT", "claim_id": claim.get("claim_id"),
                               "property": property_name, "relation": relation_key,
                               "reason": reason, "target": target})
            gate_claims.append({"predicate": relation_key,
                                "status": claim.get("status") if target["resolved"] else "MISSING"})
        elif route["layer"] == "field":
            campo_key = route["campo"]
            property_name = notion_field_name(config, entity_type, campo_key)
            if property_name is None:
                operations.append({"action": "CONFLICT", "claim_id": claim.get("claim_id"),
                                   "reason": "FIELD_NOT_IN_ENTITY_SCHEMA"})
                claim_status = "MISSING"
            else:
                # Never blindly overwrite: an entity discovered as
                # already-existing (matched_existing_row) can already carry a
                # real, different value for this field. KEEP silently if
                # unchanged, ADD only if genuinely empty, otherwise CONFLICT
                # (never applied) -- more conservative than
                # build_incremental_patch's own UPDATE-on-mismatch for
                # properties, a deliberate choice while this discovery path
                # is still only validated on one real artist.
                old_value = existing_campi.get(campo_key)
                if old_value in (None, "", [], {}):
                    operations.append({"action": "ADD", "claim_id": claim.get("claim_id"),
                                       "property": property_name, "value": route["value"]})
                    claim_status = claim.get("status")
                elif str(old_value) == str(route["value"]):
                    claim_status = claim.get("status")
                else:
                    operations.append({"action": "CONFLICT", "claim_id": claim.get("claim_id"),
                                       "property": property_name, "reason": "FIELD_VALUE_MISMATCH"})
                    claim_status = "MISSING"
            gate_claims.append({"predicate": campo_key, "status": claim_status})
    required = required_fields(config, entity_type) if entity_type in config.get("entita", {}) else set()
    final_gate = gate(status, gate_claims, required)
    # AMBIGUOUS (more than one existing row with this title) must never be
    # treated as "no existing row" -- a naive existing-is-None check would
    # propose CREATE and risk a duplicate page; leave operation undecided,
    # the REVIEW_REQUIRED gate above already blocks it from being published.
    operation = None if status == "AMBIGUOUS" else ("CREATE" if existing is None else "UPDATE")
    keep = {"properties": {}, "relations": {}}
    if entity_type in config.get("entita", {}):
        spec = config["entita"][entity_type]
        for key, meta in spec.get("campi", {}).items():
            keep["properties"][meta["notion"]] = existing_campi.get(key)
        for key, meta in spec.get("relazioni", {}).items():
            keep["relations"][meta["notion"]] = existing_relazioni.get(key, [])
    return {"entity_type": entity_type.upper(), "name": name, "notion_status": status,
            "operation": operation, "existing_notion_id": (existing or {}).get("id"),
            "keep": keep, "operations": operations, "gate": final_gate,
            # Multi-entity body routing (build_entity_body) is a single
            # fallback section, not the section-routed, semantically-checked
            # logic candidate.py's attach_body_adapter uses -- always require
            # manual review before any body text from this path is published.
            "body_gate": "BODY_REVIEW_REQUIRED", "dry_run": True}


def build_entity_body(name: str, entity_type: str, claims: list[dict], page_templates: dict) -> str:
    """Deterministic, no reinterpretation: every claim about this entity
    becomes one bullet, with source, under a single fallback section already
    present in the real template for this type."""
    spec = page_templates.get("entita", {}).get(entity_type, {})
    sections = [s["titolo"] for s in spec.get("struttura_pagina", [])]
    fallback = next((s for s in BODY_FALLBACK_SECTIONS if s in sections), sections[0] if sections else "NOTE")
    lines = [f"## {fallback}"]
    for claim in claims:
        lines.append(f"- {claim.get('subject')} — {claim.get('predicate')}: {claim.get('object')} "
                     f"(status: {claim.get('status')}, fonti: {', '.join(claim.get('source_file_ids', []))})")
    return "\n".join(lines) + "\n"


def claims_for_entity(claims: list[dict], name: str) -> list[dict]:
    n = norm(name)
    return [c for c in claims if norm(str(c.get("subject", ""))) == n or norm(str(c.get("object", ""))) == n]


def write_entity_bundle(run_dir: Path, patch: dict, body_markdown: str, claims: list[dict]) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", patch["name"]).strip("_") or "unnamed"
    bundle = run_dir / "entities" / f"{patch['entity_type'].lower()}__{safe_name}"
    write_json(bundle / "entity.json", {"entity_type": patch["entity_type"], "name": patch["name"]})
    write_json(bundle / "claims.json", claims)
    write_json(bundle / "PATCH.json", patch)
    (bundle / "body.proposed_markdown").write_text(body_markdown, encoding="utf-8")
    # NOTION_PATCH.json + NOTION_PAYLOAD.json: same shape gmv_notion_candidate.py
    # writes, so this bundle is publishable via the existing, unmodified
    # gmv_notion_publish.py -- load_bundle() only ever looks for these two
    # filenames, never PATCH.json (kept above for this module's own callers/tests).
    publish_patch = {**patch, "body": {"proposed_markdown": body_markdown}}
    write_json(bundle / "NOTION_PATCH.json", publish_patch)
    write_json(bundle / "NOTION_PAYLOAD.json", {"gate": patch["gate"]})
    lines = [f"# {patch['name']} ({patch['entity_type']})", "",
             f"Notion status: `{patch['notion_status']}`  ", f"Gate: `{patch['gate']}`  ",
             f"Operazioni proposte: {len(patch['operations'])}", ""]
    (bundle / "EVIDENCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bundle


def run_multi_candidate(claims: list[dict], rows: dict, config: dict, page_templates: dict,
                        primary_name: str, primary_type: str, run_dir: Path) -> dict:
    discovered = discover_entities(claims, rows, page_templates, primary_name)
    discovered_index = {norm(d["name"]): d for d in discovered if d["generate"]}
    discovered_index[norm(primary_name)] = {"name": primary_name, "entity_type": primary_type}

    priority = page_templates.get("generation_priority", [primary_type])
    entities = [{"name": primary_name, "entity_type": primary_type, "type_source": "primary", "generate": True}]
    entities += [d for d in discovered if d["generate"]]
    entities.sort(key=lambda e: priority.index(e["entity_type"]) if e["entity_type"] in priority else len(priority))

    results, patches = [], []
    for entity in entities:
        spec = page_templates.get("entita", {}).get(entity["entity_type"], {})
        requires = spec.get("requires_existing_link", [])
        if requires:
            linked = any(o.get("action") == "RELATE" and o["target"]["resolved"]
                        for p in patches for o in p["operations"]
                        if p["entity_type"].lower() in requires)
            if not linked:
                results.append({"name": entity["name"], "entity_type": entity["entity_type"],
                                "skipped": "REQUIRES_EXISTING_LINK_NOT_FOUND"})
                continue
        entity_claims = claims_for_entity(claims, entity["name"])
        patch = build_entity_patch(entity["name"], entity["entity_type"], entity_claims,
                                   rows, config, page_templates, discovered_index)
        body = build_entity_body(entity["name"], entity["entity_type"], entity_claims, page_templates)
        bundle = write_entity_bundle(run_dir, patch, body, entity_claims)
        patches.append(patch)
        results.append({"name": entity["name"], "entity_type": entity["entity_type"],
                        "type_source": entity["type_source"], "gate": patch["gate"],
                        "notion_status": patch["notion_status"], "bundle": str(bundle)})

    unclassified = [d for d in discovered if not d["generate"]]
    return {"entities": results, "unclassified_mentions": unclassified}


def main() -> int:
    p = argparse.ArgumentParser(description="Multi-entity Notion candidate fan-out (dry-run only)")
    p.add_argument("--claims", type=Path, required=True)
    p.add_argument("--rows", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--page-templates", type=Path, required=True)
    p.add_argument("--primary-entity-name", required=True)
    p.add_argument("--primary-entity-type", required=True)
    p.add_argument("--run-dir", type=Path, required=True)
    a = p.parse_args()
    try:
        doc = read_json(a.claims, {})
        claims = doc.get("claims", doc) if isinstance(doc, dict) else doc
        output = run_multi_candidate(
            claims, read_json(a.rows, {}), read_json(a.config, {}), load_page_templates(a.page_templates),
            a.primary_entity_name, a.primary_entity_type, a.run_dir,
        )
        print(json.dumps(output, ensure_ascii=False, indent=2)); return 0
    except EvidenceError as exc:
        print(f"multi_candidate: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
