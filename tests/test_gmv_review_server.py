import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from socketserver import TCPServer

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))
import gmv_review_server as srv


def _write_bundle(run_dir, folder, *, name, entity_type="ARTISTA", gate="READY_FOR_NOTION", published=False):
    bundle = run_dir / "entities" / folder
    bundle.mkdir(parents=True)
    (bundle / "entity.json").write_text(json.dumps({"entity_type": entity_type, "name": name}), encoding="utf-8")
    (bundle / "NOTION_PAYLOAD.json").write_text(json.dumps({"gate": gate}), encoding="utf-8")
    if published:
        (bundle / "PUBLISHED.json").write_text(json.dumps({"notion_page_id": "p1"}), encoding="utf-8")
    return bundle


# --- list_entities / render_index -------------------------------------------

def test_list_entities_reflects_published_flag_without_any_manifest(tmp_path):
    _write_bundle(tmp_path, "artista__Federico", name="Federico Garibaldi", published=False)
    _write_bundle(tmp_path, "mostra__DeProfundis", name="De Profundis", entity_type="MOSTRA",
                 gate="REVIEW_REQUIRED", published=True)
    rows = srv.list_entities(tmp_path)
    by_name = {r["name"]: r for r in rows}
    assert by_name["Federico Garibaldi"]["published"] is False
    assert by_name["De Profundis"]["published"] is True
    assert by_name["De Profundis"]["gate"] == "REVIEW_REQUIRED"


def test_list_entities_empty_when_no_entities_dir(tmp_path):
    assert srv.list_entities(tmp_path) == []


def test_render_index_lists_every_entity_with_a_link(tmp_path):
    _write_bundle(tmp_path, "artista__Federico", name="Federico Garibaldi")
    page = srv.render_index(tmp_path)
    assert "Federico Garibaldi" in page
    assert '/entity/artista__Federico' in page


def test_render_index_escapes_html_in_entity_names(tmp_path):
    _write_bundle(tmp_path, "artista__X", name="<script>alert(1)</script>")
    page = srv.render_index(tmp_path)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


# --- preview_bundle / approve_bundle: never bypass publish_bundle's own checks --

def test_preview_bundle_calls_publish_bundle_with_a_declining_input_fn(tmp_path, monkeypatch):
    captured = {}
    def fake_publish_bundle(bundle_dir, *, config_path, input_fn, **kwargs):
        captured["answer"] = input_fn("prompt?")
        print("screen text")
        return 1
    monkeypatch.setattr(srv, "publish_bundle", fake_publish_bundle)
    text, rc = srv.preview_bundle(tmp_path, config_path=tmp_path / "c.json",
                                  token_file=None, notion_version="v1")
    assert captured["answer"] == "n"
    assert "screen text" in text
    assert rc == 1


def test_approve_bundle_calls_publish_bundle_with_an_accepting_input_fn(tmp_path, monkeypatch):
    captured = {}
    def fake_publish_bundle(bundle_dir, *, config_path, input_fn, **kwargs):
        captured["answer"] = input_fn("prompt?")
        return 0
    monkeypatch.setattr(srv, "publish_bundle", fake_publish_bundle)
    _text, rc = srv.approve_bundle(tmp_path, config_path=tmp_path / "c.json",
                                   token_file=None, notion_version="v1")
    assert captured["answer"] == "y"
    assert rc == 0


def test_render_entity_page_omits_publish_button_when_already_published():
    page = srv.render_entity_page("f", "some text", already_published=True, context={})
    assert "<form" not in page


def test_render_entity_page_includes_publish_button_when_not_published():
    page = srv.render_entity_page("f", "some text", already_published=False, context={})
    assert "<form" in page and "/entity/f/approve" in page


def test_render_entity_page_shows_evidence_and_body_even_when_screen_text_is_a_bare_rejection():
    """Regression: publish_bundle() returns immediately (a one-line gate
    rejection) whenever gate != READY_FOR_NOTION, before ever building the
    full review screen -- without this, a human reviewing a REVIEW_REQUIRED
    multi-entity bundle (the common case) would see nothing about what the
    claims actually say."""
    context = {"evidence_md": "# Denis Curti\n\nGate: REVIEW_REQUIRED",
              "body_markdown": "## EVIDENZE E FONTI\n- AttraversaMenti curated by Denis Curti"}
    page = srv.render_entity_page("f", "gate è 'REVIEW_REQUIRED' — pubblicazione rifiutata",
                                  already_published=False, context=context)
    assert "Denis Curti" in page
    assert "AttraversaMenti" in page


def test_render_entity_page_omits_supplementary_sections_when_bundle_has_none():
    page = srv.render_entity_page("f", "some text", already_published=False, context={})
    assert "Evidenze" not in page
    assert "Testo proposto" not in page


def test_read_bundle_context_reads_evidence_md_and_body_markdown(tmp_path):
    (tmp_path / "EVIDENCE.md").write_text("# Titolo evidenze", encoding="utf-8")
    (tmp_path / "body.proposed_markdown").write_text("## Sezione", encoding="utf-8")
    context = srv.read_bundle_context(tmp_path)
    assert context == {"evidence_md": "# Titolo evidenze", "body_markdown": "## Sezione"}


def test_read_bundle_context_returns_none_for_missing_files(tmp_path):
    context = srv.read_bundle_context(tmp_path)
    assert context == {"evidence_md": None, "body_markdown": None}


# --- real HTTP wiring, no real Notion/network calls -------------------------

class _LiveServer:
    def __init__(self, run_dir, config_path):
        handler = srv.make_handler(run_dir, config_path, None, "v1")
        self.httpd = TCPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def post(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=b"", method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - fixed 127.0.0.1 URL to this test's own local server
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_live_server_index_and_preview_and_approve_routes(tmp_path, monkeypatch):
    _write_bundle(tmp_path, "artista__Federico", name="Federico Garibaldi")
    calls = []
    def fake_publish_bundle(bundle_dir, *, config_path, input_fn, **kwargs):
        answer = input_fn("prompt?")
        calls.append(answer)
        return 0 if answer == "y" else 1
    monkeypatch.setattr(srv, "publish_bundle", fake_publish_bundle)

    server = _LiveServer(tmp_path, tmp_path / "config.json")
    try:
        status, body = server.get("/")
        assert status == 200 and "Federico Garibaldi" in body

        status, body = server.get("/entity/artista__Federico")
        assert status == 200 and "Pubblica" in body
        assert calls == ["n"]

        status, body = server.post("/entity/artista__Federico/approve")
        assert status == 200 and "Codice esito: 0" in body
        assert calls == ["n", "y"]

        status, _ = server.get("/entity/does-not-exist")
        assert status == 404
    finally:
        server.close()
