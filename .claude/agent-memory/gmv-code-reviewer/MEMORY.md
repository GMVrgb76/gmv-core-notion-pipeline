# Memoria — gmv-code-reviewer

Indice di lezioni di review stabili e riutilizzabili su GMV Core. Non è
caricata automaticamente: l'agente la legge esplicitamente a inizio review
(vedi `.claude/agents/gmv-code-reviewer.md`, sezione Memoria).

Voci verificate sul repository al 2026-08-29:

- Due failure mode reali già osservati nella pipeline evidence (validazione
  end-to-end 2026-08-26/28, documentata in `EVIDENCE_PIPELINE_RPC_VALIDATION.md`
  nel checkout locale di area35-qa): (1) `extract()` non gestisce immagini né
  `.doc` legacy — `UNSUPPORTED_FORMAT` silenzioso, zero claim prodotti anche
  se l'evidenza esiste; (2) `build_incremental_patch` va in `ValueError:
  EXISTING_PAGE_ID_UNRESOLVED` per entità `NEW_ENTITY` — il percorso
  `--run-dir` gestisce solo `UPDATE`. Se una review tocca questi percorsi,
  verificare esplicitamente se li corregge, li ignora, o introduce lo stesso
  pattern altrove.
- "GBrain" e "Shadow": nessun riscontro nel codice o nella storia Git di
  nessun branch alla data della verifica — trattare riferimenti ad essi come
  assunzione da verificare, non come premessa valida.

## Vincoli da "Notion Page Extraction Candidate" (fonte Notion, letta 2026-08-29, ultimo aggiornamento pagina 28 agosto 2026)

Documento architetturale canonico per la pipeline artista→Notion — i due
failure mode sopra (immagini/`.doc` non estratti, `NEW_ENTITY` crash) sono
confermati anche lì, con lo stesso dettaglio. In più:

- **Non toccare senza motivo esplicito e senza segnalarlo:** adaptive
  splitting/fallback ~500 caratteri, provenance, manifest, fail-closed
  design, Evidence Bundle, `NOTION_PATCH.json` — marcati esplicitamente "non
  modificare ancora" nel documento architetturale. Una PR che li tocca va
  trattata come cambiamento architetturale maggiore, non come dettaglio
  implementativo.
- **Esecuzione LLM deve restare sequenziale.** Il parallelismo fra modelli
  sul Mac mini locale è una causa di failure già diagnosticata (contesa
  hardware, tempi/success rate alterati). Una modifica che introduce
  chiamate Ollama concorrenti va segnalata come `ARCHITECTURAL ISSUE`, non
  come preferenza stilistica — contraddice un finding già validato, non
  un'opinione.
- **Duplicazione da controllare attivamente:** questo stesso documento ha
  dovuto verificare se `gmv folder-report` copriva già lo stadio 1 prima di
  proporre `gmv_artist_extract.py` nuovo. Una modifica che introduce
  estrazione/scansione file senza aver verificato `gmv folder-report`/gli
  estrattori Notion esistenti è lo stesso pattern di duplicazione da
  bloccare o segnalare.
- Config LLM locale validata da riusare come baseline per "evidenza di
  correttezza reale" quando si revisiona codice di estrazione semantica:
  `gemma4:12b`, `num_ctx=8192`, `num_predict=4096`, `think=false`,
  `max_chunk_chars=8000`, `min_adaptive_chunk_chars=500`.

Nessuna lezione di review aggiuntiva accumulata ancora da review reali.

## Lezione verificata 2026-09-13: docstring "riusato, non inventato" va sempre grep-verificata

Un contratto astratto (`10_API/gmv_projection_adapter_contracts.py`) dichiarava
esplicitamente nel docstring di riusare due vocabolari già vivi nel codice
(`OperationAction` da `gmv_notion_candidate.py`/`gmv_notion_multi_candidate.py`;
`Gate` dal `gate()` reale in `gmv_evidence_pipeline.py`). Entrambe le
affermazioni erano false alla verifica diretta:

- Il vocabolario action per-campo realmente prodotto è `{"ADD","UPDATE",
  "CONFLICT"}` (mai "CREATE" — quello è solo il valore del campo entity-level
  `operation`; "KEEP" viene calcolato ma mai scritto in `operations`, è
  rappresentato per assenza).
- Il `gate()` vivo restituisce `{"READY_FOR_NOTION","REVIEW_REQUIRED",
  "INSUFFICIENT_EVIDENCE"}`, non `{"AUTO_ACCEPT","REVIEW_REQUIRED","BLOCKED"}`
  — solo un valore su tre coincide.

**Lezione generale:** quando un modulo nuovo dichiara "questo vocabolario non
è inventato, è riusato da X" — non fidarsi della prosa, nemmeno se accurata
e ben scritta altrove nello stesso file (lo stesso file aveva altre
affermazioni verificate corrette, es. sui 6 return code di `publish_bundle()`
e sul gap entity_type IT/EN). Fare sempre `grep -n '"action"'` (o equivalente)
sui moduli citati come fonte, non fidarsi della sintesi. Un contratto/tipo
può sbagliare la sua stessa premessa fondante (evitare vocabolari paralleli)
proprio mentre dichiara di rispettarla.

**Pattern di falsa evidenza da controllare sempre:** un test che dichiara nel
nome/docstring di "pinnare"/verificare la fedeltà a un modulo esterno, ma che
in realtà confronta solo `TypeAlias.__args__` (o simili) contro un secondo
insieme hardcoded nello stesso file di test, senza mai importare o ispezionare
il modulo esterno citato. Passa sempre, non rileva mai drift dal codice reale
che dichiara di proteggere — solo drift dal contratto stesso. Verificare
sempre se il test importa davvero il modulo di riferimento prima di contare
"test verdi" come evidenza.

## Lezione verificata 2026-09-13 (review gmv_atom_validator.py): overclaim di un solo campo dello schema, e riuso parziale non dichiarato

Un modulo di validazione (`10_API/gmv_atom_validator.py`) dichiarava nel docstring
di applicare "ontology governance" su due campi (PREDICATE e, dove identity-typed,
OBJECT_TYPE) contro `GMV_ONTOLOGY_REGISTRY_v0.1.json`. Verifica diretta (`grep -n
"object_type"`): solo la dichiarazione del campo nel dataclass, nessuna regola lo
controllava, nessun test lo copriva. Il vocabolario `predicates` del registry era
davvero consultato; `entity_classes` — necessario per OBJECT_TYPE — non veniva mai
letto nonostante `_load_ontology_registry()` caricasse l'intero file.

**Lezione generale (rafforza quella del 2026-09-13 precedente):** un overclaim può
essere parziale, non totale — un modulo può riusare davvero un vocabolario/import
per un campo (verificato vero) e nello stesso paragrafo dichiarare falsamente di
applicarlo anche a un secondo campo correlato. Non basta verificare una singola
affermazione "riusato, non inventato" e fermarsi: quando il docstring elenca più
campi/controlli nella stessa frase, verificare ciascuno separatamente con grep,
non assumere che la verifica di uno implichi la veridicità degli altri.

**Seconda lezione, distinta:** quando un modulo dichiara di riusare "la logica di
normalizzazione/deduplicazione già presente" in un file più vecchio, verificare se
quel file più vecchio risolve *più di una* funzione di normalizzazione per lo
stesso problema generale (qui: `area35_validator.py` ha sia `norm()` sia
`_forma()`, quest'ultima specificamente per riconciliare ordine "Cognome, Nome" vs
"Nome Cognome" nei duplicati persona/artista). Un modulo nuovo può importare e
riusare correttamente una delle due funzioni (`norm`, verificato con `is`) mentre
omette l'altra (`_forma`) senza dichiararlo — producendo un gap di deduplicazione
concreto (falsi negativi: stesso claim, ordine del nome diverso, fingerprint
diverso) che il repo aveva già risolto altrove per lo stesso tipo di dato. Cercare
sempre, nel file citato come fonte di riuso, se esistono più utility correlate
allo stesso problema, non solo quella effettivamente importata.
