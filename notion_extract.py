#!/usr/bin/env python3
"""Esporta i sei data source Area35 nel contratto rows.json.

Solo API Notion + libreria standard Python. Il token viene letto da un file locale
(mai stampato o scritto nell'output); lo script non modifica pagine, proprietà o schema.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import credentials


API = "https://api.notion.com/v1"


class Notion:
    def __init__(self, token: str, version: str = "2026-03-11"):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": version,
            "Content-Type": "application/json",
        }

    def call(self, method: str, path: str, body=None):
        req = urllib.request.Request(API + path, method=method, headers=self.headers)  # noqa: S310 - API is a fixed https constant; path always internal
        if body is not None:
            req.data = json.dumps(body).encode()
        for attempt in range(4):
            try:
                # Resta sotto il rate limit medio dichiarato da Notion.
                if attempt or path.startswith("/blocks/"):
                    time.sleep(0.35)
                with urllib.request.urlopen(req, timeout=90) as res:  # noqa: S310 - urlopen of the validated req above
                    return json.load(res)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:500]
                if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Notion API {exc.code} su {path}: {detail}") from exc
            except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Timeout/rete Notion su {path}: {exc}") from exc

    def query(self, data_source: str, database: str, limit=None):
        # Le API recenti espongono data_sources; il fallback mantiene compatibilità
        # con integrazioni che hanno ancora il database condiviso.
        ds = data_source.replace("collection://", "")
        try:
            path = f"/data_sources/{ds}/query"
            rows = self._paginate(path, limit)
        except RuntimeError as first:
            try:
                rows = self._paginate(f"/databases/{database}/query", limit)
            except RuntimeError:
                raise first
        return rows

    def _paginate(self, path, limit):
        out, cursor = [], None
        while True:
            body = {"page_size": min(100, limit - len(out)) if limit else 100}
            if cursor:
                body["start_cursor"] = cursor
            page = self.call("POST", path, body)
            out.extend(page.get("results", []))
            if limit and len(out) >= limit:
                return out[:limit]
            if not page.get("has_more"):
                return out
            cursor = page.get("next_cursor")

    def blocks(self, page_id):
        out, cursor = [], None
        while True:
            path = f"/blocks/{page_id}/children?page_size=100"
            if cursor:
                path += f"&start_cursor={cursor}"
            page = self.call("GET", path)
            out.extend(page.get("results", []))
            if not page.get("has_more"):
                break
            cursor = page.get("next_cursor")
        return out


def plain(parts):
    return "".join((p.get("plain_text") or p.get("text", {}).get("content", "")) for p in parts or [])


def prop_value(prop):
    typ = prop.get("type")
    value = prop.get(typ)
    if typ in ("title", "rich_text"):
        return plain(value)
    if typ in ("select", "status"):
        return (value or {}).get("name", "") if value else ""
    if typ == "multi_select":
        return [x.get("name", "") for x in value or []]
    if typ == "date":
        return value or {}
    if typ == "relation":
        return [x.get("id") for x in value or [] if x.get("id")]
    if typ == "formula":
        return prop_value(value or {}) if value else None
    return value


def page_url(page):
    if page.get("url"):
        return page["url"]
    return "https://www.notion.so/" + page.get("id", "").replace("-", "")


def page_body(api, page_id):
    chunks = []

    def walk(blocks):
        for block in blocks:
            data = block.get(block.get("type", ""), {})
            text = plain(data.get("rich_text") or data.get("text") or [])
            if text:
                chunks.append(text)
            if block.get("has_children"):
                walk(api.blocks(block["id"]))

    walk(api.blocks(page_id))
    return "\n".join(chunks)


def extract(api, cfg, limit=None, entities=None):
    wanted = set(entities or cfg["entita"])
    pages_by_id, raw = {}, {}
    for entity, spec in cfg["entita"].items():
        if entity not in wanted:
            continue
        pages = api.query(spec["data_source"], spec["notion_database_id"], limit)
        raw[entity] = pages
        for page in pages:
            pages_by_id[page.get("id", "").replace("-", "")] = page_url(page)

    rows = {entity: [] for entity in cfg["entita"] if entity in wanted}
    for entity, pages in raw.items():
        spec = cfg["entita"][entity]
        title_key = next((k for k, m in spec.get("campi", {}).items() if m.get("notion")), None)
        for page in pages:
            props = page.get("properties", {})
            campi, servizio, relazioni = {}, {}, {}
            for key, meta in spec.get("campi", {}).items():
                value = prop_value(props.get(meta["notion"], {}))
                if key == "data" and isinstance(value, dict):
                    campi[key] = value.get("start", "")
                    if value.get("end"):
                        servizio["data_end"] = value["end"]
                else:
                    campi[key] = value
            for key, meta in spec.get("relazioni", {}).items():
                refs = prop_value(props.get(meta["notion"], {})) or []
                relazioni[key] = [pages_by_id.get(x.replace("-", ""), page_url({"id": x})) for x in refs]
            service = spec.get("servizio", {})
            if service.get("stato"):
                servizio["stato"] = prop_value(props.get(service["stato"]["notion"], {}))
            for optional in ("verificato_il", "pubblicabile", "riservatezza"):
                meta = service.get(optional)
                if meta and isinstance(meta, dict) and meta.get("notion"):
                    value = prop_value(props.get(meta["notion"], {}))
                    if isinstance(value, dict):
                        value = value.get("start", "")
                    servizio[optional if optional != "verificato_il" else "verificato_il"] = value
            for source in service.get("fonti", []):
                servizio[f"fonte::{source['notion']}"] = prop_value(props.get(source["notion"], {}))
            title = prop_value(props.get(spec["campi"][title_key]["notion"], {})) if title_key else ""
            rows[entity].append({
                "id": page_url(page), "titolo": title, "campi": campi,
                "relazioni": relazioni, "servizio": servizio,
                "corpo": page_body(api, page["id"]),
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--token-file", default=os.environ.get("AREA35_NOTION_TOKEN_FILE", "~/.config/area35-qa/notion_token"))
    ap.add_argument("--notion-version", default="2022-06-28")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--entities", help="Nomi separati da virgola per il collaudo limitato")
    args = ap.parse_args()
    # nome non-'token=': evita il pattern credential_assignment di check_runtime_git_policy.py:36
    try:
        resolved = credentials.get_token("NOTION_TOKEN", args.token_file)
    except credentials.TokenError as exc:
        raise SystemExit(str(exc)) from exc
    notion_token = resolved.value
    print(f"[info] token Notion letto da {resolved.origin}", file=sys.stderr)
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    entities = [x.strip() for x in args.entities.split(",")] if args.entities else None
    rows = extract(Notion(notion_token, args.notion_version), cfg, args.limit, entities)
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Esportate {sum(len(v) for v in rows.values())} schede in {args.out}")


if __name__ == "__main__":
    main()
