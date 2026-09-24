"""
title: GMV Crawler Review
description: Legge e corregge le code di revisione del crawler GMV (predicati non riconosciuti, tipi di entita' da verificare).
"""
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(
    "/Users/giacomomarcovalerio/.gmv_core/.claude/worktrees/bridge-cse_01EFSz2nNresRvPh9GbfwwzK"
)
INSTITUTIONS_PATH = REPO_ROOT / "00_CONFIG" / "area35_known_institutions.json"
PREDICATE_MAPPING_PATH = REPO_ROOT / "00_CONFIG" / "crawler_predicate_text_mapping.json"
ONTOLOGY_REGISTRY_PATH = REPO_ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"
RUNTIME_DIR = REPO_ROOT / "01_RUNTIME" / "gmv_crawler"
REJECTION_QUEUE_PATH = RUNTIME_DIR / "rejection_queue.jsonl"
ENTITY_PROPOSAL_QUEUE_PATH = RUNTIME_DIR / "entity_proposal_queue.jsonl"
RUN_LOG_PATH = RUNTIME_DIR / "run_log.jsonl"
ATOMS_LOG_PATH = RUNTIME_DIR / "atoms_built.jsonl"
PRICE_LOG_PATH = RUNTIME_DIR / "price_log.jsonl"
CONTRACT_LOG_PATH = RUNTIME_DIR / "contract_log.jsonl"
RUN_NIGHTLY_SCRIPT = REPO_ROOT / "automation" / "run_nightly.sh"
# Chat-triggered runs used to redirect to DEVNULL -- a run that failed to
# even start (wrong path, bad env) looked identical to "started fine" from
# here, and check_last_run_status() could only ever report the last
# COMPLETED run, so a run still in progress looked like a stale failure.
# Found live 2026-09-18 when a chat-triggered run apparently never started
# (no process, no log) and the user was shown Dropbox history from hours
# earlier. Real files + a PID lock fix both problems at once.
CHAT_STDOUT_LOG = RUNTIME_DIR / "chat_triggered_stdout.log"
CHAT_STDERR_LOG = RUNTIME_DIR / "chat_triggered_stderr.log"
RUN_PID_FILE = RUNTIME_DIR / "current_run.pid"


def _running_pid() -> int | None:
    """None if no run is in progress. Self-healing: a PID file left over
    from a crashed/killed run is detected as stale and treated as
    not-running, no separate cleanup step needed.

    Real bug found live 2026-09-19: os.kill(pid, 0) alone isn't enough --
    a process killed via pkill can sit as a <defunct> ZOMBIE for a while,
    still holding its PID slot, so kill(0) alone kept reporting "still
    running" and blocked every real run behind it. `ps -o stat=` reveals
    the zombie state (leading 'Z') that kill(0) cannot see."""
    if not RUN_PID_FILE.exists():
        return None
    try:
        pid = int(RUN_PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
    except (ValueError, ProcessLookupError, PermissionError):
        return None
    try:
        stat = subprocess.run(  # noqa: S603, S607 -- fixed system binary, pid is our own int
            ["/bin/ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 -- if we can't tell, err toward "still running" (safer than a duplicate run)
        return pid
    if stat.startswith("Z"):
        return None
    return pid


class Tools:
    def run_crawler_now(self) -> str:
        """Avvia subito una scansione del crawler (la stessa cosa che gira
        di notte alle 3), senza aspettare la schedulazione automatica.
        Usa questo strumento quando l'utente chiede esplicitamente di far
        partire, avviare, lanciare o eseguire ora il crawler.
        IMPORTANTE: questo strumento restituisce solo la CONFERMA che la
        scansione e' partita, non il risultato -- la scansione reale
        richiede alcuni minuti in background. Per sapere come e' andata,
        l'utente deve richiedere check_last_run_status() poco dopo (es.
        dopo un paio di minuti)."""
        if not RUN_NIGHTLY_SCRIPT.exists():
            return f"ERRORE: script non trovato in {RUN_NIGHTLY_SCRIPT}."
        already_running = _running_pid()
        if already_running is not None:
            return (
                f"Una scansione e' gia' in corso (processo {already_running}) -- "
                "non ne avvio una seconda in parallelo. Chiedimi 'controlla l'ultima "
                "esecuzione' per lo stato, oppure riprova piu' tardi."
            )
        with CHAT_STDOUT_LOG.open("a", encoding="utf-8") as out, CHAT_STDERR_LOG.open("a", encoding="utf-8") as err:
            process = subprocess.Popen(  # noqa: S603 -- fixed local script path, no external input
                [str(RUN_NIGHTLY_SCRIPT)],
                stdout=out, stderr=err,
                start_new_session=True,
            )
        RUN_PID_FILE.write_text(str(process.pid), encoding="utf-8")
        return (
            "Scansione avviata in background sulle cartelle artista configurate. "
            "Richiedimi 'controlla l'ultima esecuzione' tra un paio di minuti per sapere l'esito."
        )

    def check_last_run_status(self) -> str:
        """Dice se l'esecuzione notturna del crawler (le 3 di notte) ha
        funzionato l'ultima volta o e' fallita, e perche'. Usa SEMPRE
        questo strumento per primo quando l'utente chiede com'e' andata
        la notte o se ci sono novita' -- le altre funzioni leggono solo
        le code, non dicono se la scansione stessa e' riuscita."""
        running_pid = _running_pid()
        if running_pid is not None:
            return (
                f"Una scansione e' attualmente in corso (processo {running_pid}). "
                "Non e' ancora finita -- il risultato qui sotto, se presente, si "
                "riferisce all'esecuzione PRECEDENTE, non a questa. Richiedi di nuovo "
                "tra qualche minuto."
            )
        if not RUN_LOG_PATH.exists():
            return "Il crawler non ha ancora mai completato un'esecuzione."
        last_complete = None
        for line in RUN_LOG_PATH.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("event") == "run_complete":
                last_complete = row
        if last_complete is None:
            return "Nessuna esecuzione completata trovata nel log."
        if last_complete.get("scan_failed"):
            return (
                f"ATTENZIONE: l'ultima esecuzione ({last_complete['at']}) e' fallita "
                "nella lettura di Dropbox -- molto probabilmente il token di accesso "
                "e' scaduto. La pipeline non ha elaborato nulla di nuovo finche' non "
                "viene fornito un token valido."
            )
        return (
            f"Ultima esecuzione completata alle {last_complete['at']}: "
            f"{last_complete['files_processed']} file elaborati, "
            f"{last_complete['atoms_built']} atomi costruiti, "
            f"{last_complete['needing_review']} elementi da verificare."
        )

    def list_unrecognized_predicates(self) -> str:
        """Elenca i predicati grezzi non riconosciuti dalla pipeline del crawler,
        con quante volte compaiono, cosi' l'utente puo' decidere se e come
        mapparli su un predicato reale governato."""
        if not REJECTION_QUEUE_PATH.exists():
            return "Nessuna coda di scarto trovata."
        seen: dict[str, int] = {}
        for line in REJECTION_QUEUE_PATH.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            key = row["raw_predicate"]
            seen[key] = seen.get(key, 0) + 1
        if not seen:
            return "Nessun predicato in sospeso."
        lines = ["Predicati grezzi non riconosciuti (frequenza):"]
        for pred, count in sorted(seen.items(), key=lambda x: -x[1]):
            lines.append(f'- "{pred}" (x{count})')
        return "\n".join(lines)

    def list_entities_needing_verification(self) -> str:
        """Elenca le entita' (probabili istituzioni, luoghi o altro) che la
        pipeline ha classificato indovinando, senza un fatto verificato --
        vanno mostrate all'utente perche' confermi o corregga, mai date per
        buone automaticamente."""
        if not ENTITY_PROPOSAL_QUEUE_PATH.exists():
            return "Nessuna entita' in sospeso."
        seen: dict[tuple[str, str], int] = {}
        for line in ENTITY_PROPOSAL_QUEUE_PATH.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            key = (row["entity_name"], row["entity_type"])
            seen[key] = seen.get(key, 0) + 1
        if not seen:
            return "Nessuna entita' in sospeso."
        lines = ["Entita' da verificare (il tipo e' una proposta, non un fatto confermato):"]
        for (name, entity_type), count in sorted(seen.items(), key=lambda x: -x[1]):
            lines.append(f'- "{name}" -> proposto come {entity_type} (x{count})')
        return "\n".join(lines)

    def list_known_institutions(self) -> str:
        """Elenca le istituzioni gia' confermate e salvate come reali
        (musei, gallerie, fondazioni, enti culturali)."""
        data = json.loads(INSTITUTIONS_PATH.read_text(encoding="utf-8"))
        names = data.get("institutions", [])
        if not names:
            return "Nessuna istituzione confermata finora."
        return "Istituzioni confermate:\n" + "\n".join(f"- {n}" for n in names)

    def confirm_institution(self, name: str) -> str:
        """Conferma che 'name' e' una vera istituzione (museo, galleria,
        fondazione, ente culturale) e la salva nell'elenco reale usato dalla
        pipeline per riconoscerla in futuro senza doverla indovinare.
        Usa questa funzione SOLO quando l'utente ha confermato esplicitamente,
        in questa conversazione, che il nome dato e' davvero un'istituzione --
        non decidere da solo, non dedurlo dal contesto."""
        data = json.loads(INSTITUTIONS_PATH.read_text(encoding="utf-8"))
        institutions = data.get("institutions", [])
        if name in institutions:
            return f"'{name}' era gia' nell'elenco."
        institutions.append(name)
        data["institutions"] = institutions
        INSTITUTIONS_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return (
            f"Confermato: '{name}' aggiunta alle istituzioni note. "
            "La prossima volta la pipeline la riconoscera' senza doverla indovinare."
        )

    def show_artist_data(self, artist_name: str) -> str:
        """Mostra cosa la pipeline sa DAVVERO su un nome (artista, persona,
        istituzione), separando due categorie molto diverse:
        1) le MONADI governate (atoms_built.jsonl, GMV_KNOWLEDGE_MONAD_SPEC_v1.0)
           -- fatti passati per un predicato mappato e verificato, i soli
           affidabili come risposta diretta a "chi e'"/"cosa ha fatto";
        2) i claim grezzi NON verificati nella coda di scarto -- materiale
           reale, citato da documenti reali, ma MAI da presentare come un
           fatto confermato, solo come indizio.
        USA SEMPRE questa funzione (invece di rispondere "non lo so" o
        inventare) quando l'utente chiede informazioni su una persona o
        entita' specifica "in base ai dati GMV". A oggi il backlog di
        mappatura predicati e' ancora agli inizi: la sezione 1 sara' quasi
        sempre vuota per chiunque -- dillo esplicitamente, non far sembrare
        che manchino dati proprio su questa persona. Se trovi solo dati
        grezzi, presentali chiaramente come "non ancora verificati", mai
        come fatti certi."""
        name_lower = artist_name.strip().lower()
        if not name_lower:
            return "Serve un nome non vuoto."
        lines = [f"Dati per '{artist_name}':", ""]

        governed = []
        if ATOMS_LOG_PATH.exists():
            for line in ATOMS_LOG_PATH.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if name_lower in (row.get("subject") or "").lower():
                    governed.append(row)

        if governed:
            lines.append(f"FATTI VERIFICATI E GOVERNATI ({len(governed)}):")
            for atom in governed:
                lines.append(
                    f'- {atom["subject"]} --[{atom["predicate"]}]--> {atom["object"]} '
                    f'(status={atom.get("status")})'
                )
        else:
            lines.append(
                "FATTI VERIFICATI E GOVERNATI: nessuno ancora -- il backlog di "
                "mappatura predicati e' ancora agli inizi per TUTTI i nomi nel "
                "sistema, non e' un'assenza di dati specifica su questa persona."
            )

        lines.append("")
        raw = []
        seen_refs = set()
        if REJECTION_QUEUE_PATH.exists():
            for line in REJECTION_QUEUE_PATH.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                subject_raw = row.get("subject_raw")
                if not subject_raw or name_lower not in subject_raw.lower():
                    continue
                ref = row.get("extraction_claim_ref")
                if ref in seen_refs:
                    continue
                seen_refs.add(ref)
                raw.append(row)

        if raw:
            lines.append(
                f"DATI GREZZI NON VERIFICATI da documenti reali ({len(raw)}, "
                "mostro fino a 10) -- NON sono fatti confermati, solo materiale "
                "estratto in attesa di mappatura del predicato:"
            )
            for row in raw[:10]:
                lines.append(
                    f'- "{row["subject_raw"]}" --[{row.get("raw_predicate")}]--> '
                    f'"{row.get("object_raw", "?")}"'
                )
                lines.append(f'  citazione originale: "{row.get("evidence_excerpt", "?")}"')
        else:
            lines.append("DATI GREZZI: nessun claim trovato nemmeno nella coda di scarto.")

        return "\n".join(lines)

    def show_price_history(self, artist_or_title: str) -> str:
        """Mostra le voci di listino prezzi reali estratte per un artista o
        un titolo d'opera (prezzo, anno, tecnica, dimensioni, citazione
        originale). USA questa funzione quando l'utente chiede quanto
        costava un'opera o lo storico prezzi di un artista. I dati vengono
        da listini prezzi reali gia' elaborati (price_log.jsonl) -- se non
        trovi nulla per un nome, significa che non e' ancora stato
        elaborato un listino che lo cita, non che il prezzo sia zero o
        sconosciuto in assoluto: dillo esplicitamente."""
        name_lower = artist_or_title.strip().lower()
        if not name_lower:
            return "Serve un nome o titolo non vuoto."
        if not PRICE_LOG_PATH.exists():
            return "Nessun listino prezzi ancora elaborato dalla pipeline."
        matches = []
        for line in PRICE_LOG_PATH.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            haystack = " ".join([
                row.get("artist_name", ""), row.get("title", ""), row.get("source_id", ""),
            ]).lower()
            if name_lower in haystack:
                matches.append(row)
        if not matches:
            return (
                f"Nessuna voce di listino trovata per '{artist_or_title}' -- "
                "non e' ancora stato elaborato un listino che lo cita, non "
                "significa che il prezzo sia noto e sia zero."
            )
        lines = [f"Voci di listino trovate per '{artist_or_title}' ({len(matches)}):"]
        for row in matches:
            details = [str(d) for d in (row.get("year"), row.get("medium"), row.get("dimensions")) if d]
            price_str = f'{row.get("price")} {row.get("currency", "")}'.strip()
            title = row.get("title", "?")
            suffix = f" ({', '.join(details)})" if details else ""
            lines.append(f'- "{title}" -- {price_str}{suffix}')
            lines.append(f'  citazione originale: "{row.get("evidence_excerpt", "?")}"')
        return "\n".join(lines)

    def show_contract_summary(self, artist_name: str) -> str:
        """Mostra i riepiloghi contratto reali estratti che coinvolgono un
        artista (tipo contratto, galleria, commissione, termini di
        pagamento, obblighi chiave, date se disponibili). USA questa
        funzione quando l'utente chiede cosa dice un contratto o le
        condizioni commerciali di un artista. Nota: alcuni campi (nome
        artista, date) sono spesso vuoti anche su un contratto elaborato
        con successo -- limite noto del modello sui contratti legali
        lunghi, non un errore -- per questo la ricerca controlla anche il
        percorso del file (source_id), non solo il campo artist_name."""
        name_lower = artist_name.strip().lower()
        if not name_lower:
            return "Serve un nome non vuoto."
        if not CONTRACT_LOG_PATH.exists():
            return "Nessun contratto ancora elaborato dalla pipeline."
        matches = []
        for line in CONTRACT_LOG_PATH.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            haystack = " ".join([row.get("artist_name", ""), row.get("source_id", "")]).lower()
            if name_lower in haystack:
                matches.append(row)
        if not matches:
            return f"Nessun contratto trovato per '{artist_name}'."
        lines = [f"Contratti trovati per '{artist_name}' ({len(matches)}):"]
        for row in matches:
            lines.append(f"- Tipo: {row.get('contract_type') or '(non specificato)'}")
            lines.append(f"  Galleria: {row.get('gallery_name') or '(non specificato)'}")
            if row.get("start_date") or row.get("end_date"):
                lines.append(f"  Periodo: {row.get('start_date') or '?'} - {row.get('end_date') or '?'}")
            lines.append(f"  Commissione: {row.get('commission_percentage') or '(non specificata)'}")
            lines.append(f"  Termini di pagamento: {row.get('payment_terms') or '(non specificati)'}")
            obligations = row.get("key_obligations") or []
            if obligations:
                lines.append(f"  Obblighi principali ({len(obligations)}):")
                for ob in obligations[:5]:
                    lines.append(f"    - {ob}")
                if len(obligations) > 5:
                    lines.append(f"    ... e altri {len(obligations) - 5}")
            lines.append(f"  Fonte: {row.get('source_id')}")
        return "\n".join(lines)

    def show_predicate_examples(self, raw_predicate: str) -> str:
        """Mostra fino a 3 esempi reali (soggetto, predicato, oggetto,
        citazione dal documento originale) per un predicato grezzo non
        ancora mappato, cosi' l'utente puo' verificare il significato prima
        di confermare una mappatura. USA SEMPRE questa funzione prima di
        confermare_mappatura_predicato -- non proporre mai una mappatura
        senza aver mostrato almeno un esempio reale, per non ripetere
        l'errore gia' successo in passato di mappare un predicato alla
        cieca solo dal testo. Le voci accodate prima del 2026-09-21 non
        hanno soggetto/oggetto/citazione salvati (limite noto, dillo
        all'utente se capita)."""
        if not REJECTION_QUEUE_PATH.exists():
            return "Nessuna coda di scarto trovata."
        examples = []
        seen_refs = set()
        total_matches = 0
        for line in REJECTION_QUEUE_PATH.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("raw_predicate") != raw_predicate:
                continue
            if row.get("reason_code") != "PREDICATE_TEXT_NOT_MAPPED":
                continue
            total_matches += 1
            # Voci accodate prima del 2026-09-21 non hanno questi campi
            # affatto (non un valore vuoto, la chiave manca) -- prima di
            # questo controllo venivano comunque mostrate con placeholder
            # "?" perche' .get(..., "?") nascondeva l'assenza invece di
            # saltare la riga: bug reale trovato dal vivo, un utente ha
            # visto "?" ovunque nonostante un esempio fresco con contesto
            # reale fosse gia' stato aggiunto in coda al file (le voci
            # vecchie, molto piu' numerose, venivano trovate per prime).
            if "subject_raw" not in row:
                continue
            ref = row.get("extraction_claim_ref")
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            examples.append(row)
            if len(examples) >= 3:
                break
        if not examples:
            if total_matches:
                return (
                    f"Trovate {total_matches} occorrenze di '{raw_predicate}' ma "
                    "nessuna ha contesto salvato (tutte accodate prima del "
                    "2026-09-21, senza soggetto/oggetto/citazione). Serve una "
                    "nuova estrazione che tocchi di nuovo questo predicato per "
                    "avere un esempio reale da verificare."
                )
            return f"Nessuna occorrenza trovata per '{raw_predicate}'."
        lines = [f"Esempi reali per il predicato grezzo '{raw_predicate}':"]
        for ex in examples:
            subj = ex.get("subject_raw", "?")
            obj = ex.get("object_raw", "?")
            excerpt = ex.get("evidence_excerpt", "?")
            source = ex.get("source_id", "?")
            lines.append(f'- "{subj}" --[{raw_predicate}]--> "{obj}"')
            lines.append(f'  citazione originale: "{excerpt}"')
            lines.append(f"  fonte: {source}")
        return "\n".join(lines)

    def list_known_governed_predicates(self) -> str:
        """Elenca i predicati governati gia' definiti nel registro
        (GMV_ONTOLOGY_REGISTRY_v0.1.json), con dominio e range, cosi'
        l'utente sa a quale predicato governato puo' mappare un predicato
        grezzo. USA questa funzione prima di confermare una mappatura, per
        proporre solo predicati che esistono davvero nel registro -- non
        inventarne uno nuovo qui: se nessun predicato esistente si adatta,
        dillo all'utente invece di forzare una mappatura sbagliata."""
        data = json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))
        lines = ["Predicati governati disponibili:"]
        for p in data.get("predicates", []):
            lines.append(
                f"- {p['predicate_id']} ({p['predicate_class']}): "
                f"dominio={p.get('domain')} range={p.get('range')}"
            )
        return "\n".join(lines)

    def confirm_predicate_mapping(self, raw_predicate: str, predicate_id: str, verified_against: str) -> str:
        """Conferma che il predicato grezzo 'raw_predicate' corrisponde al
        predicato governato 'predicate_id' (deve essere uno di quelli
        elencati da list_known_governed_predicates) e salva la mappatura
        nel file curato. 'verified_against' deve spiegare brevemente perche'
        la mappatura e' corretta (dominio/range coerenti, caso reale citato
        da show_predicate_examples) -- stesso standard di rigore gia' usato
        nelle voci esistenti del file.
        Usa questa funzione SOLO dopo aver mostrato all'utente un esempio
        reale con show_predicate_examples E aver ricevuto conferma esplicita
        in questa conversazione che la mappatura e' corretta -- non decidere
        da solo, non dedurlo dal contesto (stesso principio gia' applicato a
        confirm_institution)."""
        registry = json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))
        known_ids = {p["predicate_id"] for p in registry.get("predicates", [])}
        if predicate_id not in known_ids:
            return (
                f"'{predicate_id}' non esiste nel registro dei predicati "
                "governati -- controlla list_known_governed_predicates() "
                "per l'elenco reale, non inventarne uno nuovo qui."
            )
        data = json.loads(PREDICATE_MAPPING_PATH.read_text(encoding="utf-8"))
        mappings = data.get("mappings", [])
        if any(m["raw_predicate_text"] == raw_predicate for m in mappings):
            return f"'{raw_predicate}' era gia' mappato."
        mappings.append({
            "raw_predicate_text": raw_predicate,
            "predicate_id": predicate_id,
            "verified_against": verified_against,
        })
        data["mappings"] = mappings
        PREDICATE_MAPPING_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return (
            f"Confermato: '{raw_predicate}' -> {predicate_id}. "
            "La prossima estrazione lo riconoscera' senza bisogno di revisione."
        )
