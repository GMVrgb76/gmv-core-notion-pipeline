from pathlib import Path
from datetime import datetime
import json

ROOT = Path.home() / "Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM"

APP = ROOT / "99_SYSTEM/10_APPRENTICE"
REPORTS = APP / "reports"
STATE = APP / "state"
JOBS = APP / "jobs"
EXPERIENCE = APP / "EXPERIENCE_LOG.md"
STATE_FILE = STATE / "APPRENTICE_STATE.json"

for p in [REPORTS, STATE, JOBS]:
    p.mkdir(parents=True, exist_ok=True)

if not EXPERIENCE.exists():
    EXPERIENCE.write_text(
        "# GMV APPRENTICE - EXPERIENCE LOG\n\n"
        "Questo file registra l'esperienza progressiva del GMV Apprentice.\n\n"
        "## Log\n\n",
        encoding="utf-8"
    )

charter = ROOT / "99_SYSTEM/00_CONSTITUTION/GMV_APPRENTICE_CHARTER.md"
cognitive = ROOT / "99_SYSTEM/KNOWLEDGE/GMV_COGNITIVE_LOOP.md"
knowledge_model = ROOT / "99_SYSTEM/KNOWLEDGE/GMV_KNOWLEDGE_MODEL.md"

now = datetime.now()
stamp = now.strftime("%Y_%m_%d_%H%M")

previous_state = {}
if STATE_FILE.exists():
    try:
        previous_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        previous_state = {}

experience_text = EXPERIENCE.read_text(encoding="utf-8", errors="ignore")

capabilities = {
    "document_discovery": "ACTIVE",
    "ocr": "AVAILABLE",
    "document_classification": "EARLY",
    "entity_extraction": "EARLY",
    "state_update": "PROTOTYPE",
    "task_generation": "NOT_READY",
    "publishing": "NOT_READY",
    "dossier_engine": "V1_ACTIVE",
    "recursive_experience": "V1_ACTIVE",
}

targets = {
    "Immobili": ROOT / "02_IMMOBILI",
    "Area35 Archive": ROOT / "01_AREA35_MASTER",
    "Deals": ROOT / "09_DEALS",
    "Famiglia": ROOT / "03_FAMIGLIA",
}

scan = {}
for name, path in targets.items():
    if path.exists():
        pdfs = list(path.rglob("*.pdf"))
        docs = list(path.rglob("*.docx")) + list(path.rglob("*.doc"))
        md = list(path.rglob("*.md"))
        scan[name] = {
            "exists": True,
            "pdf": len(pdfs),
            "doc": len(docs),
            "md": len(md),
            "total_known_docs": len(pdfs) + len(docs) + len(md),
        }
    else:
        scan[name] = {"exists": False, "total_known_docs": 0}

previous_scan = previous_state.get("scan", {})
changes = []

for name, data in scan.items():
    old = previous_scan.get(name, {}).get("total_known_docs")
    new = data.get("total_known_docs", 0)
    if old is None:
        changes.append(f"{name}: baseline iniziale {new} documenti.")
    elif new != old:
        sign = "+" if new > old else ""
        changes.append(f"{name}: {old} → {new} documenti ({sign}{new-old}).")

if not changes:
    changes.append("Nessuna variazione documentale rilevata rispetto al ciclo precedente.")

# Decisione V1.1: non più job fisso cieco.
# Se ci sono variazioni, priorità al dominio cambiato.
# Se non ci sono variazioni, priorità al collo di bottiglia dichiarato.
changed_domains = [
    c.split(":")[0] for c in changes
    if "→" in c
]

if changed_domains:
    domain = changed_domains[0]
    reason = "Dominio modificato rispetto al ciclo precedente."
    action = "Verificare i nuovi documenti e preparare aggiornamento di State/Timeline/Dossier."
else:
    domain = "Immobili"
    reason = "Nessuna variazione rilevata; mantenuto dominio di addestramento prioritario."
    action = "Stabilizzare Document Classification e preparare Entity/State pipeline."

selected_job = {
    "domain": domain,
    "reason": reason,
    "action": action,
    "status": "PLANNED"
}

state = {
    "runtime": "GMV Apprentice Runtime V1.1",
    "last_run": now.isoformat(timespec="seconds"),
    "charter_loaded": charter.exists(),
    "cognitive_loop_loaded": cognitive.exists(),
    "knowledge_model_loaded": knowledge_model.exists(),
    "capabilities": capabilities,
    "scan": scan,
    "changes_since_previous_run": changes,
    "selected_job": selected_job,
    "experience_log_chars": len(experience_text),
}

STATE_FILE.write_text(
    json.dumps(state, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

report = REPORTS / f"APPRENTICE_REPORT_{stamp}.md"
report.write_text(f"""# GMV APPRENTICE REPORT

Data: {now.strftime("%Y-%m-%d %H:%M:%S")}

## Runtime

GMV Apprentice Runtime V1.1

## Constitution

- Apprentice Charter: {"OK" if charter.exists() else "MISSING"}
- Cognitive Loop: {"OK" if cognitive.exists() else "MISSING"}
- Knowledge Model: {"OK" if knowledge_model.exists() else "MISSING"}

## Experience

- EXPERIENCE_LOG letto: SÌ
- Caratteri esperienza letti: {len(experience_text)}
- Stato precedente letto: {"SÌ" if previous_state else "NO"}

## Capability State

""" + "\n".join(f"- {k}: {v}" for k, v in capabilities.items()) + f"""

## Domain Scan

""" + "\n".join(
    f"- {name}: {data.get('total_known_docs', 0)} documenti noti"
    for name, data in scan.items()
) + f"""

## Cambiamenti rispetto al ciclo precedente

""" + "\n".join(f"- {c}" for c in changes) + f"""

## Selected Job

Dominio: {selected_job["domain"]}

Motivo:
{selected_job["reason"]}

Azione:
{selected_job["action"]}

## Limite individuato

L'Apprentice ora legge esperienza e stato precedente, ma non modifica ancora documenti originali.
La prossima capacità necessaria resta la trasformazione stabile di documenti in Entity, Timeline, State e Dossier.

## Stato

Nessun documento originale modificato.
Nessun commit effettuato.
Runtime ricorsivo V1.1 eseguito.
""", encoding="utf-8")

with EXPERIENCE.open("a", encoding="utf-8") as f:
    f.write(f"## {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("- Runtime eseguito: GMV Apprentice Runtime V1.1\n")
    f.write(f"- Stato precedente letto: {'SÌ' if previous_state else 'NO'}\n")
    f.write(f"- Cambiamenti rilevati: {len(changes)}\n")
    for c in changes:
        f.write(f"  - {c}\n")
    f.write(f"- Job selezionato: {selected_job['domain']} — {selected_job['action']}\n\n")

print("GMV APPRENTICE RUNTIME V1.1 OK")
print(report)
print(EXPERIENCE)
