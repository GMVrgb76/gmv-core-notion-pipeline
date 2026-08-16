#!/usr/bin/env python3
"""
adapter_notion.py — estrae le schede Area35 da Notion e produce rows.json
nel formato atteso da area35_validator.py.

Sola lettura: esegue solo query e letture di pagina, non modifica nulla.

Uso:
    export NOTION_TOKEN=secret_xxx        # integrazione interna con accesso ai 6 database
    python3 adapter_notion.py --config config.json --out rows.json
    python3 adapter_notion.py --config config.json --out rows.json --with-bodies
    python3 area35_validator.py --config config.json --rows rows.json --out report

Requisiti:
  - i sei database condivisi con l'integrazione (••• → Connections)
  - notion_database_id valorizzato in config.json per ogni entità (già presente)

--with-bodies scarica anche il corpo delle pagine (biografie, testi critici) per
attivare le regole di testo (famiglia Q). Costa una chiamata per pagina: più lento.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.notion.com/v1"
VERSIONE = "2022-06-28"


# --------------------------------------------------------------------------- #
# HTTP (con retry su rate-limit 429)
# --------------------------------------------------------------------------- #

def _headers(token):
    return {"Authorization": f"Bearer {token}", "Notion-Version": VERSIONE, "Content-Type": "application/json"}


def _call(method, path, token, body=None, tentativi=4):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    for t in range(tentativi):
        req = urllib.request.Request(url, data=data, headers=_headers(token), method=method)
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and t < tentativi - 1:
                attesa = int(e.headers.get("Retry-After", "2"))
                time.sleep(attesa)
                continue
            raise RuntimeError(f"HTTP {e.code} su {method} {url}: {e.read().decode(errors='replace')}") from None
    raise RuntimeError("Troppi tentativi (rate limit).")


# --------------------------------------------------------------------------- #
# Lettura delle property
# --------------------------------------------------------------------------- #

def _plain(prop):
    """Valore Python semplice da una property Notion."""
    t = prop.get("type")
    if t in ("title", "rich_text"):
        return "".join(b.get("plain_text", "") for b in prop.get(t, []))
    if t == "number":
        return prop.get("number")
    if t in ("select", "status"):
        s = prop.get(t)
        return s.get("name", "") if s else ""
    if t == "multi_select":
        return [o.get("name", "") for o in prop.get("multi_select", [])]
    if t == "date":
        return prop.get("date") or {}          # dict {start, end} o {}
    if t == "relation":
        return [r.get("id") for r in prop.get("relation", [])]
    if t == "url":
        return prop.get("url") or ""
    if t == "checkbox":
        return "__YES__" if prop.get("checkbox") else "__NO__"
    if t in ("created_time", "last_edited_time"):
        return prop.get(t)
    if t == "formula":
        f = prop.get("formula") or {}
        return f.get(f.get("type"), "")
    if t == "files":
        return [f.get("name", "") for f in prop.get("files", [])]
    return ""


def _query_pagine(db_id, token):
    pagine, cur = [], None
    while True:
        body = {"page_size": 100}
        if cur:
            body["start_cursor"] = cur
        d = _call("POST", f"/databases/{db_id}/query", token, body)
        pagine += d.get("results", [])
        if not d.get("has_more"):
            break
        cur = d.get("next_cursor")
    return pagine


def _corpo(page_id, token):
    righe, cur = [], None
    while True:
        suff = f"?start_cursor={cur}&page_size=100" if cur else "?page_size=100"
        d = _call("GET", f"/blocks/{page_id}/children{suff}", token)
        for b in d.get("results", []):
            t = b.get("type")
            c = b.get(t, {})
            frag = c.get("rich_text") or c.get("text") or []
            testo = "".join(f.get("plain_text", "") for f in frag)
            if testo:
                righe.append(testo)
        if not d.get("has_more"):
            break
        cur = d.get("next_cursor")
    return "\n".join(righe).strip()


# --------------------------------------------------------------------------- #
# Mappatura pagina → record (guidata da config)
# --------------------------------------------------------------------------- #

def _record(pagina, entita, spec, cfg):
    props = pagina.get("properties", {})
    campo_titolo = next(iter(spec["campi"]))
    rec = {"id": pagina["id"], "titolo": "", "campi": {}, "relazioni": {}, "servizio": {}}

    # campi ordinari
    for chiave, meta in spec["campi"].items():
        prop = props.get(meta["notion"])
        if prop is None:
            continue
        val = _plain(prop)
        if meta.get("tipo") == "data":
            start = (val or {}).get("start", "") if isinstance(val, dict) else val
            rec["campi"][chiave] = start or ""
            end = (val or {}).get("end") if isinstance(val, dict) else None
            if end:
                rec["servizio"][f"{chiave}_end"] = end
                if chiave == "data":
                    rec["servizio"]["data_end"] = end
        else:
            rec["campi"][chiave] = val

    # relazioni (liste di id pagina)
    for chiave, meta in spec.get("relazioni", {}).items():
        prop = props.get(meta["notion"])
        rec["relazioni"][chiave] = _plain(prop) if prop else []

    # campi di servizio
    srv = spec.get("servizio", {})
    if srv.get("stato"):
        p = props.get(srv["stato"]["notion"])
        rec["servizio"]["stato"] = _plain(p) if p else ""
    if srv.get("verificato_il"):
        p = props.get(srv["verificato_il"]["notion"])
        d = _plain(p) if p else {}
        rec["servizio"]["verificato_il"] = (d or {}).get("start", "") if isinstance(d, dict) else ""
    for fm in srv.get("fonti", []):
        p = props.get(fm["notion"])
        rec["servizio"][f"fonte::{fm['notion']}"] = (_plain(p) if p else "") or ""
    if srv.get("pubblicabile"):
        p = props.get(srv["pubblicabile"]["notion"])
        rec["servizio"]["pubblicabile"] = _plain(p) if p else "__NO__"
    if srv.get("riservatezza"):
        p = props.get(srv["riservatezza"]["notion"])
        rec["servizio"]["riservatezza"] = _plain(p) if p else ""

    rec["titolo"] = str(rec["campi"].get(campo_titolo) or f"(senza titolo) {rec['id']}")
    return rec


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    global VERSIONE
    ap = argparse.ArgumentParser(description="Estrae le schede Notion Area35 in rows.json (sola lettura).")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--out", default="rows.json")
    ap.add_argument("--with-bodies", action="store_true", help="Scarica anche i corpi pagina (per le regole di testo).")
    ap.add_argument("--version", default=VERSIONE, help="Notion-Version header.")
    args = ap.parse_args()
    VERSIONE = args.version

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN assente. Impostarlo prima di eseguire.", file=sys.stderr)
        return 2

    cfg = json.load(open(args.config, encoding="utf-8"))
    rows = {}
    tot = 0
    for entita, spec in cfg["entita"].items():
        db_id = spec.get("notion_database_id")
        if not db_id:
            print(f"[avviso] '{entita}': notion_database_id assente, salto.", file=sys.stderr)
            rows[entita] = []
            continue
        try:
            pagine = _query_pagine(db_id, token)
        except Exception as exc:
            print(f"[errore] query '{entita}': {exc}", file=sys.stderr)
            rows[entita] = []
            continue

        recs = []
        for pagina in pagine:
            rec = _record(pagina, entita, spec, cfg)
            if args.with_bodies and spec.get("biografia_in_corpo"):
                try:
                    rec["corpo"] = _corpo(pagina["id"], token)
                except Exception as exc:
                    print(f"[avviso] corpo non letto per {rec['id']}: {exc}", file=sys.stderr)
            recs.append(rec)
        rows[entita] = recs
        tot += len(recs)
        print(f"  {entita:12} {len(recs)} schede")

    json.dump(rows, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nScritto {args.out}: {tot} schede totali.")
    if not args.with_bodies:
        print("Nota: senza --with-bodies le regole di testo (Q) restano in gran parte inerti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
