#!/usr/bin/env python3
"""Write a candidate patch (from gmv_notion_candidate.py) to a real Notion page.

Sibling to notion_extract.py: reuses its Notion HTTP client and prop_value()
unchanged. Never touches relation properties -- build_incremental_patch()
never resolves a relation to a writable value, only ever CONFLICT for those.
Never sends a request in "dry-run"/"check" mode. The interactive review,
mandatory confirmation, and audit logging live one layer up, in
10_API/gmv_notion_publish.py -- this module is pure mechanics plus a thin
CLI for standalone use.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import credentials
from notion_extract import Notion, prop_value

MULTI_SELECT_SPLIT_RE = re.compile(r"[,;•|/]")
PAGE_ID_RE = re.compile(r"[0-9a-fA-F]{32}$")


def _extract_page_id(value: str) -> str:
    """Accepts a bare page id (dashed or not) or a full Notion URL/slug and
    returns the bare 32-hex-char id the Notion API expects in a path."""
    candidate = str(value).strip().split("?")[0].rstrip("/").split("/")[-1]
    hex_id = candidate.replace("-", "")
    match = PAGE_ID_RE.search(hex_id)
    if not match:
        raise ValueError(f"cannot extract a Notion page id from {value!r}")
    return match.group(0)


def _split_multi(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [x.strip() for x in MULTI_SELECT_SPLIT_RE.split(str(value)) if x.strip()]


def _build_title(value): return {"title": [{"type": "text", "text": {"content": str(value)}}]}
def _build_rich_text(value): return {"rich_text": [{"type": "text", "text": {"content": str(value)}}]}
def _build_number(value): return {"number": None if value in (None, "") else float(value)}
def _build_select(value): return {"select": None if not value else {"name": str(value)}}
def _build_multi_select(value): return {"multi_select": [{"name": v} for v in _split_multi(value)]}
def _build_date(value): return {"date": None if not value else {"start": str(value)}}
def _build_url(value): return {"url": str(value) if value else None}
def _build_checkbox(value):
    if isinstance(value, bool): return {"checkbox": value}
    return {"checkbox": str(value).strip().lower() in {"true", "yes", "si", "sì", "1"}}

# Deliberately no "relation" entry: relations are never written by this module.
# build_incremental_patch() in gmv_notion_candidate.py never emits ADD/UPDATE for
# a relation key today (always CONFLICT) -- belt-and-suspenders, not an accident.
NOTION_TYPE_BUILDERS = {
    "title": _build_title, "rich_text": _build_rich_text, "number": _build_number,
    "select": _build_select, "multi_select": _build_multi_select, "date": _build_date,
    "url": _build_url, "checkbox": _build_checkbox,
}


def fetch_database_schema(client: Notion, database_id: str) -> dict[str, str]:
    """{notion_property_name: notion_type}, read live -- config.json's coarse
    'tipo' field can't distinguish title from rich_text, and a live read also
    protects against config.json drifting from the real database over time."""
    result = client.call("GET", f"/databases/{database_id}")
    return {name: prop["type"] for name, prop in result.get("properties", {}).items()}


def build_property_payload(schema: dict[str, str], operations: list[dict]) -> tuple[dict, list[dict]]:
    """Only consumes action in {ADD, UPDATE}; CONFLICT and anything else is
    surfaced upstream, never touched here. Returns (notion_properties, skipped)."""
    properties: dict = {}
    skipped: list[dict] = []
    for op in operations:
        if op.get("action") not in ("ADD", "UPDATE"):
            continue
        name = op["property"]
        notion_type = schema.get(name)
        builder = NOTION_TYPE_BUILDERS.get(notion_type)
        if builder is None:
            skipped.append({**op, "reason": f"UNSUPPORTED_NOTION_TYPE:{notion_type}"})
            continue
        properties[name] = builder(op.get("value"))
    return properties, skipped


def markdown_to_blocks(markdown: str) -> list[dict]:
    """Strict parser for exactly the format render_body_patch_markdown() ever
    produces: '## ' (heading_2), '### ' (heading_3), '- ' (bulleted list item),
    blank lines. Fails closed on anything else rather than guessing a rendering."""
    blocks = []
    for line in markdown.splitlines():
        if not line.strip():
            continue
        # No leading whitespace check: render_body_patch_markdown() never indents
        # anything (flat bullets only, no nesting) -- an indented line is always
        # out-of-format, not a nested list to support.
        if line.startswith("### "):
            text = line[4:]
            blocks.append({"object": "block", "type": "heading_3",
                            "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]}})
        elif line.startswith("## "):
            text = line[3:]
            blocks.append({"object": "block", "type": "heading_2",
                            "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}})
        elif line.startswith("- "):
            text = line[2:]
            blocks.append({"object": "block", "type": "bulleted_list_item",
                            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]}})
        else:
            raise ValueError(f"unexpected markdown construct: {line!r}")
    return blocks


def fetch_live_properties(client: Notion, page_id: str) -> dict:
    page = client.call("GET", f"/pages/{_extract_page_id(page_id)}")
    props = page.get("properties", {})
    return {name: prop_value(prop) for name, prop in props.items()}


def find_existing_page_id(client: Notion, database_id: str, title_property: str, title: str) -> str | None:
    """Live, exact-match check used only to guard a CREATE against producing a
    duplicate page: does a page with this literal title already exist in the
    database right now? Not a fuzzy/normalized dedupe -- a near-miss title
    still requires a human to notice and resolve manually via the warning
    this triggers upstream."""
    result = client.call("POST", f"/databases/{database_id}/query",
                          {"filter": {"property": title_property, "title": {"equals": title}}})
    results = result.get("results", [])
    return results[0]["id"] if results else None


def check_staleness(client: Notion, patch: dict) -> dict:
    if patch.get("existing_notion_id") is None:
        return {"stale": False, "diffs": [], "reason": "CREATE has no live page to compare"}
    live = fetch_live_properties(client, patch["existing_notion_id"])
    diffs = []
    for name, bundle_value in patch.get("keep", {}).get("properties", {}).items():
        live_value = live.get(name)
        if str(live_value) != str(bundle_value):
            diffs.append({"property": name, "bundle_value": bundle_value, "live_value": live_value})
    return {"stale": bool(diffs), "diffs": diffs}


def plan_requests(database_id: str, patch: dict, schema: dict, body_markdown: str | None) -> tuple[list[dict], list[dict]]:
    """Pure, no network calls -- the exact requests apply_patch() would send."""
    properties, skipped = build_property_payload(schema, patch.get("operations", []))
    requests = []
    if patch["operation"] == "CREATE":
        requests.append({"method": "POST", "path": "/pages",
                          "body": {"parent": {"database_id": database_id}, "properties": properties}})
        page_id_placeholder = "{page_id_from_create}"
    else:
        page_id_placeholder = _extract_page_id(patch["existing_notion_id"])
        if properties:
            requests.append({"method": "PATCH", "path": f"/pages/{page_id_placeholder}",
                              "body": {"properties": properties}})
    if body_markdown and patch.get("body_gate") == "BODY_PATCH_READY":
        blocks = markdown_to_blocks(body_markdown)
        if blocks:
            requests.append({"method": "PATCH", "path": f"/blocks/{page_id_placeholder}/children",
                              "body": {"children": blocks}})
    return requests, skipped


def apply_patch(client: Notion, database_id: str, patch: dict, schema: dict, body_markdown: str | None) -> dict:
    properties, skipped = build_property_payload(schema, patch.get("operations", []))
    if patch["operation"] == "CREATE":
        result = client.call("POST", "/pages", {"parent": {"database_id": database_id}, "properties": properties})
        page_id = result["id"]
        created = True
    else:
        page_id = _extract_page_id(patch["existing_notion_id"])
        if properties:
            client.call("PATCH", f"/pages/{page_id}", {"properties": properties})
        created = False
    blocks_appended = 0
    if body_markdown and patch.get("body_gate") == "BODY_PATCH_READY":
        blocks = markdown_to_blocks(body_markdown)
        if blocks:
            client.call("PATCH", f"/blocks/{page_id}/children", {"children": blocks})
            blocks_appended = len(blocks)
    return {"page_id": page_id, "created": created,
            "properties_applied": sorted(properties), "properties_skipped": skipped,
            "blocks_appended": blocks_appended}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["check", "dry-run", "apply"])
    ap.add_argument("--notion-patch", type=Path, required=True)
    ap.add_argument("--body-markdown", type=Path)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--entity-type", required=True)
    ap.add_argument("--token-file", default="~/.config/area35-qa/notion_token")
    ap.add_argument("--notion-version", default="2022-06-28")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    if args.mode == "apply" and not args.confirm:
        print("apply requires --confirm", file=sys.stderr)
        return 2

    try:
        resolved = credentials.get_token("NOTION_TOKEN", args.token_file)
    except credentials.TokenError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"[info] token Notion letto da {resolved.origin}", file=sys.stderr)

    patch = json.loads(args.notion_patch.read_text(encoding="utf-8"))
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    database_id = cfg["entita"][args.entity_type.lower()]["notion_database_id"]
    body_markdown = args.body_markdown.read_text(encoding="utf-8") if args.body_markdown else None
    client = Notion(resolved.value, args.notion_version)

    if args.mode == "check":
        output = check_staleness(client, patch)
    elif args.mode == "dry-run":
        requests, skipped = plan_requests(database_id, patch, fetch_database_schema(client, database_id), body_markdown)
        output = {"requests": requests, "properties_skipped": skipped}
    else:
        output = apply_patch(client, database_id, patch, fetch_database_schema(client, database_id), body_markdown)

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
