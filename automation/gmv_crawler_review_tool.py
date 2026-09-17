"""
title: GMV Crawler Review
description: Legge e corregge le code di revisione del crawler GMV (predicati non riconosciuti, tipi di entita' da verificare).
"""
import json
from pathlib import Path

REPO_ROOT = Path(
    "/Users/giacomomarcovalerio/.gmv_core/.claude/worktrees/bridge-cse_01EFSz2nNresRvPh9GbfwwzK"
)
INSTITUTIONS_PATH = REPO_ROOT / "00_CONFIG" / "area35_known_institutions.json"
RUNTIME_DIR = REPO_ROOT / "01_RUNTIME" / "gmv_crawler"
REJECTION_QUEUE_PATH = RUNTIME_DIR / "rejection_queue.jsonl"
ENTITY_PROPOSAL_QUEUE_PATH = RUNTIME_DIR / "entity_proposal_queue.jsonl"


class Tools:
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
