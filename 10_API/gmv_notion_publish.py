#!/usr/bin/env python3
"""Review, approve, and publish a gmv_notion_candidate.py bundle to Notion.

The only command in this codebase that performs a live external write.
Confirmation is always interactive and mandatory -- there is no --yes/--force
bypass for it, by deliberate design. Every publish is journaled through the
existing hash-chained audit log (audit_integrity.py) before the bundle is
marked as published.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

import credentials
from notion_extract import Notion
from notion_publish import check_staleness, fetch_database_schema, plan_requests, apply_patch

from audit_integrity import append as audit_append

UTC = timezone.utc


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class Bundle:
    dir: Path
    entity_name: str
    entity_type: str
    payload: dict
    patch: dict
    body_markdown: str | None


def load_bundle(bundle_dir: Path) -> Bundle:
    entity = read_json(bundle_dir / "entity.json", None)
    if entity is None:
        raise FileNotFoundError(f"not a bundle directory (missing entity.json): {bundle_dir}")
    payload = read_json(bundle_dir / "NOTION_PAYLOAD.json", None)
    if payload is None:
        raise FileNotFoundError(f"missing NOTION_PAYLOAD.json in {bundle_dir}")
    patch = read_json(bundle_dir / "NOTION_PATCH.json", None)
    if patch is None:
        if (bundle_dir / "PATCH.json").is_file():
            raise ValueError(
                f"{bundle_dir} is a multi-entity bundle (gmv_notion_multi_candidate.py, "
                "PATCH.json) -- not supported by gmv evidence publish yet, only "
                "single-entity NOTION_PATCH.json bundles from gmv_notion_candidate.py"
            )
        raise FileNotFoundError(
            f"missing NOTION_PATCH.json in {bundle_dir} -- this bundle was likely "
            "generated without --run-dir, so only the simple NOTION_PAYLOAD.json "
            "shape exists; regenerate with gmv_notion_candidate.py --run-dir"
        )
    body_markdown = patch.get("body", {}).get("proposed_markdown")
    return Bundle(dir=bundle_dir, entity_name=entity["name"], entity_type=entity["entity_type"],
                  payload=payload, patch=patch, body_markdown=body_markdown)


def render_review_screen(bundle: Bundle, requests: list[dict], skipped_ops: list[dict], staleness: dict) -> str:
    lines = [
        f"Entità: {bundle.entity_name} ({bundle.entity_type})",
        f"Operazione: {bundle.patch['operation']}",
        f"Bundle: {bundle.dir}",
        "",
    ]
    if staleness.get("stale"):
        lines.append("ATTENZIONE: il bundle potrebbe essere obsoleto (la pagina Notion è cambiata):")
        for diff in staleness["diffs"]:
            lines.append(f"  - {diff['property']}: bundle={diff['bundle_value']!r} vivo={diff['live_value']!r}")
        lines.append("")

    adds = [op for op in bundle.patch.get("operations", []) if op.get("action") in ("ADD", "UPDATE")]
    if adds:
        lines.append("Cambi proposti:")
        for op in adds:
            lines.append(f"  - {op['property']}: -> {op.get('value')!r}  (claim {op.get('claim_id')})")
        lines.append("")

    conflicts = [op for op in bundle.patch.get("operations", []) if op.get("action") == "CONFLICT"]
    not_applied = conflicts + skipped_ops
    if not_applied:
        lines.append("NON APPLICATO — richiede risoluzione manuale su Notion:")
        for op in not_applied:
            lines.append(f"  - {op.get('property', '(nessuna proprietà)')}: {op.get('reason')}  (claim {op.get('claim_id')})")
        lines.append("")

    if bundle.patch.get("body_gate") == "BODY_PATCH_READY" and bundle.body_markdown:
        lines.append("Corpo da aggiungere (non sostituisce mai il contenuto esistente):")
        lines.append(bundle.body_markdown)
        lines.append("")
    else:
        lines.append("Corpo: REVIEW REQUIRED — non verrà pubblicato nessun blocco di testo.")
        lines.append("")

    lines.append("Richieste HTTP esatte che verrebbero inviate:")
    lines.append(json.dumps(requests, ensure_ascii=False, indent=2))
    return "\n".join(lines)


def confirm(prompt: str, input_fn: Callable[[str], str] = input) -> bool:
    return input_fn(prompt).strip().lower() in {"y", "yes"}


def publish_bundle(
    bundle_dir: Path,
    *,
    config_path: Path,
    token_file: str | None = None,
    notion_version: str = "2022-06-28",
    skip_staleness_check: bool = False,
    input_fn: Callable[[str], str] = input,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    audit_path: Path = Path.home() / ".gmv_core" / "04_LOGS" / "notion_writes.v1.jsonl",
) -> int:
    bundle = load_bundle(bundle_dir)

    if (bundle_dir / "PUBLISHED.json").is_file():
        published = read_json(bundle_dir / "PUBLISHED.json", {})
        print(f"già pubblicato: pagina {published.get('notion_page_id')} il {published.get('published_at')}"
              f" (audit #{published.get('audit_sequence')})")
        return 3

    if bundle.payload.get("gate") != "READY_FOR_NOTION":
        print(f"gate è {bundle.payload.get('gate')!r}, non READY_FOR_NOTION — pubblicazione rifiutata")
        return 4

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    database_id = cfg["entita"][bundle.entity_type.lower()]["notion_database_id"]
    try:
        resolved = credentials.get_token("NOTION_TOKEN", token_file)
    except credentials.TokenError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    client = Notion(resolved.value, notion_version)

    staleness = check_staleness(client, bundle.patch)
    if staleness.get("stale") and not skip_staleness_check:
        print("bundle potenzialmente obsoleto — differenze:")
        for diff in staleness["diffs"]:
            print(f"  - {diff['property']}: bundle={diff['bundle_value']!r} vivo={diff['live_value']!r}")
        print("rigenera il candidato, oppure passa --skip-staleness-check per procedere comunque")
        return 5

    schema = fetch_database_schema(client, database_id)
    requests, skipped_ops = plan_requests(database_id, bundle.patch, schema, bundle.body_markdown)
    print(render_review_screen(bundle, requests, skipped_ops, staleness))

    if not confirm("\nPubblicare questi cambi su Notion? [y/N] ", input_fn):
        print("ANNULLATO — nessuna scrittura inviata a Notion.")
        return 1

    result = apply_patch(client, database_id, bundle.patch, schema, bundle.body_markdown)

    record = {
        "action": "NOTION_PUBLISH", "entity_name": bundle.entity_name, "entity_type": bundle.entity_type,
        "operation": bundle.patch["operation"], "bundle_path": str(bundle_dir),
        "notion_page_id": result["page_id"], "created": result["created"],
        "properties_applied": result["properties_applied"], "properties_skipped": result["properties_skipped"],
        "blocks_appended": result["blocks_appended"], "published_at": clock().isoformat(),
    }
    written = audit_append(audit_path, record)

    write_json(bundle_dir / "PUBLISHED.json", {
        "notion_page_id": result["page_id"], "created": result["created"],
        "published_at": record["published_at"], "audit_sequence": written["sequence"],
        "audit_record_hash": written["record_hash"],
    })

    print(f"\nPubblicato: pagina Notion {result['page_id']} ({'creata' if result['created'] else 'aggiornata'})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--token-file", default="~/.config/area35-qa/notion_token")
    parser.add_argument("--notion-version", default="2022-06-28")
    parser.add_argument("--skip-staleness-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        return publish_bundle(args.bundle, config_path=args.config, token_file=args.token_file,
                               notion_version=args.notion_version, skip_staleness_check=args.skip_staleness_check)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
