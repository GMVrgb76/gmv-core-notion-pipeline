#!/usr/bin/env python3
"""
Validatore Area35 Archive — controllo qualità delle schede Notion in vista della
proiezione verso monade (.md, GMV_KNOWLEDGE_MONAD_SPEC_v1.0).

Ambito verificato dallo strumento: struttura, integrità referenziale, coerenza
temporale (object-time), risolvibilità della fonte, disciplina epistemica dello
stato, coerenza del gate di pubblicazione (SPEC §14). NON verifica la verità dei
fatti: misura il rischio di errore, non l'errore.

Ingresso normalizzato (JSON):
  { "artista": [ {"id","titolo","campi":{...},"relazioni":{k:[...]},"servizio":{...},"corpo": "..."} ], ... }
Gli adattatori (SQL Notion o REST) producono questa forma; il motore non conosce la sorgente.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

SEV = {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2, "INFO": 3}


# --------------------------------------------------------------------------- #
# Modello
# --------------------------------------------------------------------------- #

@dataclass
class Record:
    id: str
    entita: str
    titolo: str
    campi: dict = field(default_factory=dict)
    relazioni: dict = field(default_factory=dict)
    servizio: dict = field(default_factory=dict)
    corpo: str = ""


@dataclass
class Issue:
    codice: str; severita: str; entita: str; record_id: str; titolo: str
    campo: str; messaggio: str; azione: str = ""


def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def vuoto(v):
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, dict)) and not v)


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if not vuoto(x)]
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                return [x for x in json.loads(s) if not vuoto(x)]
            except Exception:
                pass
        return [p.strip() for p in s.split(",") if p.strip()]
    return [v]


FMT = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y")


def parse_data(v):
    if vuoto(v):
        return None
    s = re.split(r"[T\u2192]|\s+->\s+|\s+→\s+", str(v).strip())[0].strip()
    for f in FMT:
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    m = re.search(r"\b(1[89]\d{2}|20\d{2})\b", s)
    return dt.date(int(m.group(1)), 1, 1) if m else None


def parse_anno(v):
    if vuoto(v):
        return None
    m = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", str(v))
    return int(m.group(1)) if m else None


def testo(v):
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return "" if v is None else str(v)


# --------------------------------------------------------------------------- #
# Helper di servizio (per-entità)
# --------------------------------------------------------------------------- #

def stato_epistemico(cfg, valore):
    """Mappa un'opzione di stato Notion sullo stato epistemico monade."""
    return cfg["mappa_stato_epistemico"].get(norm(valore))


def livello_fonte(cfg, url):
    u = norm(url)
    if not u:
        return None
    if "dropbox" in u:
        return "CANONICAL_SUM"
    if re.match(r"^https?", str(url).strip().lower()):
        return "EXTERNAL_WEB"
    return "IGNOTO"


# --------------------------------------------------------------------------- #
# Regole
# --------------------------------------------------------------------------- #

def _iss(r, c, s, campo, msg, az=""):
    return Issue(c, s, r.entita, r.id, r.titolo, campo, msg, az)


def r_struttura(corpus, cfg):
    out = []
    for r in corpus:
        spec = cfg["entita"].get(r.entita)
        if not spec:
            continue
        for k, m in spec["campi"].items():
            v = r.campi.get(k)
            if vuoto(v):
                if m.get("obbligatorio"):
                    out.append(_iss(r, "S01", "BLOCKER", k, f"Campo obbligatorio '{m['notion']}' assente.",
                                    "Compilare o marcare la scheda come non pubblicabile."))
                elif m.get("peso", 0) >= 2:
                    out.append(_iss(r, "S02", "MINOR", k, f"Campo rilevante '{m['notion']}' non valorizzato."))
                continue
            t = m.get("tipo")
            if t == "data" and parse_data(v) is None:
                out.append(_iss(r, "S03", "MAJOR", k, f"Data non interpretabile: {v!r}."))
            elif t == "anno" and parse_anno(v) is None:
                out.append(_iss(r, "S03", "MAJOR", k, f"Anno non interpretabile: {v!r}."))
            elif t == "intero" and not re.fullmatch(r"-?\d+(\.\d+)?", testo(v).strip()):
                out.append(_iss(r, "S03", "MINOR", k, f"Valore non numerico: {v!r}."))
    return out


def r_relazioni(corpus, cfg):
    out = []
    idx_tit = {(r.entita, norm(r.titolo)): r for r in corpus}
    idx_id = {r.id: r for r in corpus}
    inbound = defaultdict(int)

    def risolvi(target, rif):
        return idx_id.get(rif) or idx_tit.get((target, norm(rif)))

    for r in corpus:
        spec = cfg["entita"].get(r.entita, {})
        for k, m in spec.get("relazioni", {}).items():
            vals = as_list(r.relazioni.get(k))
            if not vals:
                if m.get("obbligatoria"):
                    out.append(_iss(r, "R01", "BLOCKER", k, f"Relazione obbligatoria '{m['notion']}' vuota.",
                                    f"Collegare almeno un record '{m['target']}'."))
                continue
            for v in vals:
                b = risolvi(m["target"], v)
                if b is None:
                    out.append(_iss(r, "R02", "MAJOR", k, f"Riferimento non risolto: '{v}' (atteso '{m['target']}').",
                                    "Creare la scheda mancante o correggere la denominazione."))
                else:
                    inbound[b.id] += 1

    for r in corpus:
        spec = cfg["entita"].get(r.entita, {})
        for k, m in spec.get("relazioni", {}).items():
            inv = m.get("inversa")
            if not inv:
                continue
            for v in as_list(r.relazioni.get(k)):
                b = risolvi(m["target"], v)
                if b is None:
                    continue
                ritorno = as_list(b.relazioni.get(inv))
                if not any(norm(x) == norm(r.titolo) or x == r.id for x in ritorno):
                    out.append(_iss(r, "R03", "MINOR", k,
                                    f"Relazione asimmetrica: '{b.titolo}' non riporta '{r.titolo}' in '{inv}'."))

    for r in corpus:
        if inbound.get(r.id, 0) == 0 and not any(as_list(r.relazioni.get(k)) for k in r.relazioni):
            out.append(_iss(r, "R04", "MAJOR", "-", "Record isolato: nessuna relazione in entrata né in uscita.",
                            "Collegare o escludere dall'export."))
    return out


def r_temporale(corpus, cfg):
    out = []
    c = cfg["corpus"]
    da = parse_data(c.get("attivita_da"))
    a = parse_data(c.get("attivita_a")) or dt.date.today()
    amin, amax = c.get("anno_minimo_plausibile", 1900), c.get("anno_massimo_plausibile", 2030)
    idx = {(r.entita, norm(r.titolo)): r for r in corpus}
    idx_id = {r.id: r for r in corpus}

    def risolvi_artista(rif):
        """Resolve the normalized relation contract: URL/ID first, title as fallback."""
        return idx_id.get(rif) or idx.get(("artista", norm(rif)))

    for r in corpus:
        if r.entita == "mostra":
            di = parse_data(r.campi.get("data")) or parse_data(r.servizio.get("data_start"))
            df = parse_data(r.servizio.get("data_end"))
            if di and df and df < di:
                out.append(_iss(r, "T01", "BLOCKER", "data", f"Fine ({df}) anteriore all'inizio ({di})."))
            if di and da and di < da:
                out.append(_iss(r, "T02", "MAJOR", "data", f"Mostra ({di}) anteriore all'inizio attività dichiarato ({da})."))
            if di and di > a:
                out.append(_iss(r, "T02", "MINOR", "data", f"Mostra ({di}) successiva alla fine attività ({a})."))
            for nome in as_list(r.relazioni.get("artisti")):
                art = risolvi_artista(nome)
                if art and di:
                    n = parse_anno(art.campi.get("anno_nascita"))
                    if n and di.year < n:
                        out.append(_iss(r, "T03", "BLOCKER", "data",
                                        f"Mostra nel {di.year} con artista '{art.titolo}' nato nel {n}."))
        if r.entita == "artista":
            n = parse_anno(r.campi.get("anno_nascita"))
            if n and not (amin <= n <= amax):
                out.append(_iss(r, "T05", "MAJOR", "anno_nascita", f"Anno fuori intervallo plausibile: {n}."))
        if r.entita == "opera":
            an = parse_anno(r.campi.get("anno"))
            if an and not (amin <= an <= amax):
                out.append(_iss(r, "T05", "MINOR", "anno", f"Anno opera fuori intervallo: {an}."))
    return out


def r_monade(corpus, cfg):
    """Famiglia critica: risolvibilità fonte, disciplina epistemica, gate PUBLIC (SPEC §5,§13,§14)."""
    out = []
    giorni = cfg["corpus"].get("obsolescenza_verifica_giorni", 730)
    oggi = dt.date.today()

    for r in corpus:
        spec = cfg["entita"].get(r.entita)
        if not spec:
            continue
        srv = spec.get("servizio", {})

        # --- stato / disciplina epistemica ---
        stato_meta = srv.get("stato")
        stato_val = r.servizio.get("stato")
        epist = None
        if stato_meta:
            if vuoto(stato_val):
                out.append(_iss(r, "M04", "MAJOR", stato_meta["notion"],
                                "Stato scheda non impostato: nessun segnale epistemico per la proiezione monade.",
                                "Impostare lo stato; in monade diventa lo STATUS dell'atomo."))
            else:
                epist = stato_epistemico(cfg, stato_val)
                if epist is None:
                    out.append(_iss(r, "M04", "MINOR", stato_meta["notion"],
                                    f"Valore di stato '{stato_val}' non mappabile su uno stato epistemico monade."))

        # --- fonte / risolvibilità verso SUM ---
        fonti_meta = srv.get("fonti", [])
        ha_campo_fonte = bool(fonti_meta)
        valore_fonte = None
        livello = None
        for fm in fonti_meta:
            key = f"fonte::{fm['notion']}"
            v = r.servizio.get(key) or r.servizio.get(fm["notion"])
            if not vuoto(v):
                valore_fonte = v
                livello = livello_fonte(cfg, v)
                break

        if not ha_campo_fonte:
            out.append(_iss(r, "M01", "MAJOR", "-",
                            f"L'entità '{r.entita}' non ha alcun campo-fonte: la scheda non è ancorabile a evidenza canonica (SUM).",
                            "Difetto di schema: valutare l'aggiunta di un campo 'Fonte Dropbox' (url)."))
        elif vuoto(valore_fonte):
            out.append(_iss(r, "M02", "MAJOR", fonti_meta[0]["notion"],
                            "Fonte non valorizzata: la scheda non è risolvibile verso evidenza (ATOM → SOURCE → SUM).",
                            "Inserire il locator della fonte canonica."))
        elif livello == "EXTERNAL_WEB":
            out.append(_iss(r, "M03", "INFO", fonti_meta[0]["notion"],
                            "Fonte è un URL esterno, non un locator Dropbox/SUM: evidenza più debole.",
                            "Dove possibile, ancorare a SUM oltre che al web."))

        # --- obsolescenza verifica ---
        vmeta = srv.get("verificato_il")
        if vmeta:
            vd = parse_data(r.servizio.get(vmeta["notion"]) or r.servizio.get("verificato_il"))
            if vd is None and epist == "VALID":
                out.append(_iss(r, "M06", "MINOR", vmeta["notion"],
                                "Scheda 'Verificata' ma senza data di verifica: obsolescenza non valutabile."))
            elif vd and (oggi - vd).days > giorni:
                out.append(_iss(r, "M06", "MINOR", vmeta["notion"],
                                f"Verifica risalente a {vd} ({(oggi - vd).days} giorni)."))

        # --- gate di pubblicazione (SPEC §14) ---
        pmeta = srv.get("pubblicabile")
        if pmeta:
            pub = norm(r.servizio.get(pmeta["notion"]) or r.servizio.get("pubblicabile"))
            pubblicabile = pub in ("yes", "__yes__", "true", "1", "si", "vero")
            if pubblicabile:
                if epist != "VALID":
                    out.append(_iss(r, "M07", "MAJOR", pmeta["notion"],
                                    f"Pubblicabile ma stato non verificato ('{stato_val}' → {epist or 'ignoto'}). "
                                    "Violazione §14: claim UNVERIFIED verso PUBLIC.",
                                    "Verificare la scheda prima di pubblicarla, o togliere Pubblicabile."))
                if ha_campo_fonte and vuoto(valore_fonte):
                    out.append(_iss(r, "M07", "MAJOR", pmeta["notion"],
                                    "Pubblicabile ma privo di fonte risolvibile (§14: inferenza da fonte assente)."))
                rmeta = srv.get("riservatezza")
                if rmeta:
                    rv = r.servizio.get(rmeta["notion"]) or r.servizio.get("riservatezza")
                    if rv and rv in rmeta.get("valori_non_pubblici", []):
                        out.append(_iss(r, "M08", "BLOCKER", rmeta["notion"],
                                        f"Pubblicabile ma riservatezza '{rv}': §14 vieta dati INTERNAL/confidenziali in PUBLIC."))
                for ce in srv.get("campi_economici", []):
                    if not vuoto(r.campi.get(ce)):
                        out.append(_iss(r, "M08", "BLOCKER", ce,
                                        "Pubblicabile con dato economico privato valorizzato: §14 lo esclude da PUBLIC."))
    return out


def r_testo(corpus, cfg):
    out = []
    lex = cfg["lessico"]
    frasi = Counter(); mappa = defaultdict(list)

    def contiene(nt, marker):
        m = norm(marker)
        return bool(m and re.search(rf"\b{re.escape(m)}\b", nt))

    for r in corpus:
        spec = cfg["entita"].get(r.entita, {})
        blocchi = {k: testo(r.campi.get(k)) for k, m in spec.get("campi", {}).items() if m.get("tipo") == "testo"}
        if r.corpo:
            blocchi["__corpo__"] = r.corpo
        for k, tx in blocchi.items():
            if not tx.strip():
                continue
            nt = norm(tx)
            for mk in lex["placeholder"]:
                if contiene(nt, mk):
                    out.append(_iss(r, "Q01", "BLOCKER", k, f"Residuo di lavorazione: '{mk}'.", "Rimuovere prima dell'export."))
                    break
            if k == "__corpo__" or len(tx) > 200:
                st = tx.rstrip()
                if st and st[-1] not in ".!?»\"')":
                    out.append(_iss(r, "Q02", "MAJOR", k, "Testo senza punteggiatura finale: probabile troncamento."))
                if [t for t in lex["registro_promozionale"] if contiene(nt, t)]:
                    out.append(_iss(r, "Q03", "MINOR", k, "Registro promozionale in un archivio descrittivo."))
                llm = [t for t in lex["marcatori_llm"] if contiene(nt, t)]
                if len(llm) >= 2:
                    out.append(_iss(r, "Q04", "MAJOR", k, f"Stilemi di testo generato: {', '.join(llm[:3])}.",
                                    "Verificare la fonte e i fatti asseriti."))
                if [t for t in lex["vaghezza_datata"] if contiene(nt, t)]:
                    out.append(_iss(r, "Q08", "MINOR", k, "Riferimenti non ancorati (es. 'negli anni'): illeggibili fuori contesto in monade."))
                for f in re.split(r"(?<=[.!?])\s+", tx):
                    f = f.strip()
                    if len(f) > 40:
                        frasi[norm(f)] += 1; mappa[norm(f)].append(r)
    for f, n in frasi.items():
        if n >= 3:
            for r in mappa[f][:n]:
                out.append(_iss(r, "Q07", "MINOR", "-", f"Frase ricorrente in {n} schede: boilerplate."))
    return out


def _forma(nome):
    n = norm(nome)
    if "," in nome:
        n = norm(" ".join(reversed([p.strip() for p in nome.split(",")])))
    return " ".join(sorted(t for t in n.split() if len(t) > 1))


def r_duplicati(corpus, cfg):
    out = []
    for ent, spec in cfg["entita"].items():
        recs = [r for r in corpus if r.entita == ent]
        chiavi = spec.get("chiave_identita", [])
        gruppi = defaultdict(list)
        for r in recs:
            parts = []
            for c in chiavi:
                parts.append(norm(testo(r.campi.get(c))) or norm("|".join(as_list(r.relazioni.get(c)))))
            k = "|".join(parts)
            if k.strip("|"):
                gruppi[k].append(r)
        for g in gruppi.values():
            if len(g) > 1:
                for r in g:
                    out.append(_iss(r, "D01", "BLOCKER", "|".join(chiavi),
                                    f"Chiave di identità duplicata in {len(g)} schede: {[x.id for x in g]}."))
        if ent in ("artista", "persona"):
            for i, a in enumerate(recs):
                for b in recs[i + 1:]:
                    if a.titolo and b.titolo and norm(a.titolo) != norm(b.titolo) and _forma(a.titolo) == _forma(b.titolo):
                        out.append(_iss(a, "D02", "MAJOR", "-",
                                        f"Probabile stessa entità con denominazione diversa: '{b.titolo}' ({b.id})."))
    return out


def r_normalizzazione(corpus, cfg):
    """Incoerenze trasversali di schema, emesse una sola volta (findings a livello di corpus)."""
    out = []

    def globale(codice, sev, msg, az=""):
        out.append(Issue(codice, sev, "corpus", "-", "Area35 Archive", "-", msg, az))

    lessici = defaultdict(list)
    for ent, spec in cfg["entita"].items():
        st = spec.get("servizio", {}).get("stato")
        if st:
            lessici[tuple(sorted(norm(o) for o in st["opzioni"]))].append(f"{ent}:{st['notion']}")
    if len(lessici) > 1:
        dettaglio = "; ".join(f"[{', '.join(sorted(v))}]" for v in lessici.values())
        globale("N01", "MINOR",
                f"L'asse di stato usa {len(lessici)} vocabolari diversi tra i database: {dettaglio}.",
                "Unificare su un lessico unico e mappabile agli stati epistemici monade.")

    campi_fonte = defaultdict(list)
    for ent, spec in cfg["entita"].items():
        fonti = spec.get("servizio", {}).get("fonti", [])
        nomi = tuple(f["notion"] for f in fonti) or ("(nessuno)",)
        campi_fonte[nomi].append(ent)
    if len(campi_fonte) > 1:
        dettaglio = "; ".join(f"{'/'.join(k)} → {', '.join(v)}" for k, v in campi_fonte.items())
        globale("N03", "MINOR",
                f"Il campo-fonte ha nomi/semantiche diverse tra i database: {dettaglio}.",
                "Uniformare l'ancora di provenienza; garantire un locator Dropbox dove la fonte canonica è SUM.")

    senza_fonte = [ent for ent, spec in cfg["entita"].items() if not spec.get("servizio", {}).get("fonti")]
    if senza_fonte:
        globale("N04", "MAJOR",
                f"Entità prive di qualsiasi campo-fonte: {', '.join(senza_fonte)}. Ogni loro scheda è, per schema, non ancorabile a SUM.",
                "Aggiungere un campo 'Fonte Dropbox' (url) a queste entità.")
    return out


REGOLE = [r_struttura, r_relazioni, r_temporale, r_monade, r_testo, r_duplicati, r_normalizzazione]


def esegui(corpus, cfg):
    issues = []
    for reg in REGOLE:
        try:
            issues += reg(corpus, cfg)
        except Exception as e:
            print(f"[errore] regola {reg.__name__}: {e}", file=sys.stderr)
    issues.sort(key=lambda i: (SEV.get(i.severita, 9), i.entita, i.titolo, i.codice))
    return issues


# --------------------------------------------------------------------------- #
# Punteggi
# --------------------------------------------------------------------------- #

@dataclass
class Punteggio:
    r: Record; completezza: float; epistemico: str; blockers: int; majors: int; minors: int
    esportabile: bool; motivi: list


def punteggi(corpus, cfg, issues):
    per = defaultdict(list)
    for i in issues:
        per[i.record_id].append(i)
    out = []
    for r in corpus:
        spec = cfg["entita"].get(r.entita)
        if not spec:
            continue
        tot = ok = 0
        for k, m in spec["campi"].items():
            p = m.get("peso", 1); tot += p
            if not vuoto(r.campi.get(k)):
                ok += p
        for k, m in spec.get("relazioni", {}).items():
            p = 3 if m.get("obbligatoria") else 1; tot += p
            if as_list(r.relazioni.get(k)):
                ok += p
        comp = ok / tot if tot else 0.0
        epist = stato_epistemico(cfg, r.servizio.get("stato")) or "UNVERIFIED"
        mine = per.get(r.id, [])
        b = sum(1 for i in mine if i.severita == "BLOCKER")
        mj = sum(1 for i in mine if i.severita == "MAJOR")
        mn = sum(1 for i in mine if i.severita == "MINOR")
        motivi = []
        if b:
            motivi.append(f"{b} bloccanti")
        if comp < cfg["soglie_export"]["completezza_minima"]:
            motivi.append(f"completezza {comp:.0%}")
        out.append(Punteggio(r, comp, epist, b, mj, mn, not motivi, motivi))
    out.sort(key=lambda p: (p.esportabile, p.completezza))
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def carica_rows(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    corpus = []
    for ent, righe in data.items():
        for i, row in enumerate(righe):
            corpus.append(Record(
                id=row.get("id") or f"{ent}:{i:05d}",
                entita=ent,
                titolo=row.get("titolo", ""),
                campi=row.get("campi", {}),
                relazioni=row.get("relazioni", {}),
                servizio=row.get("servizio", {}),
                corpo=row.get("corpo", ""),
            ))
    return corpus


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--rows", required=True, help="JSON normalizzato {entita:[righe]}")
    ap.add_argument("--out", default="report")
    args = ap.parse_args()
    cfg = json.load(open(args.config, encoding="utf-8"))
    corpus = carica_rows(args.rows)
    issues = esegui(corpus, cfg)
    pts = punteggi(corpus, cfg, issues)

    import os
    os.makedirs(args.out, exist_ok=True)
    with open(f"{args.out}/issues.json", "w", encoding="utf-8") as f:
        json.dump([i.__dict__ for i in issues], f, ensure_ascii=False, indent=2)

    conteggi = Counter(i.severita for i in issues)
    esp = sum(1 for p in pts if p.esportabile)
    print(f"Schede: {len(pts)} | Esportabili: {esp} | " +
          " ".join(f"{s}:{conteggi.get(s,0)}" for s in ("BLOCKER", "MAJOR", "MINOR", "INFO")))
    return 1 if conteggi.get("BLOCKER") else 0


if __name__ == "__main__":
    sys.exit(main())
