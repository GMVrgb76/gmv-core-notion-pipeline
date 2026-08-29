import sys
from pathlib import Path

# Plain sys.path import (not importlib.util.spec_from_file_location) so this is the
# exact same module object gmv_artist_web_retrieve imports internally — otherwise
# `except evidence.EvidenceError` below would not catch exceptions web.py raises,
# since the two loading styles produce independent classes for the same source file.
sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import gmv_evidence_pipeline as evidence
import gmv_artist_web_retrieve as web

def test_request_lists_only_unmet_or_unverified_predicates():
    claims = [
        {"predicate": "nato a", "status": "SUPPORTED_BY_ARCHIVE"},
        {"predicate": "opere", "status": "SUPPORTED_BY_WEB"},
    ]
    requests = web.build_retrieval_requests("Riccardo Paternò Castello", "artista", claims, {"nato a", "opere", "formazione"})
    predicates = {r["predicate"] for r in requests}
    assert predicates == {"opere", "formazione"}
    assert "nato a" not in predicates

def test_ingest_produces_gate_blocking_claims_and_content_addressed_snapshot(tmp_path):
    findings = [{"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Ritratto, studio da Bronzino.", "url": "https://example.org/rpc"}]
    claims = web.ingest_web_findings("Riccardo Paternò Castello", findings, tmp_path)
    assert claims[0]["status"] == "SUPPORTED_BY_WEB"
    assert claims[0]["source_type"] == "WEB"
    fid = claims[0]["file_id"]
    _, cache = evidence.paths(tmp_path)
    snapshot = evidence.read_json(cache / "web" / f"{fid.split(':', 1)[1]}.json", None)
    assert snapshot["url"] == "https://example.org/rpc" and snapshot["text"] == findings[0]["evidence_excerpt"]
    index = evidence.load_index(tmp_path / "index" / "WEB_INDEX.jsonl")
    assert index[fid]["source_type"] == "WEB"

def test_ingest_rejects_finding_missing_required_field(tmp_path):
    try:
        web.ingest_web_findings("X", [{"predicate": "opere", "object_raw": "o", "url": "https://x"}], tmp_path)
    except evidence.EvidenceError as exc:
        assert "evidence_excerpt" in str(exc)
    else:
        assert False

def test_single_web_source_never_reaches_gate_alone(tmp_path):
    findings = [{"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "a", "url": "https://a"}]
    claims = web.ingest_web_findings("Riccardo Paternò Castello", findings, tmp_path)
    resolved = evidence.resolve_claims(claims, {"artista": []})
    consolidated = evidence.consolidate_claims(resolved)
    assert evidence.gate("NEW_ENTITY", consolidated, {"opere"}) == "INSUFFICIENT_EVIDENCE"

def test_two_corroborating_web_sources_verify_local_and_pass_gate(tmp_path):
    findings = [
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Fonte uno: studio da Bronzino.", "url": "https://a"},
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Fonte due: conferma studio da Bronzino.", "url": "https://b"},
    ]
    claims = web.ingest_web_findings("Riccardo Paternò Castello", findings, tmp_path)
    resolved = evidence.resolve_claims(claims, {"artista": []})
    consolidated = evidence.consolidate_claims(resolved)
    assert len(consolidated) == 1 and len(consolidated[0]["source_file_ids"]) == 2
    # Not yet verified: still gate-blocking on its own.
    assert evidence.gate("NEW_ENTITY", consolidated, {"opere"}) == "INSUFFICIENT_EVIDENCE"
    verified = web.verify_local(consolidated, tmp_path, min_corroborating_sources=2)
    assert verified[0]["status"] == "VERIFIED"
    assert evidence.gate("NEW_ENTITY", verified, {"opere"}) == "READY_FOR_NOTION"

def test_known_limitation_query_id_as_sole_discriminator_undercounts_sources(tmp_path):
    """Documented trade-off, not a bug to fix here: normalize_source_url discards the
    query string entirely, so two genuinely different pages on a query-id-based site
    (common on PHP/CMS/forum software, e.g. article.php?id=123 vs ?id=456) collapse to
    the same source_url. This under-counts real corroboration (a false negative: a
    well-corroborated claim stays SUPPORTED_BY_WEB longer than necessary) but never
    over-counts it (never fakes VERIFIED from one real source) — the safe failure
    direction per this module's explicit design trade-off. A third source from a
    genuinely different domain still resolves it correctly."""
    findings = [
        {"predicate": "opere", "object_raw": "A", "evidence_excerpt": "Articolo 123 su Studio da Bronzino.", "url": "https://news.example.com/article.php?id=123"},
        {"predicate": "opere", "object_raw": "A", "evidence_excerpt": "Articolo 456, fonte diversa dello stesso sito.", "url": "https://news.example.com/article.php?id=456"},
    ]
    claims = web.ingest_web_findings("X", findings, tmp_path)
    resolved = evidence.resolve_claims(claims, {"artista": []})
    consolidated = evidence.consolidate_claims(resolved)
    assert len(consolidated[0]["source_file_ids"]) == 2  # two real sources...
    verified = web.verify_local(consolidated, tmp_path, min_corroborating_sources=2)
    assert verified[0]["status"] == "SUPPORTED_BY_WEB"  # ...undercounted as one, not falsely VERIFIED

def test_normalize_source_url_collapses_scheme_www_and_query():
    base = web.normalize_source_url("https://onlysite.example/page")
    assert web.normalize_source_url("http://onlysite.example/page") == base
    assert web.normalize_source_url("https://www.onlysite.example/page") == base
    assert web.normalize_source_url("https://onlysite.example/page?utm_source=fb") == base
    assert web.normalize_source_url("https://onlysite.example/page/") == base

def test_http_https_variant_of_same_page_is_not_two_independent_sources(tmp_path):
    findings = [
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Primo estratto.", "url": "http://onlysite.example/page"},
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Secondo estratto.", "url": "https://onlysite.example/page"},
    ]
    claims = web.ingest_web_findings("Riccardo Paternò Castello", findings, tmp_path)
    resolved = evidence.resolve_claims(claims, {"artista": []})
    consolidated = evidence.consolidate_claims(resolved)
    verified = web.verify_local(consolidated, tmp_path, min_corroborating_sources=2)
    assert verified[0]["status"] == "SUPPORTED_BY_WEB"
    assert evidence.gate("NEW_ENTITY", verified, {"opere"}) == "INSUFFICIENT_EVIDENCE"

def test_www_and_tracking_query_variants_are_not_independent_sources(tmp_path):
    findings = [
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Primo estratto.", "url": "https://www.onlysite.example/page?utm_source=fb"},
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Secondo estratto.", "url": "https://onlysite.example/page?utm_source=tw"},
    ]
    claims = web.ingest_web_findings("Riccardo Paternò Castello", findings, tmp_path)
    resolved = evidence.resolve_claims(claims, {"artista": []})
    consolidated = evidence.consolidate_claims(resolved)
    verified = web.verify_local(consolidated, tmp_path, min_corroborating_sources=2)
    assert verified[0]["status"] == "SUPPORTED_BY_WEB"
    assert evidence.gate("NEW_ENTITY", verified, {"opere"}) == "INSUFFICIENT_EVIDENCE"

def test_same_url_quoted_twice_is_not_two_independent_sources(tmp_path):
    """The exploit the reviewer demonstrated: re-quoting one page must not fake corroboration."""
    findings = [
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Primo estratto della stessa pagina.", "url": "https://onlysite.example/page"},
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Secondo estratto, stessa pagina.", "url": "https://onlysite.example/page/"},
    ]
    claims = web.ingest_web_findings("Riccardo Paternò Castello", findings, tmp_path)
    resolved = evidence.resolve_claims(claims, {"artista": []})
    consolidated = evidence.consolidate_claims(resolved)
    assert len(consolidated[0]["source_file_ids"]) == 2
    verified = web.verify_local(consolidated, tmp_path, min_corroborating_sources=2)
    assert verified[0]["status"] == "SUPPORTED_BY_WEB"
    assert evidence.gate("NEW_ENTITY", verified, {"opere"}) == "INSUFFICIENT_EVIDENCE"

def test_identical_excerpt_from_different_urls_keeps_both_provenance(tmp_path):
    """Content-collision must not overwrite one source's snapshot/url with another's."""
    findings = [
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Testo di sindacazione identico.", "url": "https://siteA.example/page"},
        {"predicate": "opere", "object_raw": "Studio da Bronzino", "evidence_excerpt": "Testo di sindacazione identico.", "url": "https://siteB.example/page"},
    ]
    claims = web.ingest_web_findings("Riccardo Paternò Castello", findings, tmp_path)
    assert claims[0]["file_id"] != claims[1]["file_id"]
    index = evidence.load_index(tmp_path / "index" / "WEB_INDEX.jsonl")
    urls = {index[c["file_id"]]["url"] for c in claims}
    assert urls == {"https://siteA.example/page", "https://siteB.example/page"}
    resolved = evidence.resolve_claims(claims, {"artista": []})
    consolidated = evidence.consolidate_claims(resolved)
    verified = web.verify_local(consolidated, tmp_path, min_corroborating_sources=2)
    assert verified[0]["status"] == "VERIFIED"

def test_ingest_validates_whole_batch_before_writing_any_file(tmp_path):
    """A bad finding later in the batch must not leave orphaned snapshots from earlier ones."""
    findings = [
        {"predicate": "opere", "object_raw": "o", "evidence_excerpt": "e", "url": "https://a"},
        {"predicate": "opere", "object_raw": "o", "url": "https://b"},
    ]
    try:
        web.ingest_web_findings("X", findings, tmp_path)
    except evidence.EvidenceError:
        pass
    else:
        assert False
    assert not (tmp_path / "cache" / "web").exists()
    assert not (tmp_path / "index" / "WEB_INDEX.jsonl").exists()

def test_verify_local_leaves_archive_claims_untouched(tmp_path):
    claims = [{"status": "SUPPORTED_BY_ARCHIVE", "source_file_ids": ["sha256:x"]}]
    assert web.verify_local(claims, tmp_path) == claims
