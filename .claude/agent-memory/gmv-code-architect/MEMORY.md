# Memoria — gmv-code-architect

Indice di conoscenza architetturale stabile su GMV Core. Non è caricata
automaticamente: l'agente la legge esplicitamente a inizio consultazione (non
esiste un meccanismo nativo di memoria per-subagent in Claude Code 2.1.221 —
vedi `.claude/agents/gmv-code-architect.md`, sezione Memoria).

Voci verificate sul repository al 2026-08-29:

- Fase architetturale attiva: **Core Integrity** (`GMV_ARCHITECTURE.md`).
  Reasoning, Decision e workflow autonomo sono target dichiarati, non
  perimetro implementato — non raccomandare soluzioni che li presuppongono
  già esistenti.
- Documenti canonici e regola anti-alias: `00_CONFIG/GMV_GOVERNANCE_INDEX.md`.
- "GBrain" e "Shadow": nessun riscontro nel codice o nella storia Git di
  nessun branch alla data della verifica. Se citati come componenti
  esistenti, riverificare prima di assumerli.
- Le decisioni ADR e i documenti `*_FREEZE.md`/`*_SUSPENSION.md` sotto
  `00_CONFIG/` sono i vincoli bloccanti da controllare per prime; l'elenco
  completo va riletto ad ogni consultazione, non memorizzato staticamente qui
  (cambia nel tempo).

## Architettura decisa per la pipeline artista→Notion (fonte: pagina Notion "Notion Page Extraction Candidate", letta 2026-08-29, ultimo aggiornamento pagina 28 agosto 2026)

Questa è una **decisione architetturale già presa**, non una proposta — verificare lo stato di implementazione reale (probabilmente parziale) prima di raccomandare qualcosa in quest'area, ma non rimetterla in discussione senza motivo.

- Principio guida: "Python determina cosa esiste. Il local LLM interpreta ciò che è già delimitato. Il Web fornisce evidenza esterna. Il cloud LLM risolve soltanto l'ambiguità residua. Notion riceve soltanto ciò che ha superato il gate." Obiettivo operativo: ≥80% del lavoro sul Mac mini locale; il cloud LLM è remediator semantico su eccezioni, non motore della pipeline.
- Sequenza canonica: `Dropbox → deterministic extractor → local LLM → Web retrieval → local verification → cloud escalation solo se necessario → MD validato → Notion → canonical information export → [monade, non ancora progettata]`.
- Componenti proposti (catena di script Python, orchestratore resta Python, nessun framework agentico aggiuntivo): `gmv_artist_extract.py → gmv_artist_summarize_local.py → gmv_artist_claims.py → gmv_artist_web_retrieve.py → gmv_artist_verify_local.py → gmv_artist_escalation_plan.py → [cloud solo se richiesto] → gmv_artist_notion_payload.py`.
- **Questo conferma che la ricerca-artista e la web-retrieval sono funzioni applicative di GMV Core (script Python + LLM locale orchestrati), non compiti per un Claude Code subagent** — coerente con la rimozione di `gmv-artist-researcher`/`gmv-evidence-reviewer` decisa il 2026-08-29 (vedi memoria del progetto). Se in futuro viene proposto un subagent che rifà questa ricerca, è una duplicazione da segnalare.
- Distinzione epistemica da riusare: `ARCHIVE KNOWLEDGE` (da SUM/Area35) / `EXTERNAL KNOWLEDGE` (da Web) / `CANONICAL KNOWLEDGE` (ammessa dopo verifica e gate). Il Web verifica identità/bio/carriera/date; **non può determinare da solo la relazione storica artista↔Area35**, che resta ancorata primariamente a SUM.
- Vocabolario di stato per singola informazione: `SUPPORTED_BY_ARCHIVE / INFERRED / MISSING / CONFLICTING`; verifica locale: `VERIFIED / PARTIALLY_VERIFIED / NOT_VERIFIED / CONFLICT`; gate finale: `READY_FOR_NOTION / REVIEW_REQUIRED / INSUFFICIENT_EVIDENCE`, con uno stato intermedio `LOCAL_EVIDENCE_INCOMPLETE → WEB_RETRIEVAL_REQUIRED` prima di dichiarare `INSUFFICIENT_EVIDENCE`.
- **Riuso prima di codice nuovo** (principio esplicito nel documento): verificare se `gmv folder-report` (comando CLI deterministico già esistente) copre già lo stadio 1 prima di creare `gmv_artist_extract.py`; riusare la tracciabilità del Run Ledger già adottato da Area35 QA invece di crearne una separata; la precedente "GMV Import Skill Dropbox→Notion" aveva già un Handoff che segnalava come inefficiente l'alternanza continua Dropbox↔Notion, proponendo produzione batch dei candidati + entity resolution concentrata — riusare quella diagnosi.
- Configurazione LLM locale validata (Federico Garibaldi, caso UPDATE, PASS end-to-end): `gemma4:12b`, `num_ctx=8192`, `num_predict=4096`, `think=false`, esecuzione **sequenziale** (il parallelismo fra modelli sul Mac mini M4 24GB introduce contesa hardware e altera tempi/success rate — non parallelizzare le inferenze), `max_chunk_chars=8000`, `min_adaptive_chunk_chars=500` (è un fallback di resilienza, non un ottimo semantico dichiarato: non modificarlo senza motivo esplicito). `qwen3:8b` tronca su chunk >1200 caratteri anche a `num_predict=4096`; `qwen2.5-coder:7b` scartato per instabilità semantica su input identici.
- **Nuovo requisito architetturale emerso (28 agosto): GMV Human Interface.** La pipeline oggi espone solo stadi CLI separati (`analyze → resolve → candidate`, ognuno con parametri tecnici) — dichiarato esplicitamente "non un'interfaccia operativa adeguata per l'utente finale". Confine richiesto: `USER → GMV Human Interface → GMV Orchestrator → extraction/analyze/resolve/candidate → local LLM → Run Ledger + Evidence Bundle + NOTION_PATCH.json`. La Human Interface parla con GMV Core, mai direttamente con Ollama. Prima iterazione proposta: interfaccia web locale sul Mac mini, senza nuovo framework agentico. Rilevante per la responsabilità #9 (GUI come presentation layer, non logica di dominio).
- **Audit GitHub richiesto dal documento stesso ma non completato quando scritto** ("il tentativo di verificare direttamente lo stato GitHub corrente non è stato completato per indisponibilità dell'accesso remoto"): risolto in parte nella conversazione del 2026-08-29 che ha prodotto questa memoria — `origin/main` = `cf2f977` è **solo** l'Area35 QA Engine (validator/remediator/ledger), non contiene `10_API/gmv_evidence_pipeline.py` né il resto dell'architettura GMV Core; quel codice vive solo su `origin/codex/evidence-2026-08-27` (storia separata, nessun antenato comune con `main`). Chi implementa questa pipeline deve sapere da quale branch/checkout partire.

Nessuna lezione procedurale aggiuntiva accumulata ancora da consultazioni reali.
