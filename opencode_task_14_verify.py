"""One-off live check for opencode_task_14.md. NOT part of the pipeline, NOT
committed. Read-only against every real file; the two write methods are
exercised against a byte-identical TEMP COPY of the real registry, never the
real one, because an unattended write of gmv_entity_registry.json is exactly
what the registry's own note and Task 13's test A7 forbid.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "automation"))
import gmv_crawler_review_tool as T  # noqa: E402

tools = T.Tools()
bar = "=" * 72

print(bar)
print("A. list_known_governed_entity_types()  [real import from 10_API]")
print(bar)
print(tools.list_known_governed_entity_types())

print()
print(bar)
print("B. list_known_entities()  [REAL 00_CONFIG/gmv_entity_registry.json]")
print(bar)
print(tools.list_known_entities())
print(f"[path letto: {T.ENTITY_REGISTRY_PATH}]")

print()
print(bar)
print("C. list_pending_entity_identities()  [REAL runtime queue, as it is]")
print(bar)
print(tools.list_pending_entity_identities())
print(f"[path: {T.ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH}, esiste={T.ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH.exists()}]")

print()
print(bar)
print("D. list_pending_entity_identities() su una coda SINTETICA in /tmp")
print("   (il file reale non esiste: questo controlla solo il rendering,")
print("    non e' una coda prodotta dal crawler)")
print(bar)
sys.path.insert(0, str(T.API_DIR))
from gmv_crawler_entity_identity_proposal_queue import (  # noqa: E402
    append_entity_identity_proposals,
)
from gmv_crawler_entity_resolver import propose_entity_identity  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    synthetic = Path(tmp) / "entity_identity_proposal_queue.jsonl"
    registry = json.loads(T.ENTITY_REGISTRY_PATH.read_text(encoding="utf-8"))
    proposals = [
        p for p in (
            propose_entity_identity(
                name, registry,
                source_id=src, evidence_excerpt=excerpt, suggested_entity_type=etype,
            )
            for name, src, excerpt, etype in (
                ("Danilo Bucchi", "/Artisti/Bucchi/bio.txt", "nato a Fabriano nel 1975", "ARTIST"),
                ("Fabriano", "/Mostre/2019/curatela.txt", "la citta' di Fabriano", "PLACE"),
                ("", "/Mostre/2019/bozza.txt", "(nome mancante)", ""),
            )
        ) if p is not None
    ]
    print(f"[proposte sintetiche accodate: {len(proposals)} "
          f"(Federico Garibaldi escluso: gia' risolve, nessuna proposta)]")
    append_entity_identity_proposals(proposals, synthetic, now="2026-09-26T00:00:00Z")
    real_path, T.ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH = (
        T.ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH, synthetic,
    )
    try:
        print(tools.list_pending_entity_identities())
    finally:
        T.ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH = real_path

    print()
    print(bar)
    print("E. confirm_new_entity / confirm_entity_alias su COPIA TEMP della")
    print("   registry reale (il file reale non viene mai toccato)")
    print(bar)
    copy_path = Path(tmp) / "gmv_entity_registry_copy.json"
    copy_path.write_bytes(T.ENTITY_REGISTRY_PATH.read_bytes())
    before = T.ENTITY_REGISTRY_PATH.read_bytes()
    real_registry_path, T.ENTITY_REGISTRY_PATH = T.ENTITY_REGISTRY_PATH, copy_path
    try:
        print("E1 nuovo nome      :", tools.confirm_new_entity("Danilo Bucchi", "ARTIST"))
        print("E2 alias           :", tools.confirm_entity_alias("GMV-000002", "D. Bucchi"))
        print("E3 alias duplicato :", tools.confirm_entity_alias("GMV-000002", "D. Bucchi"))
        print("E4 nome duplicato  :", tools.confirm_new_entity("federico garibaldi", "ARTIST"))
        print("E5 tipo non valido :", tools.confirm_new_entity("Nome Nuovo", "SCULTORE"))
        print("E6 nome vuoto      :", tools.confirm_new_entity("   ", "ARTIST"))
        print("E7 id inesistente  :", tools.confirm_entity_alias("GMV-00001", "D. Gar"))
        print("E8 alias vuoto     :", tools.confirm_entity_alias("GMV-000001", "  "))
        print()
        print("E9 la copia risultante:")
        for entry in json.loads(copy_path.read_text(encoding="utf-8"))["entities"]:
            print("   ", json.dumps(entry, ensure_ascii=False))
    finally:
        T.ENTITY_REGISTRY_PATH = real_registry_path
    if T.ENTITY_REGISTRY_PATH.read_bytes() != before:
        raise SystemExit("FALLITO: la registry REALE e' stata modificata")
    print()
    print("[registry REALE byte-identica a prima: confermato]")

print()
print(bar)
print("F. list_known_entities() di nuovo, con la copia realepostata in atto")
print(bar)
print(tools.list_known_entities())
