import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import gmv_property_laya_worker as worker  # noqa: E402
import gmv_property_signals as signals  # noqa: E402
from gmv_evidence_pipeline import EvidenceError  # noqa: E402


# ---- gmv_property_laya_worker: pure functions, no laya_mlx / subprocess needed ----

def test_relative_deadline_detected_true_positive():
    assert worker.relative_deadline_detected("Il pagamento va fatto entro la fine del mese.")
    assert worker.relative_deadline_detected("Da completare entro 15 giorni.")
    assert worker.relative_deadline_detected("Rinnovo richiesto entro il 5 del mese prossimo.")


def test_relative_deadline_detected_excludes_vague_non_deadline_phrasing():
    """Regression guard: a first draft matched bare 'nelle prossime settimane', which
    is the ambiguity suite's own vague-non-deadline wording and produced a real false
    positive on a live case (see gmv_property_laya_worker.py module docstring)."""
    assert not worker.relative_deadline_detected("Vedremo cosa fare nelle prossime settimane.")
    assert not worker.relative_deadline_detected("Se ne riparlerà nel prossimo trimestre.")


def test_combined_scadenza_presente_or_semantics():
    assert worker.combined_scadenza_presente("nessuna data qui", 0.9) is True
    assert worker.combined_scadenza_presente("entro la fine del mese", 0.01) is True
    assert worker.combined_scadenza_presente("nessuna data qui", 0.01) is False


def test_derived_rischio_level_precedence():
    assert worker.derived_rischio_level(0.9, 0.9, 0.9) == "alto"
    assert worker.derived_rischio_level(0.1, 0.9, 0.9) == "medio"
    assert worker.derived_rischio_level(0.1, 0.1, 0.9) == "basso"
    assert worker.derived_rischio_level(0.1, 0.1, 0.1) == "nessuno"


def test_chunk_text_short_text_is_single_chunk():
    text = "Testo breve."
    assert worker.chunk_text(text) == [text]


def test_chunk_text_empty_text_returns_one_empty_chunk():
    assert worker.chunk_text("") == [""]


def test_chunk_text_long_text_splits_with_overlap():
    text = "x" * 4000
    chunks = worker.chunk_text(text, chunk_chars=1500, overlap_chars=200)
    assert len(chunks) > 1
    assert all(len(c) <= 1500 for c in chunks)
    # every character of the original text is covered by at least one chunk
    assert "".join(chunks).count("x") >= len(text)


def test_excerpt_centers_on_regex_match_when_present():
    text = "a" * 200 + "il pagamento e' dovuto entro la fine del mese come da accordi" + "b" * 200
    excerpt = worker._excerpt(text)
    assert "entro la fine del mese" in excerpt
    assert len(excerpt) < len(text)


def test_excerpt_falls_back_to_leading_slice_without_regex_match():
    text = "x" * 500
    excerpt = worker._excerpt(text)
    assert excerpt == text[:worker.EXCERPT_CHARS]


def test_chunk_text_marker_at_boundary_survives_in_some_chunk():
    marker = "ENTRO_IL_10_OTTOBRE"
    text = ("a" * 1400) + marker + ("b" * 1400)
    chunks = worker.chunk_text(text, chunk_chars=1500, overlap_chars=200)
    assert any(marker in c for c in chunks)


def test_aggregate_or_semantics_for_scadenza_and_rischio():
    chunk_results = [
        {"dominio": "real_estate", "scadenza_p_true": 0.01, "scadenza_combined": False,
         "regex_relative_deadline": False, "scadenza_excerpt": "no deadline text", "rischio_p_alto": 0.02, "rischio_p_medio": 0.0,
         "rischio_p_basso": 0.0, "rischio_level": "nessuno", "usage": {"input_tokens": 100}},
        {"dominio": "real_estate", "scadenza_p_true": 0.95, "scadenza_combined": True,
         "regex_relative_deadline": False, "scadenza_excerpt": "entro il 10 ottobre", "rischio_p_alto": 0.6, "rischio_p_medio": 0.0,
         "rischio_p_basso": 0.0, "rischio_level": "alto", "usage": {"input_tokens": 100}},
    ]
    out = worker.aggregate(chunk_results, "some long text")
    assert out["scadenza_presente"]["value"] is True
    assert out["scadenza_presente"]["p_true_max"] == 0.95
    assert out["scadenza_presente"]["evidence_excerpt"] == "entro il 10 ottobre"
    assert out["rischio"]["alto"] is True
    assert out["rischio"]["p_alto_max"] == 0.6
    assert out["rischio"]["reliability"] == "low_recall_advisory"
    assert out["dominio"] == "real_estate"
    assert out["dominio_agreement_across_chunks"] is True
    assert out["n_chunks"] == 2


def test_aggregate_prefers_regex_anchored_excerpt_over_higher_probability_chunk():
    """Regression guard for a real bug found by gmv-code-reviewer: picking the
    excerpt by p_true alone could attach a claim to a competing chunk's text
    that does not itself support the claim. A regex-anchored positive chunk
    (a real 'entro ...' match) must win the excerpt even if a different,
    higher-confidence chunk has no textual anchor at all."""
    chunk_results = [
        {"dominio": "real_estate", "scadenza_p_true": 0.1, "scadenza_combined": True,
         "regex_relative_deadline": True, "scadenza_excerpt": "...deve essere pagato entro il 10 ottobre...",
         "rischio_p_alto": 0.0, "rischio_p_medio": 0.0, "rischio_p_basso": 0.0, "rischio_level": "nessuno", "usage": {}},
        {"dominio": "real_estate", "scadenza_p_true": 0.99, "scadenza_combined": True,
         "regex_relative_deadline": False, "scadenza_excerpt": "Il presente documento non contiene riferimenti a scadenze specifiche.",
         "rischio_p_alto": 0.0, "rischio_p_medio": 0.0, "rischio_p_basso": 0.0, "rischio_level": "nessuno", "usage": {}},
    ]
    out = worker.aggregate(chunk_results, "text")
    assert out["scadenza_presente"]["evidence_excerpt"] == "...deve essere pagato entro il 10 ottobre..."


def test_aggregate_evidence_excerpt_is_none_when_no_deadline_found():
    chunk_results = [
        {"dominio": "real_estate", "scadenza_p_true": 0.01, "scadenza_combined": False,
         "regex_relative_deadline": False, "scadenza_excerpt": "no deadline text", "rischio_p_alto": 0.0, "rischio_p_medio": 0.0,
         "rischio_p_basso": 0.0, "rischio_level": "nessuno", "usage": {}},
    ]
    out = worker.aggregate(chunk_results, "text")
    assert out["scadenza_presente"]["value"] is False
    assert out["scadenza_presente"]["evidence_excerpt"] is None


def test_aggregate_surfaces_dominio_disagreement():
    chunk_results = [
        {"dominio": "real_estate", "scadenza_p_true": 0.0, "scadenza_combined": False,
         "regex_relative_deadline": False, "scadenza_excerpt": "", "rischio_p_alto": 0.0, "rischio_p_medio": 0.0,
         "rischio_p_basso": 0.0, "rischio_level": "nessuno", "usage": {}},
        {"dominio": "altro", "scadenza_p_true": 0.0, "scadenza_combined": False,
         "regex_relative_deadline": False, "scadenza_excerpt": "", "rischio_p_alto": 0.0, "rischio_p_medio": 0.0,
         "rischio_p_basso": 0.0, "rischio_level": "nessuno", "usage": {}},
    ]
    out = worker.aggregate(chunk_results, "text")
    assert out["dominio_agreement_across_chunks"] is False
    assert out["dominio_votes"] == {"real_estate": 1, "altro": 1}


# ---- gmv_property_signals: caching, subprocess boundary, error handling ----

def test_property_signal_path_parses_valid_fid(tmp_path):
    path = signals.property_signal_path("sha256:abcdef", tmp_path)
    assert path == tmp_path / "property_signals" / f"abcdef-{signals.PROPERTY_SIGNAL_VERSION}.json"


def test_property_signal_path_none_for_malformed_fid(tmp_path):
    assert signals.property_signal_path(None, tmp_path) is None
    assert signals.property_signal_path("not-a-fid", tmp_path) is None
    assert signals.property_signal_path("md5:abc", tmp_path) is None


def test_property_signals_batch_skips_non_success_records(tmp_path):
    records = [{"file_id": "sha256:a", "extraction_status": "UNSUPPORTED_FORMAT"}]
    out = signals.property_signals_batch(records, tmp_path)
    assert out[0]["signal_status"] == "SKIPPED_NOT_EXTRACTED"
    assert out[0]["extraction_status"] == "UNSUPPORTED_FORMAT"


def test_property_signals_batch_calls_worker_and_caches(tmp_path, monkeypatch):
    calls = []

    def fake_run(text, *, timeout):
        calls.append(text)
        return {"dominio": "real_estate", "scadenza_presente": {"value": True, "p_true_max": 0.9},
                "rischio": {"alto": False, "p_alto_max": 0.01}}

    monkeypatch.setattr(signals, "_run_laya_worker", fake_run)
    record = {"file_id": "sha256:a", "extraction_status": "SUCCESS", "text": "testo di prova"}

    out1 = signals.property_signals_batch([record], tmp_path)
    assert out1[0]["signal_status"] == "SUCCESS"
    assert out1[0]["dominio"] == "real_estate"
    assert len(calls) == 1

    # second call must hit the cache, not the worker again
    out2 = signals.property_signals_batch([record], tmp_path)
    assert out2[0]["signal_status"] == "SUCCESS"
    assert len(calls) == 1


def test_property_signals_batch_records_laya_error_without_raising(tmp_path, monkeypatch):
    def fake_run(text, *, timeout):
        raise EvidenceError("LAYA_TIMEOUT", detail="took too long")

    monkeypatch.setattr(signals, "_run_laya_worker", fake_run)
    record = {"file_id": "sha256:b", "extraction_status": "SUCCESS", "text": "testo"}
    out = signals.property_signals_batch([record], tmp_path)
    assert out[0]["signal_status"] == "LAYA_TIMEOUT"
    assert out[0]["error_detail"] == "took too long"


def test_property_signals_batch_retries_after_transient_failure(tmp_path, monkeypatch):
    """A transient failure (timeout, momentarily-missing venv, MLX OOM) must never
    be permanently cached — only a SUCCESS may be persisted, mirroring
    gmv_evidence_pipeline.semantic_extract_batch's mark_analyzed-only-on-"valid"
    convention. Regression guard for a real bug: the first version of
    property_signals_batch wrote every result to cache unconditionally, so a
    transient LAYA_TIMEOUT was cached forever and never retried."""
    calls = {"n": 0}

    def flaky_run(text, *, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise EvidenceError("LAYA_TIMEOUT", detail="took too long")
        return {"dominio": "real_estate", "scadenza_presente": {"value": False}, "rischio": {"alto": False}}

    monkeypatch.setattr(signals, "_run_laya_worker", flaky_run)
    record = {"file_id": "sha256:c", "extraction_status": "SUCCESS", "text": "testo"}

    out1 = signals.property_signals_batch([record], tmp_path)
    assert out1[0]["signal_status"] == "LAYA_TIMEOUT"
    assert calls["n"] == 1
    assert signals.property_signal_path("sha256:c", tmp_path).exists() is False

    out2 = signals.property_signals_batch([record], tmp_path)
    assert out2[0]["signal_status"] == "SUCCESS"
    assert calls["n"] == 2  # the worker WAS called again -- the earlier failure was not cached


def test_run_laya_worker_raises_when_venv_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(signals, "LAYA_VENV_PYTHON", tmp_path / "does" / "not" / "exist")
    with pytest.raises(EvidenceError) as exc_info:
        signals._run_laya_worker("testo", timeout=5)
    assert exc_info.value.code == "LAYA_UNAVAILABLE"


def test_run_laya_worker_wraps_subprocess_timeout(monkeypatch, tmp_path):
    fake_python = tmp_path / "python3"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)
    monkeypatch.setattr(signals, "LAYA_VENV_PYTHON", fake_python)

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="laya", timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(EvidenceError) as exc_info:
        signals._run_laya_worker("testo", timeout=1)
    assert exc_info.value.code == "LAYA_TIMEOUT"


def test_run_laya_worker_wraps_invalid_json_output(monkeypatch, tmp_path):
    fake_python = tmp_path / "python3"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)
    monkeypatch.setattr(signals, "LAYA_VENV_PYTHON", fake_python)

    class FakeCompletedProcess:
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompletedProcess())
    with pytest.raises(EvidenceError) as exc_info:
        signals._run_laya_worker("testo", timeout=1)
    assert exc_info.value.code == "LAYA_INVALID_OUTPUT"
