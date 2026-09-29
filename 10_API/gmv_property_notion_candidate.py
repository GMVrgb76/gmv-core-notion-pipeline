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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    candidate_p = sub.add_parser("candidate")
    candidate_p.add_argument("result", type=Path,
                             help="JSON produced by `gmv property-facts analyze-property`")
    candidate_p.add_argument("--run-dir", type=Path, required=True)
    args = p.parse_args(argv)
    document = json.loads(args.result.read_text(encoding="utf-8"))
    property_id = document["property_id"]
    bundle = build_property_bundle(property_id, document.get("consolidated", []), args.run_dir)
    payload = json.loads((bundle / "NOTION_PAYLOAD.json").read_text(encoding="utf-8"))
    print(json.dumps({"property_id": property_id, "bundle": str(bundle), "gate": payload["gate"],
                      "consolidated_claims": len(document.get("consolidated", []))},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
