#!/usr/bin/env python3
"""Local, stdlib-only review/publish interface for a gmv_notion_multi_candidate
run's bundles (run_dir/entities/*/).

GUI as presentation layer only, never domain logic: every action here is a
direct, unmodified call into gmv_notion_publish.py::publish_bundle(), which
already performs every real check (already-published, gate, live
duplicate-title guard, live staleness, audit logging). This module never
re-implements or duplicates that sequence -- it only calls publish_bundle()
twice per human action (input_fn answering "n" for preview, "y" for
approval) and renders the text it already produces.

Always started manually in the foreground; never as a LaunchAgent/scheduled
service (no Service OID / Service Registry entry exists for this). Binds to
127.0.0.1 only.
"""
from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import urlparse

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from gmv_notion_publish import publish_bundle


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def list_entities(run_dir: Path) -> list[dict]:
    """Runtime scan of run_dir/entities/*/ -- deliberately no cached manifest:
    a cache would need manual invalidation on every publish and would become a
    second, parallel status vocabulary. Reads only files the pipeline already
    writes (entity.json, NOTION_PAYLOAD.json, presence of PUBLISHED.json)."""
    entities_dir = run_dir / "entities"
    if not entities_dir.is_dir():
        return []
    out = []
    for bundle_dir in sorted(entities_dir.iterdir()):
        entity = read_json(bundle_dir / "entity.json", None)
        if entity is None:
            continue
        payload = read_json(bundle_dir / "NOTION_PAYLOAD.json", {})
        out.append({
            "folder": bundle_dir.name, "name": entity.get("name"),
            "entity_type": entity.get("entity_type"), "gate": payload.get("gate"),
            "published": (bundle_dir / "PUBLISHED.json").is_file(),
        })
    return out


def render_index(run_dir: Path) -> str:
    rows = list_entities(run_dir)
    lines = ["<html><body>", f"<h1>Run: {html.escape(str(run_dir))}</h1>", "<table border=1>",
             "<tr><th>Nome</th><th>Tipo</th><th>Gate</th><th>Stato</th><th></th></tr>"]
    for row in rows:
        status = "PUBBLICATO" if row["published"] else "in attesa"
        link = f'<a href="/entity/{html.escape(row["folder"])}">apri</a>'
        lines.append(
            f"<tr><td>{html.escape(str(row['name']))}</td><td>{html.escape(str(row['entity_type']))}</td>"
            f"<td>{html.escape(str(row['gate']))}</td><td>{status}</td><td>{link}</td></tr>")
    lines.append("</table></body></html>")
    return "\n".join(lines)


def render_entity_page(folder: str, screen_text: str, already_published: bool) -> str:
    lines = ["<html><body>", '<p><a href="/">&larr; torna all\'elenco</a></p>',
             f"<pre>{html.escape(screen_text)}</pre>"]
    if not already_published:
        lines.append(f'<form method="POST" action="/entity/{html.escape(folder)}/approve">'
                     '<button type="submit">Pubblica</button></form>')
    lines.append("</body></html>")
    return "\n".join(lines)


def render_result_page(screen_text: str, return_code: int) -> str:
    return "\n".join(["<html><body>", '<p><a href="/">&larr; torna all\'elenco</a></p>',
                      f"<pre>{html.escape(screen_text)}</pre>", f"<p>Codice esito: {return_code}</p>",
                      "</body></html>"])


def _run_publish(bundle_dir: Path, *, config_path: Path, token_file: str | None,
                 notion_version: str, answer: str) -> tuple[str, int]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = publish_bundle(bundle_dir, config_path=config_path, token_file=token_file,
                            notion_version=notion_version, input_fn=lambda _: answer)
    return buf.getvalue(), rc


def preview_bundle(bundle_dir: Path, *, config_path: Path, token_file: str | None,
                   notion_version: str) -> tuple[str, int]:
    """Runs every real publish_bundle() check (live duplicate/staleness
    included) but always declines the confirmation, so nothing is ever
    written -- see module docstring."""
    return _run_publish(bundle_dir, config_path=config_path, token_file=token_file,
                        notion_version=notion_version, answer="n")


def approve_bundle(bundle_dir: Path, *, config_path: Path, token_file: str | None,
                   notion_version: str) -> tuple[str, int]:
    return _run_publish(bundle_dir, config_path=config_path, token_file=token_file,
                        notion_version=notion_version, answer="y")


def make_handler(run_dir: Path, config_path: Path, token_file: str | None, notion_version: str):
    class Handler(BaseHTTPRequestHandler):
        def _send_html(self, body: str, code: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._send_html(render_index(run_dir))
                return
            if path.startswith("/entity/"):
                folder = path[len("/entity/"):]
                bundle_dir = run_dir / "entities" / folder
                if not bundle_dir.is_dir():
                    self._send_html("not found", 404)
                    return
                screen_text, _rc = preview_bundle(bundle_dir, config_path=config_path,
                                                  token_file=token_file, notion_version=notion_version)
                already_published = (bundle_dir / "PUBLISHED.json").is_file()
                self._send_html(render_entity_page(folder, screen_text, already_published))
                return
            self._send_html("not found", 404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path.startswith("/entity/") and path.endswith("/approve"):
                folder = path[len("/entity/"):-len("/approve")]
                bundle_dir = run_dir / "entities" / folder
                if not bundle_dir.is_dir():
                    self._send_html("not found", 404)
                    return
                screen_text, rc = approve_bundle(bundle_dir, config_path=config_path,
                                                 token_file=token_file, notion_version=notion_version)
                self._send_html(render_result_page(screen_text, rc))
                return
            self._send_html("not found", 404)

        def log_message(self, fmt, *args) -> None:
            pass

    return Handler


def run_server(run_dir: Path, config_path: Path, *, port: int = 8765,
              token_file: str | None = None, notion_version: str = "2022-06-28") -> None:
    handler = make_handler(run_dir, config_path, token_file, notion_version)
    with TCPServer(("127.0.0.1", port), handler) as httpd:
        bound_port = httpd.server_address[1]
        print(f"gmv review server: http://127.0.0.1:{bound_port}/  (run_dir={run_dir})")
        httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token-file", default="~/.config/area35-qa/notion_token")
    parser.add_argument("--notion-version", default="2022-06-28")
    args = parser.parse_args(argv)
    run_server(args.run_dir, args.config, port=args.port, token_file=args.token_file,
              notion_version=args.notion_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
