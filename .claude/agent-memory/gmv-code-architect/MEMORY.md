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

## Gap immagini/.doc in extract() — verificato 2026-08-29

`_extract()` in `10_API/gmv_evidence_pipeline.py:136-152` è un dispatcher deterministico per estensione: `{.txt,.md,.html,.csv,.json}` → lettura diretta; `.pdf` → `pypdf` (se testo vuoto, solleva già `EvidenceError("OCR_REQUIRED")`, dichiarato in `TERMINAL_EXTRACTION` riga 25 — quindi un percorso OCR era già anticipato architetturalmente per i PDF scansionati, mai implementato); `.docx` → `python-docx`; qualunque altra estensione (inclusi `.jpg`/immagini e `.doc` legacy) → `EvidenceError("UNSUPPORTED_FORMAT")` senza nemmeno un tentativo. Le due status (`OCR_REQUIRED` vs `UNSUPPORTED_FORMAT`) sono già un'incoerenza esistente per lo stesso problema di fondo (nessun testo estraibile) a seconda del contenitore.

`extract()` (righe 155-178) è invece già la funzione giusta da estendere, non da duplicare: cache content-addressed per sha256+extractor_version, stessa struttura record, stesso vocabolario terminale. `semantic_extract_batch()`/`ollama_extract()` sono a valle e format-agnostic (consumano solo `record["text"]` con `extraction_status == SUCCESS`); non serve toccarli per aggiungere vision/OCR, solo alimentarli con testo prodotto da un nuovo branch di `_extract()`.

Backlog: questo gap è già tracciato come `AI-002 — Implement document/OCR extraction` (`GMV_V2_BACKLOG.md:978`, severità High, effort XL), scoping in Sprint 005 "AI/Dossier Engine" (`GMV_V2_EXECUTION_ROADMAP.md:332-367`, esplicitamente "non un Reasoning/Decision Engine generale"). Non è quindi una capability nuova da inventare, ma la prossima fetta già pianificata — va dimensionata come "AI-002, un formato controllato alla volta", non come pipeline vision completa in un colpo solo.

Le chiamate Ollama (health/warmup/retry/adaptive-split) vivono già nello stesso file e sono già sequenziali per la contesa hardware nota sul Mac mini M4 24GB (vedi voce precedente su gemma4:12b) — qualunque step vision-model locale deve passare dallo stesso loop sequenziale di `semantic_extract_batch()`, non un worker concorrente separato.

## Stato reale del codice pipeline evidence, verificato leggendo 10_API/ (consultazione 2026-08-29, richiesta gmv_artist_web_retrieve.py)

- **Nessun subcommand `evidence` in `11_CLI/gmv`** (dispatcher bash, `case` statement): `gmv_evidence_index.py`, `gmv_content_extract.py`, `gmv_semantic_extract.py`, `gmv_entity_resolve.py`, `gmv_claims.py`, `gmv_notion_candidate.py`, `gmv_evidence_ledger.py` sono script standalone in `10_API/`, invocati direttamente come processi Python, non wired nella CLI `gmv`. Non presumere che esista un comando `gmv evidence ...`. **(Superato da 2026-09-09: `evidence` è ora un subcommand reale, vedi sezione più sotto.)**
- Sequenza reale (non quella nominale della pagina Notion): `scan` (`gmv_evidence_index.py`, content-addressed sha256 su Dropbox) → `extract` (`gmv_content_extract.py`, cache per sha256+extractor_version, stati terminali SUCCESS/OCR_REQUIRED/UNSUPPORTED_FORMAT/FILE_TOO_LARGE/EXTRACTION_ABORTED_STALE_HASH/EXTRACTION_FAILED) → `analyze`/semantic (`gmv_semantic_extract.py` → `semantic_extract_batch`, unico stadio con Ollama, chunking deterministico + adaptive-split-on-truncation, cache per content+prompt_version+model) → `resolve` (`gmv_entity_resolve.py` → `resolve_claims`/`consolidate_claims`, resolution_status MATCH/NEW_ENTITY/AMBIGUOUS→RESOLVED/PENDING_RESOLUTION) → `candidate` (`gmv_notion_candidate.py` → `compare_entity`/`gate`/`build_incremental_patch`/`write_evidence_bundle`, gate finale a 3 valori READY_FOR_NOTION/REVIEW_REQUIRED/INSUFFICIENT_EVIDENCE).
- **`write_evidence_bundle` in `gmv_evidence_pipeline.py` scrive già `verification.json: {"status": "NOT_EXECUTED", "reason": "local verifier adapter pending"}`** — è l'ancora esplicita e già presente nel codice per un futuro `gmv_artist_verify_local.py`/web-retrieval stage; non è uno stub da reinventare ma un punto d'innesto dichiarato.
- **Vocabolario di stato claim/entity oggi conflate epistemic tier e provenienza**: `ollama_extract()` assegna default `status="SUPPORTED_BY_ARCHIVE"` a entità/claim non tipizzate dal modello; questo valore è consumato sia da `gate()` (in `gmv_evidence_pipeline.py`, controllo negativo su `{INFERRED,MISSING,CONFLICTING}`) sia da `SUPPORTED_CLAIM_STATUS = {SUPPORTED_BY_ARCHIVE, VERIFIED, CONFIRMED, VALID}` in `gmv_notion_candidate.py` (`build_incremental_patch`, altrimenti CONFLICT/`UNSUPPORTED_STATUS_OR_MISSING_PROVENANCE`). **Non esiste alcun campo `source_type`** nello schema claims/entity. Aggiungere un canale "web" richiede: (a) un nuovo valore di stato parallelo (es. `SUPPORTED_BY_WEB`) aggiunto a `SUPPORTED_CLAIM_STATUS`, mai una rinomina dei valori esistenti; (b) un campo `source_type` ortogonale su ogni riga, popolato deterministicamente dallo stadio produttore, non dal LLM.
- **`file_id` (sha256 del contenuto) è l'unico anchor di provenienza** condiviso da scan/extract/resolve/candidate (`FILE_INDEX.jsonl`, poi riletto da `_body_source`/`build_incremental_patch` per risolvere `source_locator`). Qualunque nuovo canale di evidenza (web) deve riusare lo stesso meccanismo content-addressed (registrare gli snapshot fetchati con un proprio `file_id`/riga indice, `source_type` esplicito, locator=URL invece di path Dropbox) invece di introdurre un meccanismo di provenienza parallelo — altrimenti si rompe `if not c.get("source_file_ids"): raise CLAIM_WITHOUT_EVIDENCE` e la lineage.
- L'intera pipeline evidence è **completamente file-based** (JSON/JSONL sotto `~/.gmv_core/area35-qa/evidence`, fuori dal repo Git), e **fuori dal Core persistence boundary SQLite** (`ADR_CORE_PERSISTENCE_BOUNDARY`): non registra nulla come Objects/Relations/Resources. `resource_service.py`/OID `RES-*` esistono nel Core ma non sono usati da questa pipeline. Non presumere integrazione Core per questa pipeline finché non è una decisione esplicita separata.
- Run Ledger: `gmv_run_ledger.py` (root repo) è il vero ledger event-sourced (append-only `events.jsonl`, `RunLock`, `RunIdentity`); `10_API/gmv_evidence_ledger.py` scrive **solo** un sotto-manifesto dentro un `run_dir` già esistente e lo dichiara esplicitamente ("non crea un secondo ledger") — pattern di riuso da imitare per qualunque nuovo stadio, incluso web-retrieval.
- `GMV_GOVERNANCE_INDEX.md` in questo worktree (`bridge-cse_...`) si trova alla radice del repo, non sotto `00_CONFIG/` come indicato nelle istruzioni generali dell'agente — verificare il path effettivo ad ogni consultazione invece di assumere `00_CONFIG/GMV_GOVERNANCE_INDEX.md` aprioristicamente su un dato branch/worktree.

## Bridging gmv_artist_web_retrieve.py into gmv_notion_candidate.py::main() — verificato 2026-08-29, branch feat/gmv-artist-web-retrieve (non ancora mergiato)

Letto `10_API/gmv_artist_web_retrieve.py` (`build_retrieval_requests`/`ingest_web_findings`/`verify_local`), `10_API/gmv_notion_candidate.py` per intero, e le funzioni `resolve_claims`/`consolidate_claims`/`gate`/`write_evidence_bundle` di `10_API/gmv_evidence_pipeline.py` su quel branch (non su main/HEAD di questo worktree, dove il file web-retrieve non esiste ancora).

- **Il punto di merge/dedup corretto per claim archivio+web è lo stadio `resolve` (`resolve_claims`+`consolidate_claims` in `gmv_evidence_pipeline.py`), non `gmv_notion_candidate.py::main()`.** `resolve_claims`/`consolidate_claims` sono già index-agnostic (non guardano mai `paths`/provenienza fisica, solo subject/predicate/object) e `consolidate_claims` raggruppa già per `(resolved_subject_id, norm(predicate), resolved_object_id, qualifiers)`, fondendo `source_file_ids` di claim con lo stesso valore letterale — se claim archivio e claim web finiscono nello stesso raggruppamento (stesso valore normalizzato), diventano già UN solo claim con provenienza mista, senza bisogno di logica nuova. Concatenare invece le due liste di claim (già consolidate separatamente) direttamente dentro `gmv_notion_candidate.py::main()` (es. un flag `--web-claims`) NON deduplica: produce due claim paralleli per lo stesso predicato che generano operazioni CONFLICT/ADD/UPDATE contraddittorie in `build_incremental_patch`, perché ogni claim viene confrontato indipendentemente contro lo stesso valore Notion esistente.
- **Bug di ordine trovato in `consolidate_claims`** (righe ~408-420 al momento della lettura): lo `status` del gruppo consolidato viene preso SOLO dal primo claim grezzo incontrato per quella chiave (`target = grouped.setdefault(cid, {..., "status": c.get("status", "SUPPORTED_BY_ARCHIVE")})`) e non viene mai ricalcolato per i membri successivi. Finché tutti i claim in un gruppo condividono la stessa provenienza questo è innocuo; appena si mescolano provenienze eterogenee (archivio+web) nello stesso gruppo, l'esito diventa order-dependent: se il claim web (`SUPPORTED_BY_WEB`, gate-blocking) capita per primo nella lista grezza, il gruppo resta bloccante anche se un claim archivio equivalente lo corrobora. Va corretto con una regola di precedenza esplicita (mai "primo vince"), non aggirato ordinando i claim lato chiamante.
- **`gmv_notion_candidate.py` non ha alcun file di test** (`tests/test_gmv_notion_candidate.py` non esiste, verificato con `git ls-tree`), quindi il ramo `--run-dir` di `main()` — incluso l'assunzione `index_path = a.run_dir.parent/"state"/"index"/FILE_INDEX.jsonl` — non ha mai avuto una rete di sicurezza né una verifica end-to-end che `run_dir.parent/"state"` coincida davvero con l'`evidence_root` usato da scan/extract/ingest_web_findings. Non trattare quella convenzione di path come stabilita solo perché è nel codice: va testata esplicitamente prima di appoggiarcisi per un secondo indice (`WEB_INDEX.jsonl`). **(Superato da 2026-09-09: `tests/test_gmv_notion_candidate.py` esiste ora.)**
- `main()` oggi ricostruisce manualmente l'indice `FILE_INDEX.jsonl` con un loop inline invece di riusare `load_index()` (già esistente in `gmv_evidence_pipeline.py`, già usata da `gmv_artist_web_retrieve.py`) — piccola duplicazione preesistente da correggere quando si tocca questo punto, non da ripetere per `WEB_INDEX.jsonl`.
- `main()` non passa mai `source_paths` a `write_evidence_bundle` (chiamata senza quell'argomento opzionale) — quindi `sources.json` nel bundle è oggi sempre `paths: []`, anche per claim d'archivio. È un gap di provenance lineage preesistente, indipendente dal lavoro web, ma la stessa modifica che risolve i locators web dovrebbe alimentare anche questo parametro, altrimenti il bundle resta con lineage incompleta anche dopo aver "risolto" i locators per patch/body.
- `write_evidence_bundle`'s placeholder `verification.json = {"status": "NOT_EXECUTED", ...}` era già un punto d'innesto dichiarato (vedi voce precedente in questa memoria); ora che `verify_local` esiste, il pattern corretto è: riaggiungere il parametro opzionale `verification` E il chiamante reale (main(), calcolando un riepilogo VERIFIED/SUPPORTED_BY_WEB dai claim già passati per `verify_local`) nello stesso cambiamento — mai il parametro da solo "per uso futuro" (causa già stata di un rilievo del gmv-code-reviewer in un giro precedente).
- Vocabolario di stato: nessuna modifica necessaria lato `gmv_notion_candidate.py` — `SUPPORTED_CLAIM_STATUS` include già `VERIFIED` e esclude correttamente `SUPPORTED_BY_WEB`; `GATE_BLOCKING_STATUS` (già esteso su questo branch in `gmv_evidence_pipeline.py` con `SUPPORTED_BY_WEB`) è il posto giusto e unico dove quel vincolo vive.

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

## Real Estate ("immobili") domain already exists in GMV — verified 2026-09-27, consultation on Laya/MLX property-status integration

Before this consultation, no evidence had been checked for a "property/immobile"
domain. It exists, but almost entirely outside Core, and touches three
governance items that must be checked on any real-estate-adjacent proposal:

- **`00_CONFIG/REALESTATE_LEGACY_FREEZE.md`**: freezes only the
  Director/orchestration layer (`realestate_runner.py`,
  `real_estate_director.py`, `real_estate_recursion_check.py` —
  `99_SYSTEM/03_DIRECTORS/` in Dropbox). Reason: Dropbox-resident runtime
  writing operational state (`~/.gmv_runtime/realestate_state.json`), no
  Service OID, unregistered, dormant. Reactivation requires Project Owner
  approval + Core relocation + Service registration + test coverage. A new
  real-estate feature does not reactivate this by existing, but must not
  repeat the same violation pattern (Dropbox-resident executable code,
  unregistered, writing state outside Core) — any new script must live in
  Core (`10_API/`) from day one, not be authored/run from Dropbox.
- **Market Engine `SRV-000004`** (`01_RUNTIME/legacy/market_engine_v2.py`,
  `00_CONFIG/SERVICE_SPECIFICATION.md` §13) is registered, active,
  compatibility-mode, hash-pinned. It reads Dropbox
  `02_IMMOBILI/00_MARKET`/`02_COMPARABLES` markdown and does **purely
  regex/keyword extraction** (prezzo, €/mq, yield, rendimento, comparabile
  headings/numbers) — no LLM at all. Confirms "immobili" here means literal
  real estate (villas/apartments), not art. Good precedent for
  deterministic-first, but it's a pinned legacy compatibility artifact, not
  something to extend directly for new semantic work.
- **Dropbox `property_engine.py`** (found at
  `90_HISTORY/10_GMV_OS/99_SYSTEM/02_SERVICES/RealEstate/property_engine.py`)
  is a still-**UNCLASSIFIED** legacy item, open since REBASE 001 Task 3,
  explicitly listed `POST-STABILIZATION`/unscheduled in
  `PROJECT_STATUS.md` §3 and `SYSTEM_MAP.md` §4. It parses
  `01_PROPERTIES/PROPERTY_INDEX.md` (`### name` / `Stato:` / `Tipo:` /
  `Cartella attuale:` / `Scheda:` fields) and produces `PROPERTY_REPORT.md`
  / `PROPERTY_STATUS.md` by **counting files per property folder**
  (total/temp/priority) — a documentation-completeness check, not content
  semantics. It does not read document text or extract deadlines/risk.
  Because it is unclassified and its output filename is literally
  `PROPERTY_STATUS.md`, **do not name a new module/output
  `gmv_property_status.py`/`PROPERTY_STATUS.md`** — real collision risk
  with an item whose disposition is still open.
- **The real per-property document tree already exists and matches the
  user's stated inputs almost exactly**: Dropbox
  `02_IMMOBILI/01_PORTFOLIO/<PROPERTY>/` (seen: GERMIGNAGA, COURMA, MILANO,
  WITT12, VIG35, C2, VM8) each has `02_CONTRATTI`, `04_MANUTENZIONE`,
  `06_TECH`, `07_INQUILINO`, `03_FISCALE`, `08_ARCHIVIO STORICO`,
  `00_KNOWLEDGE`, `01_DOCS`, `00_REVIEW_PRIORITY`, `TASKS.md`,
  `PROPERTY_HISTORY.md`, `OBJECT.yaml`. This is the real evidence source
  for "email/verbali/contratti/segnalazioni manutenzione" — a new document
  ingestion feature should point at this tree via the same content-addressed
  scan mechanism as evidence pipeline, not invent a new document root.
- **`OBJECT.yaml` per property carries `schema: GMV_OBJECT_V1`,
  `gmv_id: GMV-REA-000001`** — a pre-Core, Dropbox-native ID convention.
  `REA` is **not** one of the six closed OID prefixes in
  `ADR_DB008_OID_PREFIX_TYPE_CONSISTENCY.md` (`COR/PER/PLG/RES/SRV/SYS`).
  Treating a "property" as a first-class typed Core Object is therefore not
  a trivial mapping — it needs its own explicit ADR-level decision (new
  prefix or reuse of an existing one) before any Core Objects-table
  integration is attempted. Until then, property-derived structured output
  should stay file-based/Runtime-output-classed, same posture as the
  evidence pipeline (`ADR_CORE_PERSISTENCE_BOUNDARY`: not yet Core SQLite).
- **`COURMA/TASKS.md` literally says "Aggiornare Morning Brief con eventuali
  scadenze"** (a human-authored instruction, found live in the data, not a
  proposal) — the intended consumer of property deadlines, by the data's
  own convention, is **Morning Brief** (`SRV-000002`, registered, active,
  compatibility-mode, entrypoint `~/.gmv_scripts/genera_morning_brief.sh`).
  A new deadline-extraction feature should treat Morning Brief as the
  eventual downstream reader, but must not write logic *into* the
  hash-pinned compatibility script itself — it should produce a structured
  file artifact Morning Brief (or a future native successor) can read,
  mirroring how Market Engine only ever *writes* `MARKET_REPORT.md`/
  `MARKET_STATUS.md` and never calls anything downstream itself.
- **`GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md`** froze exactly the pattern
  of "compute an advisory score/flag and write it somewhere with no
  confirmed consumer, no gate, no binding effect" when done as *unregistered
  automation* — its freeze reasoning explicitly cites "no component may
  bypass Reasoning/Decision/autonomous-workflow gates" (also stated
  verbatim in `GMV_ARCHITECTURE.md` line 72). This directly reinforces
  (not just by analogy) that a model-derived `rischio_alto` flag must
  surface as consultative human-review input only, never as a trigger for
  any autonomous action (notification, escalation, status change) — that
  would need the same Reasoning/Decision gates this repo has not yet built.
- Net: the correct integration shape is a **new stage bolted onto the
  existing evidence-pipeline primitives** (`gmv_evidence_index.py` scan +
  `gmv_content_extract.py` extract, both already generic/format-addressed,
  not artist-specific), **not** a new service, not a revival of the frozen
  Real Estate Director, not a rename/overwrite of the unclassified
  `property_engine.py` output files, and not a write path into Morning
  Brief's compatibility script.

## Ontology/predicate governance system: real, mature, but NOT on main — verified 2026-09-27/28

`00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json` + `10_API/gmv_atom_validator.py` +
`00_CONFIG/EPISTEMIC_INGESTION_RULES_v0.2.json` + a frozen 18-field ATOM
schema (`GMV_KNOWLEDGE_MONAD_SPEC_v1.0`) exist only on branch/worktree
`worktree-bridge-cse_01EFSz2nNresRvPh9GbfwwzK` (`origin/worktree-bridge-cse_01EFSz2nNresRvPh9GbfwwzK`).
Confirmed via `git merge-base --is-ancestor <ontology-commit> origin/main` →
NOT an ancestor. That branch is 106 commits ahead of its merge-base with
main (`92dad42c`, itself 4 commits behind current main tip `b480b04f`) and 0
commits behind — a clean-ish but large, unfinished, active line of work
("rescue medium/dimensions captions into atoms" was the tip when checked),
built specifically for the Area35 **art** domain (WORK/ARTWORK_INSTANCE/
EXHIBITION/curated_by/edition_of etc.), real-corpus-validated on artist
biographies, not real estate. Do not treat it as mergeable-on-a-whim: 106
commits of unreviewed-here work is a Project Owner-level decision, not
something to pull in for an unrelated feature.

**Meta-governance gap, worth repeating as a lesson**: even on its OWN
branch, `GMV_GOVERNANCE_INDEX.md` does not reference
`GMV_ONTOLOGY_REGISTRY_v0.1.json`, `GMV_KNOWLEDGE_MONAD_SPEC_v1.0`, or
`EPISTEMIC_INGESTION_RULES_v0.2.json` at all (grep empty on both). A real,
rigorously-built governance artifact was never itself indexed. Any new
ontology/predicate registry (any domain) must be added to
`GMV_GOVERNANCE_INDEX.md` in the same change that introduces it — don't
repeat this gap.

**Bigger structural finding: main already has an unconstrained
subject/predicate/object claim shape, with NO ontology governance wired in,
for ANY domain (art included)** — this predates and is independent of the
unmerged atom system. `10_API/gmv_evidence_pipeline.py`: the LLM extraction
JSON schema (~line 59) requires claims as `{subject_raw, predicate:
<free string, no enum>, object_raw, evidence_excerpt}`; `resolve_claims`
(~577) resolves subject/object against `notion_rows` into
`resolved_subject_id`/`resolved_object_id`; `consolidate_claims` (~618)
groups by `(resolved_subject_id, norm(predicate), resolved_object_id,
qualifiers)`, enforces `CLAIM_WITHOUT_EVIDENCE` if `source_file_ids` is
empty. `predicate` is never checked against any registry anywhere on main.
**Implication for any "governed predicates" request (real estate or
otherwise): the claim/resolution/consolidation machinery to build on
already exists and is merged/tested — what's missing on main, for every
domain, is only the registry file + a validation step comparing `predicate`
(and object type) against it**, mirroring what `gmv_atom_validator.py` does
on the unmerged branch (`predicate_is_governed`,
`object_type_matches_predicate_range`) but pluggable onto the
already-merged claim shape instead of the unmerged 18-field ATOM schema —
much less new surface than it first appears, and does not require adopting
the unmerged system's ATOM/EIC machinery at all.

Registry file shape worth imitating structurally regardless of dependency:
top-level `governance_rule` ("reuse-before-invention"), `status_values`
(CORE/DOMAIN/CANDIDATE/DEPRECATED), `predicate_classes` (IDENTITY/
ATTRIBUTE/RELATION/EVENT/MEASURE/EPISTEMIC), `entity_classes[]`
(`class_id`, `status`, `aliases`, `definition`, `source_reference`),
`predicates[]` (`predicate_id`, `predicate_class`, `status`, `domain[]`,
`range[]`, `aliases`, `inverse`, `definition`, `source_reference`). Every
CANDIDATE entry there cites concrete real-corpus case counts as
`source_reference`, never invented — same discipline should apply to any
new registry (cite the real validation evidence already in hand, e.g. an
existing N-case validation summary file, not invented examples).
