#!/usr/bin/env python3
"""Property status/deadline signals via the local Laya MLX runtime. Reads a JSON
request ({"text": "..."}) from stdin, prints ONE JSON result object to stdout,
nothing else. Any failure -> message to stderr, exit 1.

Runs only under the isolated venv at ~/GMV/models/laya/.venv (laya-mlx/mlx are
not installed in this project's main .venv — same reason and same shape as
ocr_paddleocr_pdf.py's PaddleOCR isolation: a heavy, platform-specific
dependency kept out of the tracked dependency set and invoked as a subprocess
instead). Never imported by gmv_property_signals.py; only executed as a
subprocess, so `laya_mlx` is imported lazily inside load_agent(), not at
module top level — this file must stay importable (for its pure helper
functions) in the main venv where laya_mlx is absent.

Question schema, the regex/OR combination for scadenza_presente, and the
3-noul risk-level derivation are ported from
~/GMV/models/laya/scripts/gmv_mitigated_schema.py, validated there against 10
generic + 14 real-estate cases (see ~/GMV/models/laya/results/
real_estate_validation_summary.md): scadenza_presente 14/14, rischio_alto
10/10 true negatives but only 2/4 true positives (low recall — never read a
False here as "no risk"), dominio 11/14 with a known blind spot on informal
maintenance/damage reports.

Chunking (below) is NEW here, not part of that validation. Empirical finding
that motivated it (measured live on this checkpoint, 2026-09-27, not assumed):
with the production question set, `usage.input_tokens` hard-caps at 5120 and
any content past that point is silently dropped with no error and no flag in
the output. Worse, a deadline signal placed near the end of an all-filler
document degraded from P(true)=0.99 at ~500 chars of leading filler to
P(true)=0.003 at ~4000+ chars — well before the 5120-token hard cap, so this
is dilution, not just truncation. A real lease/contract can easily put its
operative deadline clause past that point. CHUNK_CHARS below was chosen from
this measurement (comfortably under where degradation started), but the
chunking+aggregation strategy itself has NOT been validated against real long
documents — only against the short, single-paragraph exploratory suite. Treat
any `n_chunks > 1` result as lower-confidence until that gap is closed.

Live-verified consequence of OR-aggregating rischio_alto across chunks (not
just theorized): on a 6000-char synthetic document, chunking correctly
recovered a deadline buried at the end (single-call P(true)=0.003 -> chunked
P(true)=0.95, confirming the fix works) but ALSO raised rischio_alto to
P=0.90 on text with no real structural/safety risk, just a "penali severe"
(severe penalties) phrase in one chunk. Asking rischio_alto once per chunk and
OR-ing the results necessarily raises its false-positive rate above the
10/10-true-negative figure validated in the single-call exploratory suite —
more independent chances for one chunk to cross 0.5 by chance. This is a
known, accepted tradeoff (missing a real risk is worse than one extra false
positive for a signal already documented as advisory-only), not an oversight.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys

MODEL = "aac6fef/laya-multilingual-mlx"
REVISION = "f2b4faf51023039425946074e2cf1361d2db11d5"  # pragma: allowlist secret -- pinned public HF model revision hash, not a credential
DTYPE = "float16"

# Chosen from a live measurement on this checkpoint (see module docstring):
# degradation on a deadline signal was already visible by ~2000 chars of
# leading filler. 1500 stays under that with margin. Not re-derived from a
# tokenizer count -- laya-mlx exposes no tokenizer, only agent.predict()'s
# own usage.input_tokens after the fact.
CHUNK_CHARS = 1500
CHUNK_OVERLAP_CHARS = 200

QUESTION_SET_VERSION = "0.1"

DOMINIO = {
    "type": "choice",
    "instructions": (
        "A quale dominio appartiene principalmente questo contenuto? "
        "Rispondi 'non_determinabile' se il testo non lo chiarisce."
    ),
    "criteria": {
        "arte": "mostre, opere, progetti artistici",
        "real_estate": "immobili, contratti di locazione, manutenzione",
        "amministrazione": "fatture, pagamenti, amministrazione di conto",
        "comunicazione": "email, richieste di risposta, corrispondenza",
        "altro": "nessuno dei precedenti",
        "non_determinabile": "il testo non fornisce elementi sufficienti per decidere",
    },
}

SCADENZA_PRESENTE = {
    "type": "noul",
    "instructions": "Il testo contiene una scadenza operativa esplicita (una data o un termine assoluto)?",
    "criteria": {
        "false": "il testo non indica alcuna data o termine entro cui fare qualcosa",
        "true": "il testo indica una data o un termine entro cui fare qualcosa",
    },
}

RISCHIO_ALTO = {
    "type": "noul",
    "instructions": (
        "Il testo descrive un rischio operativo alto "
        "(es. danno strutturale, perdita economica rilevante, urgenza dichiarata)?"
    ),
    "criteria": {
        "false": "non c'è un rischio grave o urgente",
        "true": "il testo descrive un rischio grave o urgente",
    },
}

RISCHIO_MEDIO = {
    "type": "noul",
    "instructions": "Il testo descrive un rischio operativo medio (una conseguenza concreta ma non grave se non si agisce)?",
    "criteria": {
        "false": "non c'è una conseguenza concreta se non si agisce",
        "true": "il testo descrive una conseguenza concreta ma non grave se non si agisce",
    },
}

RISCHIO_BASSO = {
    "type": "noul",
    "instructions": "Il testo descrive un rischio operativo basso (una routine amministrativa senza conseguenze gravi)?",
    "criteria": {
        "false": "non c'è nemmeno un rischio basso: è irrilevante o assente",
        "true": "il testo descrive una situazione di routine con un rischio minimo",
    },
}

# Same set validated in real_estate_validation_summary.md: dominio + scadenza_presente
# + all three rischio_* together (medio/basso are asked, not just alto, because the
# validated numbers were measured with all three in the same call -- see
# mitigation_summary.md §4 on why the exact question-set composition matters).
PRODUCTION_QUESTIONS = {
    "dominio": DOMINIO,
    "scadenza_presente": SCADENZA_PRESENTE,
    "rischio_alto": RISCHIO_ALTO,
    "rischio_medio": RISCHIO_MEDIO,
    "rischio_basso": RISCHIO_BASSO,
}

# Excludes bare "nelle prossime settimane" / "nel prossimo trimestre" on purpose --
# see gmv_mitigated_schema.py's own note: that phrasing is the ambiguity suite's
# vague-non-deadline wording and produced a real false positive there.
RELATIVE_DEADLINE_PATTERNS = [
    r"entro\s+la\s+fine\s+del\s+mese",
    r"entro\s+la\s+fine\s+dell.anno",
    r"entro\s+la\s+fine\s+della\s+settimana",
    r"entro\s+il\s+(\d+\s+del\s+)?(mese|trimestre|anno)\s+prossimo",
    r"entro\s+\d+\s+giorni",
    r"entro\s+\d+\s+settiman[ae]",
    r"entro\s+breve",
    r"quanto\s+prima",
]
_RELATIVE_DEADLINE_RE = re.compile("|".join(RELATIVE_DEADLINE_PATTERNS), re.IGNORECASE)


def relative_deadline_detected(text: str) -> bool:
    return bool(_RELATIVE_DEADLINE_RE.search(text))


def combined_scadenza_presente(text: str, noul_p_true: float, threshold: float = 0.5) -> bool:
    return (noul_p_true >= threshold) or relative_deadline_detected(text)


def derived_rischio_level(p_alto: float, p_medio: float, p_basso: float, threshold: float = 0.5) -> str:
    if p_alto >= threshold:
        return "alto"
    if p_medio >= threshold:
        return "medio"
    if p_basso >= threshold:
        return "basso"
    return "nessuno"


def chunk_text(text: str, chunk_chars: int = CHUNK_CHARS, overlap_chars: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Fixed-window chunking with overlap so a deadline phrase straddling a
    chunk boundary is not silently split in half. Not sentence-aware (unlike
    gmv_evidence_pipeline.py's deterministic_chunks/adaptive_split_chunk) --
    deliberately kept simple since this is unvalidated territory; sentence-aware
    splitting is a candidate improvement once real long-document cases exist."""
    text = text.strip()
    if len(text) <= chunk_chars:
        return [text] if text else [""]
    chunks = []
    step = max(chunk_chars - overlap_chars, 1)
    for start in range(0, len(text), step):
        chunk = text[start:start + chunk_chars]
        if chunk:
            chunks.append(chunk)
        if start + chunk_chars >= len(text):
            break
    return chunks


def load_agent():
    import laya_mlx as laya  # noqa: E402 - deliberately lazy, see module docstring

    return laya.load(MODEL, dtype=DTYPE, revision=REVISION)


EXCERPT_CHARS = 300
EXCERPT_CONTEXT_CHARS = 80


def _excerpt(chunk: str) -> str:
    """A short, human-checkable text snippet for a positive scadenza_presente
    chunk -- required because a downstream governed claim (gmv_property_claims.py)
    must carry a real evidence_excerpt, never an unsupported assertion (mirrors
    gmv_evidence_pipeline's own CLAIM_WITHOUT_EVIDENCE guard). Centers on the
    regex match when there is one (the more informative anchor); otherwise takes
    a leading slice, since the noul alone gives no span to anchor on."""
    match = _RELATIVE_DEADLINE_RE.search(chunk)
    if match:
        start = max(match.start() - EXCERPT_CONTEXT_CHARS, 0)
        end = min(match.end() + EXCERPT_CONTEXT_CHARS, len(chunk))
        return chunk[start:end].strip()
    return chunk[:EXCERPT_CHARS].strip()


def predict_chunk(agent, chunk: str) -> dict:
    result = agent.predict(chunk, PRODUCTION_QUESTIONS)
    answers = result["answers"]
    p_scad = answers["scadenza_presente"]["noul"]
    p_alto = answers["rischio_alto"]["noul"]
    p_medio = answers["rischio_medio"]["noul"]
    p_basso = answers["rischio_basso"]["noul"]
    return {
        "dominio": answers["dominio"].get("choice"),
        "scadenza_p_true": p_scad,
        "scadenza_combined": combined_scadenza_presente(chunk, p_scad),
        "regex_relative_deadline": relative_deadline_detected(chunk),
        "scadenza_excerpt": _excerpt(chunk),
        "rischio_p_alto": p_alto,
        "rischio_p_medio": p_medio,
        "rischio_p_basso": p_basso,
        "rischio_level": derived_rischio_level(p_alto, p_medio, p_basso),
        "usage": result.get("usage", {}),
    }


def aggregate(chunk_results: list[dict], text: str) -> dict:
    """OR-style aggregation for presence questions (a deadline/risk anywhere in
    the document counts), majority vote for dominio (a document's domain is
    usually stable across its own chunks; disagreement is surfaced, not hidden)."""
    scad_true = any(c["scadenza_combined"] for c in chunk_results)
    scad_p = max(c["scadenza_p_true"] for c in chunk_results)
    # The excerpt must come from a chunk whose own text actually supports the
    # claim, not just whichever positive chunk had the highest model probability.
    # A regex-anchored chunk (a real "entro ..." match) is preferred over a
    # model-only positive chunk: on a multi-chunk document (the norm, not the
    # exception, at CHUNK_CHARS=1500) picking by p_true alone could attach an
    # excerpt from an unrelated high-confidence chunk that does not itself
    # mention a deadline -- found by live review, not by inspection alone.
    # KNOWN RESIDUAL GAP, re-verified live after this fix: RELATIVE_DEADLINE_PATTERNS
    # only covers relative phrasing ("entro la fine del mese"), not absolute dates
    # ("entro il 10 ottobre") -- an absolute-date deadline is caught by the noul
    # alone, with no regex anchor at all. When every positive chunk lacks a regex
    # match (the common case for absolute dates), this still falls back to
    # highest-p_true, which can still select a non-supporting filler chunk over the
    # one actually containing the date -- reproduced live on a 6000-char synthetic
    # document. Not fixed here: would require a second, broader regex for absolute
    # dates too, a new unvalidated capability out of this session's minimal scope.
    positive_chunks = [c for c in chunk_results if c["scadenza_combined"]]
    regex_chunks = [c for c in positive_chunks if c["regex_relative_deadline"]]
    excerpt_pool = regex_chunks or positive_chunks
    scad_excerpt = max(excerpt_pool, key=lambda c: c["scadenza_p_true"])["scadenza_excerpt"] if excerpt_pool else None
    alto_true = any(c["rischio_p_alto"] >= 0.5 for c in chunk_results)
    alto_p = max(c["rischio_p_alto"] for c in chunk_results)

    dominio_votes = [c["dominio"] for c in chunk_results]
    dominio_counts = {v: dominio_votes.count(v) for v in set(dominio_votes)}
    dominio_top = max(dominio_counts, key=dominio_counts.get)
    dominio_agreement = dominio_counts[dominio_top] == len(dominio_votes)

    return {
        "dominio": dominio_top,
        "dominio_agreement_across_chunks": dominio_agreement,
        "dominio_votes": dominio_counts,
        "scadenza_presente": {
            "value": scad_true,
            "p_true_max": scad_p,
            "regex_relative_deadline_any_chunk": any(c["regex_relative_deadline"] for c in chunk_results),
            "evidence_excerpt": scad_excerpt,
        },
        "rischio": {
            "alto": alto_true,
            "p_alto_max": alto_p,
            "reliability": "low_recall_advisory",
            "reliability_note": (
                "Validated true-negative rate 10/10; true-positive recall only 2/4 "
                "(missed an explicit structural-collapse warning). A False here must "
                "never be read as 'no risk' -- pair with human review of the source "
                "text, never surface as a standalone verdict."
            ),
        },
        "text_chars_total": len(text),
        "n_chunks": len(chunk_results),
        "chunk_chars": CHUNK_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "chunking_validated": False,
        "input_tokens_per_chunk": [c["usage"].get("input_tokens") for c in chunk_results],
    }


def run(agent, text: str) -> dict:
    chunks = chunk_text(text)
    chunk_results = [predict_chunk(agent, c) for c in chunks]
    result = aggregate(chunk_results, text)
    result.update({
        "model": MODEL,
        "revision": REVISION,
        "question_set_version": QUESTION_SET_VERSION,
    })
    return result


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        text = request["text"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"invalid request: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    try:
        # laya_mlx/mlx/huggingface_hub can print banners or download progress to
        # stdout on some versions (the exact class of problem ocr_paddleocr_pdf.py
        # already hit with PaddleOCR); stdout must stay a pure single-JSON-object
        # contract for the caller, so redirect it to stderr for the duration.
        with contextlib.redirect_stdout(sys.stderr):
            agent = load_agent()
            result = run(agent, text)
    except Exception as exc:  # noqa: BLE001 - any failure here must surface as a clear non-zero exit
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
