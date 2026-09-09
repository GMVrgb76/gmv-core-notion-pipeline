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

## Notion candidate/publish pipeline: single vs multi-entity bundle (verificato 2026-09-09)

- `10_API/gmv_notion_candidate.py` (single-entity) e `10_API/gmv_notion_multi_candidate.py`
  (multi-entity fan-out) condividono già primitive da `gmv_evidence_pipeline.py`
  (`compare_entity`, `gate`, `norm`, `required_fields`, `read_json`/`write_json`,
  `EvidenceError`) ma emettono bundle strutturalmente incompatibili:
  single usa `NOTION_PATCH.json` con `operation` (CREATE/UPDATE), `operations`
  ADD/UPDATE/CONFLICT su **nomi di property Notion reali**, `keep`, `body_gate`;
  multi usa `PATCH.json` con `operations` RELATE/SET_FIELD su chiavi interne mai
  risolte, nessun `operation`, nessun `keep`/`body_gate`/`provenance`.
  `10_API/gmv_notion_publish.py::load_bundle` rifiuta esplicitamente `PATCH.json`
  (ValueError con messaggio "not supported ... yet").
- **Due config artifacts distinti, non intercambiabili**: `config.json`
  (`entita.<tipo>.campi`/`relazioni`, ognuno con `notion` = nome property reale
  + `obbligatorio`, più `notion_database_id`) è consumato da
  `build_incremental_patch` (candidate.py) per risolvere predicate→property
  Notion reale. `00_CONFIG/notion_page_templates.json`
  (`entita.<tipo>.struttura_pagina`/`field_hints`/`relation_hints`,
  `discovery_hints`, `generation_priority`) è consumato SOLO da multi_candidate
  per classificare/instradare claim (relation vs field vs body) e scoprire
  entità. `gmv_notion_multi_candidate.py::build_entity_patch` riceve GIÀ
  `config` come parametro ma lo usa solo per `required_fields()` — non lo usa
  mai per risolvere un `SET_FIELD`/`RELATE` a un nome di property Notion reale.
  Questo è il meccanismo concreto dietro il gap di vocabolario, non solo una
  differenza di naming.
- **Le relazioni Notion non sono MAI scritte da nessuno dei due percorsi.**
  `build_incremental_patch` (single) marca OGNI relation claim come CONFLICT
  incondizionatamente ("RELATION_TARGET_ID_NOT_RESOLVED"), anche quando in
  teoria potrebbe risolvere il valore. `notion_publish.py::NOTION_TYPE_BUILDERS`
  non ha un builder "relation" (commento esplicito: "Deliberately no relation
  entry ... belt-and-suspenders, not an accident"). `gmv_notion_multi_candidate.py`
  è l'UNICO punto del codice che tenta una vera risoluzione di relation target
  (`_relation_target`, contro `rows.get(target_type)`), ma anche lì l'esito
  resolved=True non porta mai a una vera scrittura — nessun writer esiste.
  Conseguenza pratica: un target di relazione "pending" non è un rischio di
  pubblicazione prematura oggi, né lo sarebbe con un'integrazione minima che si
  limiti a riusare `plan_requests`/`apply_patch` esistenti — perché nessun
  meccanismo scrive mai una relation. Un relation-writer è lavoro nuovo,
  separato, da validare su dati reali prima di costruirlo (rischio reale:
  scrivere su una property `relation` Notion sostituisce l'intera lista, quindi
  serve merge con `keep.relations` esistente, mai già implementato/testato —
  `check_staleness` oggi controlla solo `keep.properties`, mai `keep.relations`).
- Convergenza raccomandata: NON insegnare a `plan_requests`/`apply_patch` un
  secondo vocabolario (RELATE/SET_FIELD) — invece far emettere a
  `build_entity_patch` la STESSA forma già capita da `gmv_notion_publish.py`
  (operation CREATE/UPDATE via `existing is None`, ADD/UPDATE/CONFLICT su
  property reali risolte via `config.json`), scrivendo via
  `write_evidence_bundle` (già esistente in `gmv_evidence_pipeline.py`) invece
  del bespoke `write_entity_bundle`. Così ogni entità scoperta diventa un
  bundle single-entity normale, pubblicabile con `gmv evidence publish` senza
  toccare `gmv_notion_publish.py`. Attenzione: `compare_entity` può restituire
  `status="AMBIGUOUS", existing=None` — un mapping naive `existing is None →
  CREATE` tratterebbe erroneamente un'entità ambigua come CREATE (rischio
  duplicazione pagina); va gestita esplicitamente come caso a parte (nessun
  `operation` deciso, gate REVIEW_REQUIRED, già garantito da `gate()`).

## Pattern: innesto di un'interfaccia non-terminale su una CLI di conferma esistente (verificato 2026-09-09)

- `10_API/gmv_notion_publish.py::publish_bundle(..., input_fn=input)` è già
  progettata per essere chiamata da un'interfaccia non-terminale senza
  duplicare nessuna logica di sicurezza: basta chiamarla due volte con
  `input_fn` diverso, catturando stdout con
  `contextlib.redirect_stdout(io.StringIO())`.
  - Anteprima (safe, nessuna scrittura): `input_fn=lambda _: "n"` — esegue
    comunque TUTTI i controlli reali (già-pubblicato, gate, doppione,
    staleness) e stampa `render_review_screen`, ma `confirm()` risulta
    False quindi `apply_patch` non viene mai chiamato.
  - Approvazione reale: `input_fn=lambda _: "y"`, stessa chiamata.
  - Vantaggio: l'anteprima ri-verifica sempre tutto "a caldo" (incluse
    letture live Notion per staleness/doppione) ad ogni caricamento,
    chiudendo la finestra tra "l'umano ha visto la pagina" e "ha
    approvato". Non è spreco da ottimizzare, è correttezza.
  - Non richiamare `render_review_screen`/`plan_requests`/`check_staleness`
    direttamente da un'interfaccia esterna in parallelo a `publish_bundle`:
    sarebbe una duplicazione della sequenza di controlli, con rischio di
    divergenza silenziosa nel tempo.
- Corollario generale sull'elenco di bundle di un run
  (`run_dir/entities/*/`, prodotto da `gmv_notion_multi_candidate.py`):
  non creare un `MANIFEST.json` cache — andrebbe aggiornato manualmente ogni
  volta che un bundle passa a `PUBLISHED.json` e diventerebbe un secondo
  vocabolario di stato parallelo. Preferire sempre uno scan a runtime delle
  sottocartelle più lettura dei file già esistenti (`entity.json`,
  `NOTION_PAYLOAD.json`, presenza `PUBLISHED.json`).
- Nessun `*_FREEZE.md`/`*_SUSPENSION.md` copre oggi un'interfaccia
  web locale di revisione bundle. Ma il precedente di governance rilevante
  esiste: `GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md` e
  `GMV_RESEARCH_LAB_AUTOMATIONS_SUSPENSION.md` sono entrambi scattati per
  automazioni/servizi persistenti (LaunchAgent) privi di Service OID e
  registrazione in Service Registry (`00_CONFIG/SERVICE_SPECIFICATION.md`).
  Qualunque nuovo piccolo server locale va quindi proposto come processo
  avviato manualmente in foreground, mai come LaunchAgent/servizio
  schedulato, a meno di una decisione di governance separata ed esplicita.
