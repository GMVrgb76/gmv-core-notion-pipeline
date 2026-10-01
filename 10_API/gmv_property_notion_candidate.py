#!/usr/bin/env python3
"""Real-estate candidate bundle: local, inspectable, and never publishable.

Writes the same on-disk bundle shape Area35's art pipeline already produces
(gmv_evidence_pipeline.write_evidence_bundle), then forcibly downgrades its
gate. This module reads and writes NOTHING on Notion -- no client, no
credentials, no comparison against live database state.

Why the downgrade is not optional: the live real-estate Notion databases are
already populated by an independent ChatGPT pipeline under its own
confidence-tier reconciliation contract (CONFERMATO_UTENTE / DOCUMENTATO /
CONTROLLATO / DA_RIVEDERE). Writing here now, or creating a parallel Notion
database, would risk double insertion or corrupting that contract. Until the
user decides an explicit reconciliation contract, this pipeline stops at a
reviewable proposal on disk.

The downgrade is a real code-level block, not a convention: it survives
because gmv_notion_publish.publish_bundle refuses any bundle whose payload
gate is not literally READY_FOR_NOTION, and because write_evidence_bundle
never emits the NOTION_PATCH.json that publish_bundle would otherwise need.
Both are asserted by tests, not just asserted here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gmv_evidence_pipeline import write_evidence_bundle  # noqa: E402

RECONCILIATION_PENDING_GATE = "RECONCILIATION_CONTRACT_PENDING"
PUBLISH_BLOCKED_REASON = (
    "Live Notion database is independently populated by the existing ChatGPT real-estate "
    "pipeline (GMV Real Estate Knowledge Pipeline); no reconciliation contract has been decided "
    "yet. Do not publish this bundle until that decision is made explicitly."
)


def build_property_bundle(property_id: str, consolidated_claims: list[dict], run_dir: Path,
                          source_paths: dict[str, list[str]] | None = None) -> Path:
    """Write the reviewable bundle for one property under
    <run-dir>/entities/<property_id>/ and force its gate closed.

    required=set() is deliberate: no mandatory Notion field has been decided
    for real estate (unlike Area35, where required_fields(config, entity_type)
    comes from a real existing config file), and inventing an arbitrary set
    here would be a fabricated contract, not a discovered one.
    """
    bundle = write_evidence_bundle(run_dir, property_id, "IMMOBILE", consolidated_claims,
                                   notion_status="NEW_ENTITY", required=set(),
                                   source_paths=source_paths)
    payload_path = bundle / "NOTION_PAYLOAD.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["gate"] = RECONCILIATION_PENDING_GATE
    payload["publish_blocked_reason"] = PUBLISH_BLOCKED_REASON
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rewrite_markdown_gate(bundle / "EVIDENCE.md", RECONCILIATION_PENDING_GATE)
    return bundle


def _rewrite_markdown_gate(markdown_path: Path, gate_value: str) -> None:
    """EVIDENCE.md is the file a human actually reads first, and
    write_evidence_bundle() renders it from the gate it computed internally --
    before any override, so it would otherwise advertise READY_FOR_NOTION while
    the JSON payload one directory over says the bundle is blocked. Two
    artifacts disagreeing about publishability is exactly the kind of thing a
    later session would trust, so the line is corrected to match. Rewriting the
    single rendered line (rather than reimplementing the whole document) keeps
    the shared bundle writer untouched; a missing line is a hard error, never a
    silent skip that would leave the contradiction in place.
    """
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("Gate: `"):
            lines[i] = f"Gate: `{gate_value}`"
            break
    else:
        raise ValueError(f"EVIDENCE.md has no gate line to correct: {markdown_path}")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Predicate -> section mapping for render_property_page_markdown(). Purely predicate-based,
# not document-type-based -- a real, known limitation: ha_scadenza/ha_debitore/ha_ente_impositore
# are domain=["DOCUMENT"] generic in the registry and can legitimately come from either a tax
# notice or a lease, but nothing here distinguishes which one produced a given instance, so both
# land in FISCAL_PREDICATES's section (the common case today, since no lease documents have
# contributed real claims yet). "Utenze e bollette" has no predicates at all (see module docstring
# on utenze_e_assicurazioni never being promoted) -- it always renders empty, deliberately, not a
# bug: there is neither a governed predicate nor, as of 2026-09-29, any bank statement or utility
# bill document in GERMIGNAGA's Dropbox folder to extract from.
FISCAL_PREDICATES = {"ha_tipo_tributo", "ha_anno_imposta", "ha_ente_impositore", "ha_debitore",
                     "ha_creditore", "ha_importo_dovuto", "ha_numero_rata", "ha_scadenza",
                     "ha_maggior_tributo", "ha_interessi"}
LEASE_PREDICATES = {"ha_decorrenza", "ha_termine", "ha_ricorrenza", "ha_causale_obbligo"}
PROPERTY_PREDICATES = {"riguarda_immobile", "ha_tipo_documento"}
DEADLINE_PREDICATES = {"mentions_deadline"}

PAGE_SECTIONS = [
    ("Obblighi fiscali", FISCAL_PREDICATES),
    ("Contratti e locazioni", LEASE_PREDICATES),
    ("Dati immobile", PROPERTY_PREDICATES),
    ("Scadenze generiche", DEADLINE_PREDICATES),
]


def _claim_row(claim: dict) -> str:
    source = ", ".join(claim.get("source_file_ids", [])[:1]) or "—"
    qualifiers = claim.get("qualifiers", {})
    page = qualifiers.get("pagina")
    fonte = f"{source[:16]}…" + (f" p.{page}" if page else "")
    return f"| {claim.get('subject', '')} | {claim.get('predicate', '')} | {claim.get('object', '')} | {fonte} |"


def render_property_page_markdown(property_id: str, consolidated_claims: list[dict]) -> str:
    """Renders consolidated claims into the same section structure as the real
    GMV Real Estate Knowledge Pipeline "Pilota immobiliare" Notion pages
    (Obblighi fiscali / Contratti e locazioni / Dati immobile / Scadenze
    generiche / Utenze e bollette) -- a local Markdown preview only, never
    written to Notion (see module docstring). Every governed predicate is
    placed in exactly one section; a predicate not covered by PAGE_SECTIONS
    (future registry growth) falls into a trailing "Altri fatti" section
    rather than being silently dropped.
    """
    by_predicate: dict[str, list[dict]] = {}
    for claim in consolidated_claims:
        by_predicate.setdefault(claim.get("predicate"), []).append(claim)
    covered = set()
    lines = [f"# {property_id} — anteprima pagina (bozza locale, non pubblicata su Notion)", ""]
    for title, predicates in PAGE_SECTIONS:
        covered |= predicates
        rows = [c for pred in predicates for c in by_predicate.get(pred, [])]
        lines.append(f"## {title}")
        if rows:
            lines.append("| Soggetto | Predicato | Oggetto | Fonte |")
            lines.append("|---|---|---|---|")
            lines.extend(_claim_row(c) for c in rows)
        else:
            lines.append("_Nessun fatto governato in questa sezione._")
        lines.append("")
    lines.append("## Utenze e bollette")
    lines.append("_Nessun predicato governato esiste ancora per questo dominio "
                 "(bollette/contratti di fornitura) -- sezione strutturalmente vuota, non un errore._")
    lines.append("")
    leftover = [c for pred, claims in by_predicate.items() if pred not in covered for c in claims]
    if leftover:
        lines.append("## Altri fatti (predicato non ancora mappato a una sezione)")
        lines.append("| Soggetto | Predicato | Oggetto | Fonte |")
        lines.append("|---|---|---|---|")
        lines.extend(_claim_row(c) for c in leftover)
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    candidate_p = sub.add_parser("candidate")
    candidate_p.add_argument("result", type=Path,
                             help="JSON produced by `gmv property-facts analyze-property`")
    candidate_p.add_argument("--run-dir", type=Path, required=True)
    render_p = sub.add_parser("render")
    render_p.add_argument("result", type=Path,
                          help="JSON produced by `gmv property-facts analyze-property`")
    render_p.add_argument("-o", "--output", type=Path, help="Write Markdown here instead of stdout")
    args = p.parse_args(argv)
    document = json.loads(args.result.read_text(encoding="utf-8"))
    property_id = document["property_id"]
    if args.command == "render":
        markdown = render_property_page_markdown(property_id, document.get("consolidated", []))
        if args.output:
            args.output.write_text(markdown, encoding="utf-8")
        else:
            print(markdown)
        return 0
    bundle = build_property_bundle(property_id, document.get("consolidated", []), args.run_dir)
    payload = json.loads((bundle / "NOTION_PAYLOAD.json").read_text(encoding="utf-8"))
    print(json.dumps({"property_id": property_id, "bundle": str(bundle), "gate": payload["gate"],
                      "consolidated_claims": len(document.get("consolidated", []))},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
