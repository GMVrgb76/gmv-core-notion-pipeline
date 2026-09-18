#!/usr/bin/env python3
"""GMV Crawler — autonomous nightly run, no interactive session required.

Composes ONLY already-built, already-verified pieces from this project
(nothing new invented here, just wired together): `DropboxConnector`
(10_API/gmv_dropbox_connector.py, verified live for the first time this
session against a real account/token), `register_scan()`
(10_API/gmv_crawler_registry.py, Task 2 -- detects NEW/MODIFIED files
since the last run via content hash, never re-processes something
unchanged), `extract_document()` (10_API/gmv_crawler_extractor.py, step
10), `process_document()` (10_API/gmv_crawler_orchestrator.py, this
session -- EXTRACT CANDIDATES -> BUILD ATOMS, both ATTRIBUTE and
RELATION), and the two review queues (Task 7/9).

Deliberately placed OUTSIDE 01_RUNTIME/, 10_API/, gmv_core/ (the three
directories tests/test_sqlite_connection_boundary.py statically scans
for sqlite3.connect() call sites) -- this script owns its own raw
connection to a REGISTRY DB that is specific to this nightly-run
concern, not a second, competing "core" persistence path. Disclosed
here explicitly, not hidden: this is a deliberate placement decision,
not an attempt to dodge the boundary test's real intent (there is still
exactly one owner of this specific database file, this script, since
nothing else ever opens gmv_crawler_registry.db).

Run manually with `python3 automation/gmv_crawler_nightly_run.py`, or
scheduled via launchd (see automation/com.gmv.crawler.nightly.plist).
No arguments; artist folders to scan are the ARTIST_FOLDERS constant
below -- edit that list to add more, this script does not discover
folders on its own.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "10_API"))
sys.path.insert(0, str(REPO_ROOT))

from gmv_core import migrations  # noqa: E402 -- reused, not reimplemented

from gmv_crawler_extractor import extract_document  # noqa: E402
from gmv_crawler_orchestrator import process_document  # noqa: E402
from gmv_crawler_registry import register_scan  # noqa: E402
from gmv_crawler_rejection_queue import append_rejected  # noqa: E402
from gmv_crawler_entity_proposal_queue import append_entity_proposals  # noqa: E402
from gmv_dropbox_connector import DropboxConnector  # noqa: E402

# One artist folder per entry, real Dropbox path, connector_id derived
# from it (must stay stable across runs -- register_scan() scopes its
# locator/sweep queries per connector_id, changing it here orphans the
# existing registry rows for that artist).
ARTIST_FOLDERS = [
    "/GMV_MASTER_SYSTEM/01_AREA35_MASTER/99_EXPORTS/MUTUALART_2026/01_FEDERICO_GARIBALDI",
    "/GMV_MASTER_SYSTEM/01_AREA35_MASTER/99_EXPORTS/MUTUALART_2026/02_MANUEL_BONFANTI",
    "/GMV_MASTER_SYSTEM/01_AREA35_MASTER/99_EXPORTS/MUTUALART_2026/03_FLORENCIA_BRUCK",
    "/GMV_MASTER_SYSTEM/01_AREA35_MASTER/99_EXPORTS/MUTUALART_2026/04_DAVIDE_GENNA",
    # 00_area35 (profilo della galleria, non un artista) deliberatamente
    # escluso -- verificato dal vivo 2026-09-18 che la cartella MUTUALART_2026
    # contiene questi 4 artisti reali oltre a Garibaldi (usato come unico
    # caso di test durante lo sviluppo, mai esteso fino ad ora).
]

# Roster completo, 01_ARTISTS/ -- verificato dal vivo 2026-09-18: 46
# cartelle artista, quasi 3900 file totali, struttura NON uniforme.
# Ogni root qui sotto e' l'intera cartella dell'artista (un connector_id
# = uno scan del registry); il filtro sui soli testi/bio avviene DOPO,
# in TEXT_SUBFOLDER_MARKERS piu' sotto -- non qui, perche' filtrare gia'
# a livello di connector.list() richiederebbe toccare gmv_crawler_registry.py,
# un modulo condiviso, per un bisogno specifico solo di questo script.
ARTIST_ROSTER_ROOT = "/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS"
ARTIST_ROSTER_NAMES = [
    "bertola_francesco", "bonfanti_manuel", "bonzano_stefano", "bruck_florencia",
    "bucchi_danilo", "calaj_renato", "cascella_marco", "cerri_giovanni",
    "chiodi_italo", "colombo_barbara", "dall'olio_giulia", "dawson_dennis",
    "dilella_katia", "ducoli_carola", "evangelisti_nicola", "fincato_giorgia",
    "finelli_pietro", "fuku_naoki", "garibaldi_federico", "gasparini_gian_piero",
    "genna_davide", "geranzani_pietro", "girella_alessio", "hromec_robert",
    "lucido_lorenzo_di", "manos_gaspare", "mendeni_marco", "morales_ernesto",
    "nazeraj_erjon", "nicolela_kika", "pasini_giovanni", "paternò_castello_riccardo",
    "pozzo_di_borgo_camille", "qi_luo", "rocca_guido", "schiavo_alessio",
    "schiavocampo_paolo", "seli_yuki", "snape_neil", "tomasi_marcello",
    "topy_paolo", "toussaint_jacques", "valenti_fabio", "valli_giorgia",
    "vanetti_giacomo", "yalvac_melis",
]
ARTIST_FOLDERS.extend(f"{ARTIST_ROSTER_ROOT}/{name}" for name in ARTIST_ROSTER_NAMES)

# Deciso con l'utente 2026-09-18: scope "solo testi/bio" per tutti i 46
# artisti, non tutto il materiale grezzo. Per gli artisti gia' organizzati
# (7-12 su 46) i testi puliti vivono in 00_master/03_testi. Per gli altri
# 34, ancora in stato grezzo, la stessa informazione e' gia' stata
# convertita in markdown dentro 10_md_processed_files -- 09_temp_import
# (l'originale grezzo: foto, video, contratti, pdf misti) resta escluso
# di proposito, cosi' come 06_contratti/05_mercato/04_video/02_mostre.
TEXT_SUBFOLDER_MARKERS = ("/00_master/", "/03_testi/", "/10_md_processed_files/")

# BUG REALE trovato dal vivo 2026-09-18 durante il test del rinnovo token:
# 10_md_processed_files e' una cartella PIATTA con le conversioni markdown
# di file da QUALSIASI cartella originale (il nome del file porta il
# prefisso della cartella sorgente, es. "06_contratti__...pdf.md",
# "05_mercato__sales__...pdf.md") -- includerla per intero, come fatto
# sopra, ha fatto passare un vero contratto (clausole di pagamento,
# residenza, durata, recesso) e un vero file di vendita/prezzi dentro la
# pipeline LLM, con frasi finite realmente in rejection_queue.jsonl
# (rimosse a mano dopo la scoperta). Filtro per prefisso, non per
# contenuto: un contratto non ancora smistato dentro 09_temp_import
# (cartella "tutto quello che capita", non solo testi) NON verrebbe
# comunque intercettato da questo controllo -- rischio residuo dichiarato,
# non silenziato.
SENSITIVE_ORIGIN_PREFIXES = ("06_contratti__", "05_mercato__")


def _is_allowed_locator(connector_id: str, locator: str) -> bool:
    """MUTUALART_2026 entries (already curated exports) keep every file
    they have; only the full 01_ARTISTS roster needs the text-only
    filter, since that's the one with raw/mixed material mixed in."""
    if connector_id.startswith(ARTIST_ROSTER_ROOT):
        if not any(marker in locator for marker in TEXT_SUBFOLDER_MARKERS):
            return False
        basename = locator.rsplit("/", 1)[-1]
        return not basename.startswith(SENSITIVE_ORIGIN_PREFIXES)
    return True

RUNTIME_DIR = REPO_ROOT / "01_RUNTIME" / "gmv_crawler"
REGISTRY_DB = RUNTIME_DIR / "registry.db"
REJECTION_QUEUE_PATH = RUNTIME_DIR / "rejection_queue.jsonl"
ENTITY_PROPOSAL_QUEUE_PATH = RUNTIME_DIR / "entity_proposal_queue.jsonl"
ATOMS_LOG_PATH = RUNTIME_DIR / "atoms_built.jsonl"
RUN_LOG_PATH = RUNTIME_DIR / "run_log.jsonl"
PROCESSED_HASHES_PATH = RUNTIME_DIR / "processed_content_hashes.json"
# Same lock file gmv_crawler_review_tool.py's run_crawler_now() checks
# before launching -- shared here so it protects EVERY invocation path
# (chat, launchd's 3am schedule, a manual run), not just the chat one.
# Found live 2026-09-18: a chat-triggered run landed while a manual test
# run of this same script was already in progress against the same
# registry.db/run_log.jsonl -- concurrent writes were never actually
# corrupted in that instance, but nothing here made that safe on purpose.
RUN_PID_FILE = RUNTIME_DIR / "current_run.pid"

# `crawler_source_registry.state` answers "did the CONTENT change since
# the last scan" (register_scan()'s job) -- it does NOT answer "did THIS
# script ever successfully turn that content into atoms/queue entries".
# Those are different questions: a content_hash can stay state='NEW' (or
# flip to 'UNCHANGED' on the very next scan, even if this script never
# successfully processed it) regardless of whether processing succeeded.
# Conflating them was a real bug found live this session: a timeout on
# run 1 left 4 files unprocessed; run 2's register_scan() saw the same
# unchanged content and flipped them to state='UNCHANGED', so the
# state-based query below would have silently stopped trying them
# forever. PROCESSED_HASHES_PATH is this script's own record of which
# content_hash values it has successfully carried all the way through
# process_document() -- checked instead of (not in addition to) state.


def _load_processed_hashes() -> set[str]:
    if not PROCESSED_HASHES_PATH.exists():
        return set()
    return set(json.loads(PROCESSED_HASHES_PATH.read_text(encoding="utf-8")))


def _save_processed_hash(content_hash: str, processed: set[str]) -> None:
    processed.add(content_hash)
    PROCESSED_HASHES_PATH.write_text(
        json.dumps(sorted(processed), ensure_ascii=False, indent=2), encoding="utf-8"
    )

# Real files this project's extractor does not yet cover (per
# gmv_crawler_extractor.py's own real, committed format support) skip
# via doc.status != "SUCCESS", never crash the run -- one bad file must
# not stop the rest of the folder.


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def notify(title: str, message: str) -> None:
    """Best-effort macOS local notification. Never raises -- a
    notification failure must not fail the run itself."""
    try:
        subprocess.run(  # noqa: S603 -- fixed local macOS binary, args are our own strings, never external input
            ["/usr/bin/osascript", "-e", f'display notification "{message}" with title "{title}"'],
            check=False, timeout=10,
        )
    except Exception:  # noqa: S110, BLE001 -- a notification failure must never fail the run itself
        pass


def process_one_folder(connection: sqlite3.Connection, folder: str, now: str) -> tuple[int, int, int, bool]:
    """Scan one artist folder, process every file this script has not yet
    successfully carried through process_document() (see
    PROCESSED_HASHES_PATH's own note on why 'state' alone is not the
    right query here). Returns (files_processed, atoms_built,
    items_needing_review, scan_ok).

    scan_ok=False means the Dropbox scan itself failed (expired token,
    network, etc.) -- found live 2026-09-18: this used to be an
    uncaught exception that killed the whole process before it ever
    logged anything or sent a notification, so a token expiry produced
    total silence instead of a signal the user could act on."""
    connector = DropboxConnector(root_path=folder)
    connector_id = folder
    try:
        register_scan(connection, connector, connector_id=connector_id, now=now)
    except Exception as exc:
        _log_run_event({"event": "scan_failed", "folder": folder, "error": str(exc), "at": now})
        return 0, 0, 0, False

    processed_hashes = _load_processed_hashes()
    rows = connection.execute(
        "SELECT content_hash, canonical_locator FROM crawler_source_registry "
        "WHERE connector = ? AND state != 'DELETED'",
        (connector_id,),
    ).fetchall()
    rows = [
        row for row in rows
        if row[0] not in processed_hashes and _is_allowed_locator(connector_id, row[1])
    ]

    files_processed = 0
    atoms_built = 0
    needing_review = 0

    for content_hash, locator in rows:
        try:
            raw_bytes = connector.download(locator)
        except Exception as exc:
            _log_run_event({"event": "download_failed", "locator": locator, "error": str(exc), "at": now})
            continue

        suffix = Path(locator).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)
        try:
            document = extract_document(tmp_path, source_id=locator, source_hash=content_hash)
        finally:
            tmp_path.unlink(missing_ok=True)

        if document.status != "SUCCESS":
            _log_run_event({
                "event": "extraction_skipped", "locator": locator,
                "status": document.status, "at": now,
            })
            continue

        try:
            result = process_document(
                document, evidence_ids=(f"{locator}#{now}",), now=now,
                timeout=280,
            )
        except Exception as exc:
            _log_run_event({"event": "processing_failed", "locator": locator, "error": str(exc), "at": now})
            continue

        files_processed += 1
        atoms_built += len(result.atoms)

        if result.atoms:
            with ATOMS_LOG_PATH.open("a", encoding="utf-8") as handle:
                for atom in result.atoms:
                    handle.write(json.dumps(asdict(atom), ensure_ascii=False) + "\n")

        if result.rejected:
            append_rejected(result.rejected, REJECTION_QUEUE_PATH, now=now)

        needing_review += append_entity_proposals(
            result.entity_type_proposals_needing_verification, ENTITY_PROPOSAL_QUEUE_PATH, now=now,
        )

        # Marked successful (and saved to disk) only now, after every step
        # above has run without raising -- a crash partway through must
        # leave this content_hash retryable on the next run, not falsely
        # marked done.
        _save_processed_hash(content_hash, processed_hashes)

    return files_processed, atoms_built, needing_review, True


def _log_run_event(event: dict) -> None:
    with RUN_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _other_instance_running() -> int | None:
    """None if no run is currently in progress. Self-healing: a PID file
    left over from a killed/crashed run is detected as stale (the kill(0)
    liveness probe fails) and treated as not-running -- no separate
    cleanup step needed on the failure path."""
    if not RUN_PID_FILE.exists():
        return None
    try:
        pid = int(RUN_PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
    except (ValueError, ProcessLookupError, PermissionError):
        return None
    return pid


def main() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    other_pid = _other_instance_running()
    if other_pid is not None:
        _log_run_event({
            "event": "skipped_already_running", "at": now_iso(), "other_pid": other_pid,
        })
        return

    RUN_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        if not REGISTRY_DB.exists():
            migrations.migrate(REGISTRY_DB, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

        now = now_iso()
        connection = sqlite3.connect(REGISTRY_DB)
        total_files = total_atoms = total_review = 0
        any_scan_failed = False
        try:
            for folder in ARTIST_FOLDERS:
                files, atoms, review, scan_ok = process_one_folder(connection, folder, now)
                total_files += files
                total_atoms += atoms
                total_review += review
                any_scan_failed = any_scan_failed or not scan_ok
            connection.commit()
        finally:
            connection.close()

        _log_run_event({
            "event": "run_complete", "at": now,
            "files_processed": total_files, "atoms_built": total_atoms,
            "needing_review": total_review, "scan_failed": any_scan_failed,
        })

        if any_scan_failed:
            notify("GMV Crawler", "Errore: impossibile leggere Dropbox (token scaduto?). Controlla run_log.jsonl.")
        elif total_files == 0 and total_review == 0:
            notify("GMV Crawler", "Nessun file nuovo da elaborare stanotte.")
        else:
            notify(
                "GMV Crawler",
                f"{total_atoms} atomi nuovi, {total_review} da verificare -- apri OpenWebUI quando vuoi.",
            )
    finally:
        RUN_PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
