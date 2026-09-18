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
RUNTIME_DIR = REPO_ROOT / "01_RUNTIME" / "gmv_crawler"
REJECTION_QUEUE_PATH = RUNTIME_DIR / "rejection_queue.jsonl"
ENTITY_PROPOSAL_QUEUE_PATH = RUNTIME_DIR / "entity_proposal_queue.jsonl"
RUN_LOG_PATH = RUNTIME_DIR / "run_log.jsonl"
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
    from a crashed/killed run is detected as stale (os.kill probe fails)
    and treated as not-running, no separate cleanup step needed."""
    if not RUN_PID_FILE.exists():
        return None
    try:
        pid = int(RUN_PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
    except (ValueError, ProcessLookupError, PermissionError):
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
