#!/usr/bin/env python3
"""Read-only Notion comparison, gate, Evidence Bundle and dry-run payload."""
from __future__ import annotations
import argparse, json
import re
from pathlib import Path
from gmv_evidence_pipeline import compare_entity, gate, load_index, notion_payload, required_fields, summarize_web_verification, write_evidence_bundle, norm
__all__ = ["compare_entity", "gate", "notion_payload", "required_fields", "write_evidence_bundle"]

SUPPORTED_CLAIM_STATUS = {"SUPPORTED_BY_ARCHIVE", "VERIFIED", "CONFIRMED", "VALID"}
SOURCE_METADATA_PREDICATES = {"is the subject of", "is a", "has type", "is the source of"}
THEME_PREDICATES = {"has themes", "themes", "theme", "research", "practice", "focus", "explores", "investigates"}
CONCEPTS = {"storytelling": "narrazione", "cinema": "film", "photography": "fotografia", "photographer": "fotografia", "fotografo": "fotografia", "identity": "identità", "memory": "memoria", "landscape": "paesaggio", "sea": "mare", "mare": "mare", "memoria": "memoria", "paesaggio": "paesaggio", "fotografia": "fotografia", "identità": "identità", "narrazione": "narrazione", "film": "film", "filmmaker": "film", "video": "video"}

def _concept_list(value):
    return [x.strip() for x in re.split(r"[,;•|/]", str(value or "")) if x.strip()]

def _covered_concept(concept, body):
    canonical = CONCEPTS.get(concept.lower(), concept.lower())
    variants = {k for k, v in CONCEPTS.items() if v == canonical} | {canonical}
    return any(v in body.lower() for v in variants)

BODY_SECTIONS = ("IDENTITÀ", "PROFILO ARTISTICO", "BIOGRAFIA", "RELAZIONE CON AREA35", "DOCUMENTAZIONE / FONTI", "STATO EDITORIALE")

def _body_text(claim):
    subject, predicate, obj = str(claim.get("subject", "")).strip(), str(claim.get("predicate", "")).strip(), str(claim.get("object", "")).strip()
    p = predicate.lower()
    if p in {"said", "states", "stated", "says"}: return f"{subject} dichiara: {obj}"
    if p in {"has themes", "themes", "theme"}: return f"Temi documentati: {obj}"
    if p in {"works with", "uses", "medium", "media"}: return f"Medium / tecniche documentate: {obj}"
    return f"{subject} — {predicate}: {obj}" if subject and predicate else (obj or "")

def _body_destination(claim):
    p = str(claim.get("predicate", "")).lower(); text = f"{p} {claim.get('object','')}".lower()
    if any(k in p for k in ("born", "birth", "nationality", "birthplace", "place of birth", "anno_nascita", "luogo_nascita")): return "IDENTITÀ", None
    if any(k in p for k in ("studied", "educated", "graduated", "moved", "lives", "based", "career", "biography")): return "BIOGRAFIA", None
    if "area35" in text and any(k in text for k in ("represented", "collaborat", "exhibited", "curated", "produced", "supported", "relationship")): return "RELAZIONE CON AREA35", None
    if any(k in p for k in ("theme", "themes", "research", "practice", "focus", "explores", "investigates", "concern")): return "PROFILO ARTISTICO", "La ricerca"
    if any(k in p for k in ("medium", "media", "technique", "material", "language", "style", "works with", "uses")): return "PROFILO ARTISTICO", "Linguaggio e poetica"
    if any(k in p for k in ("said", "states", "stated", "describes", "according to", "critic", "interpret")): return "PROFILO ARTISTICO", "Letture / dichiarazioni documentate"
    return "DOCUMENTAZIONE / FONTI", None

def _body_source(claim, file_index):
    source_ids = claim.get("source_file_ids") or []
    source_id = claim.get("source_id") or claim.get("source") or claim.get("file_id") or (source_ids[0] if source_ids else None)
    row = file_index.get(str(source_id), {}) if source_id else {}
    paths = row.get("paths", []) if isinstance(row, dict) else []
    return str(source_id).strip() if source_id else None, (paths[0] if paths else None)

def build_artist_body_candidates(claims, existing_body, file_index):
    out = []
    for i, claim in enumerate(claims, 1):
        section, subsection = _body_destination(claim); text = _body_text(claim); sid, spath = _body_source(claim, file_index)
        excerpt = claim.get("excerpt") or (claim.get("source_excerpts") or [None])[0]
        predicate = str(claim.get("predicate", "")).strip().lower(); semantic_class = "SOURCE_METADATA" if predicate in SOURCE_METADATA_PREDICATES else "EDITORIAL_KNOWLEDGE"; delta_text = text
        if semantic_class == "SOURCE_METADATA": action, reason = "KEEP_EVIDENCE", "Source metadata retained in evidence/provenance layer; not editorial body content."
        elif str(claim.get("status", "")).upper() in {"UNVERIFIED", "DISPUTED", "CONFLICTING", "MISSING"}: action, reason = "HOLD", "Claim requires epistemic review before editorial publication."
        elif predicate in THEME_PREDICATES:
            concepts = _concept_list(claim.get("object")); locations = {"riyadh", "venice", "riyadh", "venezia"}; editorial = [c for c in concepts if c.lower() not in locations]; new = [c for c in editorial if not _covered_concept(c, existing_body or "")]
            if not new: action, reason = ("KEEP_CONTEXT" if any(c.lower() in locations for c in concepts) else "KEEP_SEMANTIC"), "All concepts are already covered by the canonical body; locations remain contextual."
            elif len(new) < len(editorial): action, delta_text, reason = "PARTIAL_ADD", ", ".join(new), "Only semantically new concepts are appended; existing concepts are preserved."
            elif not spath: action, reason = "HOLD", "No deterministic canonical source locator."
            else: action, reason = "ADD", "Supported claim has a valid canonical body destination."
        elif text and text.lower() in (existing_body or "").lower(): action, reason = "KEEP_SEMANTIC", "Equivalent information already present in canonical body."
        elif not spath: action, reason = "HOLD", "No deterministic canonical source locator."
        else: action, reason = "ADD", "Supported claim has a valid canonical body destination."
        out.append({"claim_id": claim.get("claim_id") or claim.get("id") or f"CLAIM_{i:04d}", "predicate": claim.get("predicate"), "semantic_class": semantic_class, "destination": section, "section": section, "subsection": subsection, "action": action, "subject": claim.get("subject"), "object": claim.get("object"), "text": text, "delta_text": delta_text, "source_id": sid, "source_path": spath, "excerpt": excerpt, "reason": reason})
    counts = {a: sum(x["action"] == a for x in out) for a in ("KEEP", "KEEP_SEMANTIC", "KEEP_CONTEXT", "KEEP_EVIDENCE", "ADD", "PARTIAL_ADD", "UPDATE", "CONFLICT", "HOLD")}
    return {"adapter": "ARTISTA_BODY_V1", "mode": "incremental", "dry_run": True, "counts": counts, "candidates": out}

def render_body_patch_markdown(body_candidates):
    grouped = {}
    for c in body_candidates["candidates"]:
        if c["action"] == "ADD": rendered = c["text"]
        elif c["action"] == "PARTIAL_ADD": rendered = render_partial_add(c)
        else: continue
        grouped.setdefault((c["section"], c["subsection"]), []).append(rendered)
    lines = []
    for section in BODY_SECTIONS:
        keys = [k for k in grouped if k[0] == section]
        if not keys: continue
        lines.append(f"## {section}")
        for key in keys:
            if key[1]: lines.append(f"### {key[1]}")
            lines.extend(f"- {text}" for text in grouped[key])
    return "\n".join(lines).strip()

def render_partial_add(candidate):
    """Render only the semantic delta, using destination context."""
    section = str(candidate.get("section", "")).strip()
    subsection = str(candidate.get("subsection", "")).strip()
    delta = str(candidate.get("delta_text", "")).strip()
    if not delta: return ""
    if section == "PROFILO ARTISTICO" and subsection == "La ricerca":
        return f"Nei materiali esaminati emerge inoltre il {delta} come elemento ricorrente della ricerca."
    if subsection:
        return f"Nei materiali esaminati emerge inoltre {delta} nella sezione {subsection}."
    return f"Nei materiali esaminati emerge inoltre {delta} nella sezione {section}."

def attach_body_adapter(patch, claims, existing_body, file_index):
    body = build_artist_body_candidates(claims, existing_body, file_index)
    patch["body"] = {"existing": "KEEP", "strategy": "incremental_append_only", "candidate_analysis": body, "proposed_markdown": render_body_patch_markdown(body)}
    patch["claim_routing"] = {"properties_relations": [x for x in patch.get("operations", []) if x.get("action") in {"ADD", "UPDATE"}], "body": body["candidates"]}
    patch["body_gate"] = "BODY_PATCH_READY" if (body["counts"]["ADD"] + body["counts"]["PARTIAL_ADD"]) and not body["counts"]["CONFLICT"] else "BODY_REVIEW_REQUIRED"
    return patch

def merged_index_rows(evidence_root: Path) -> dict:
    """FILE_INDEX.jsonl (Dropbox archive) merged with WEB_INDEX.jsonl (web retrieval),
    the latter normalized to the same {"paths": [...]} shape the former already has —
    so build_incremental_patch/_body_source resolve locators for either provenance
    without any change to their own logic. A web row's one "path" is its URL. Safe to
    call for archive-only artists: load_index returns {} for a missing WEB_INDEX.jsonl."""
    index = load_index(evidence_root / "index" / "FILE_INDEX.jsonl")
    for file_id, row in load_index(evidence_root / "index" / "WEB_INDEX.jsonl").items():
        index[file_id] = {**row, "paths": [row["url"]]}
    return index


def build_incremental_patch(entity_name: str, entity_type: str, claims: list[dict], current_rows: dict,
                            config: dict, index_rows: dict[str, dict]) -> dict:
    """Build a canonical-property patch; never performs a Notion write.

    Supports both fully-resolved entities already in Notion (operation UPDATE, with the
    current values kept) and new entities absent from Notion (operation CREATE, no
    existing_notion_id): the CREATE case no longer aborts on
    EXISTING_PAGE_ID_UNRESOLVED and produces the same inspectable patch/bundle shape.
    """
    typ = entity_type.lower(); spec = config["entita"][typ]
    matches = [r for r in current_rows.get(typ, []) if norm(r.get("titolo", "")) == norm(entity_name)]
    if len(matches) > 1:
        raise ValueError("EXISTING_PAGE_ID_AMBIGUOUS")
    current = matches[0] if matches else None
    field_by_name = {}
    for key, meta in spec.get("campi", {}).items():
        field_by_name[norm(key)] = ("property", key, meta)
        field_by_name[norm(meta["notion"])] = ("property", key, meta)
    for key, meta in spec.get("relazioni", {}).items():
        field_by_name[norm(key)] = ("relation", key, meta)
        field_by_name[norm(meta["notion"])] = ("relation", key, meta)
    operations, provenance = [], []
    for claim in claims:
        source_ids = claim.get("source_file_ids", [])
        locators = []
        for source_id in source_ids:
            row = index_rows.get(source_id, {})
            for path in row.get("paths", []):
                if path not in locators: locators.append(path)
        provenance.extend({"claim_id": claim.get("claim_id"), "source_file_id": sid, "source_locator": locators}
                          for sid in source_ids)
        status = str(claim.get("status", "")).upper()
        target = field_by_name.get(norm(claim.get("predicate", "")))
        if status not in SUPPORTED_CLAIM_STATUS or not source_ids or not locators:
            operations.append({"action": "CONFLICT", "claim_id": claim.get("claim_id"), "reason": "UNSUPPORTED_STATUS_OR_MISSING_PROVENANCE"})
            continue
        if not target:
            operations.append({"action": "CONFLICT", "claim_id": claim.get("claim_id"), "reason": "PREDICATE_NOT_IN_ARTISTA_SCHEMA"})
            continue
        kind, key, meta = target; value = claim.get("object")
        if kind == "property":
            old = current.get("campi", {}).get(key) if current else None
            action = ("ADD" if current is None or old in (None, "", [], {})
                      else ("KEEP" if str(old) == str(value) else "UPDATE"))
            if action != "KEEP": operations.append({"action": action, "claim_id": claim.get("claim_id"), "property": meta["notion"], "value": value})
        else:
            old = current.get("relazioni", {}).get(key, []) if current else []
            if value in old: continue
            operations.append({"action": "CONFLICT", "claim_id": claim.get("claim_id"), "property": meta["notion"], "reason": "RELATION_TARGET_ID_NOT_RESOLVED"})
    if current is None:
        return {"entity_type": entity_type.upper(), "operation": "CREATE", "existing_notion_id": None,
                "keep": {"properties": {}, "relations": {}},
                "operations": operations, "provenance": provenance, "dry_run": True}
    keep_properties = {}
    for key, meta in spec.get("campi", {}).items():
        keep_properties[meta["notion"]] = current.get("campi", {}).get(key)
    keep_relations = {}
    for key, meta in spec.get("relazioni", {}).items():
        keep_relations[meta["notion"]] = current.get("relazioni", {}).get(key, [])
    return {"entity_type": entity_type.upper(), "operation": "UPDATE", "existing_notion_id": current.get("id"),
            "keep": {"properties": keep_properties, "relations": keep_relations},
            "operations": operations, "provenance": provenance, "dry_run": True}

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("entity_name"); p.add_argument("--entity-type", required=True); p.add_argument("--claims", type=Path, required=True); p.add_argument("--rows", type=Path, required=True); p.add_argument("--config", type=Path, required=True); p.add_argument("--run-dir", type=Path); a = p.parse_args()
    doc = json.loads(a.claims.read_text()); claims = doc.get("claims", doc) if isinstance(doc, dict) else doc
    rows, cfg = json.loads(a.rows.read_text()), json.loads(a.config.read_text())
    status, _ = compare_entity(a.entity_name, a.entity_type, rows); required = required_fields(cfg, a.entity_type)
    if a.run_dir:
        index = merged_index_rows(a.run_dir.parent / "state")
        output = build_incremental_patch(a.entity_name, a.entity_type, claims, rows, cfg, index)
        current = next((r for r in rows.get(a.entity_type.lower(), []) if norm(r.get("titolo", "")) == norm(a.entity_name)), None)
        output = attach_body_adapter(output, claims, current.get("corpo", "") if current else "", index)
        source_paths = {file_id: row.get("paths", []) for file_id, row in index.items()}
        web_file_ids = {file_id for file_id, row in index.items() if row.get("source_type") == "WEB"}
        verification = summarize_web_verification(claims, web_file_ids)
        output["bundle"] = str(write_evidence_bundle(a.run_dir, a.entity_name, a.entity_type, claims, status, required,
                                                       source_paths=source_paths, verification=verification))
        bundle_path = Path(output["bundle"])
        (bundle_path / "NOTION_PATCH.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (bundle_path / "body.proposed_markdown").write_text(output["body"]["proposed_markdown"] + "\n", encoding="utf-8")
    else: output = notion_payload(a.entity_type, a.entity_name, claims, status, required)
    print(json.dumps(output, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
