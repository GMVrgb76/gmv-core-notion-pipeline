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

## Lezione verificata 2026-09-14 (review gmv_crawler_extractor.py): un wrapper "mai solleva eccezioni" va verificato contro TUTTE le eccezioni della funzione avvolta, non solo il tipo di eccezione dichiarato

Un modulo nuovo (`10_API/gmv_crawler_extractor.py::extract_document()`) avvolge
`gmv_evidence_pipeline._extract()` con `except EvidenceError` e dichiara nel
proprio docstring "Never raises for an extraction-format failure ... a caller
processing many sources can iterate without a per-file try/except". Falso,
riprodotto direttamente: per `.txt/.md/.html/.csv/.json`, `_extract()` fa
`path.read_text(encoding="utf-8", errors="strict")` senza alcun try/except
attorno (a differenza dei rami `.pdf`/`.docx`/`.doc`, che catturano
`ImportError`/`PyPdfError`/subprocess error e li convertono in
`EvidenceError`). Un file di testo con encoding non-UTF-8 (scenario reale, non
patologico — es. bio artista legacy in windows-1252) solleva
`UnicodeDecodeError` non gestito attraverso tutto il wrapper. La funzione
originale che il modulo cita come modello di parità (`gmv_evidence_pipeline.
extract()`) cattura esplicitamente `except (OSError, UnicodeError)` attorno
alla stessa chiamata — il wrapper nuovo omette quella seconda clausola.

**Lezione generale:** quando un modulo nuovo avvolge una funzione esistente e
dichiara "non solleva mai eccezioni per un fallimento di formato" o simile,
non fidarsi del claim sulla base del solo tipo di eccezione esplicitamente
gestito (qui `EvidenceError`). Leggere l'*intero* corpo della funzione avvolta
per ogni ramo/formato e cercare chiamate non protette (I/O, decode, parsing)
che possano sollevare tipi di eccezione diversi da quello dichiarato/atteso
(`OSError`, `UnicodeError`/`UnicodeDecodeError`, ecc.). Se esiste già un
chiamante precedente della stessa funzione nel repo (qui `extract()` nello
stesso file), confrontare quali except-clause usa quel chiamante: un wrapper
nuovo che ne cattura un sottoinsieme stretto è un segnale concreto di gap, non
una preferenza di stile. Un test di cross-check basato su regex/AST che
verifica solo i codici `raise EvidenceError(...)` (o equivalente) non copre
questo tipo di gap per costruzione — è cieco a eccezioni di tipo diverso da
quello che cerca, e questo va segnalato esplicitamente come limite del test,
non solo come test "verde quindi ok".

## Lezione verificata 2026-09-14 (review gmv_dropbox_connector.py): un claim "nessun meccanismo esistente per X" va grep-verificato quanto un claim "riuso Y" — è lo stesso errore speculare

Il docstring di `10_API/gmv_dropbox_connector.py` giustificava la reimplementazione
ad-hoc della risoluzione del token ("no existing credential-storage mechanism to
build on") elencando cosa aveva grepppato (SDK Dropbox, codice OAuth, secrets
vault, `secure_storage.py`). Verificato falso: `credentials.py` nella root del
repo espone già `get_token(name, file_fallback=None) -> ResolvedToken`, un
meccanismo centralizzato e generico (parametrizzato per nome env var, non
hardcoded al suo attuale consumer) con lo stesso pattern esatto — env var,
poi fallback, altrimenti errore esplicito mai silenzioso — usato realmente da
6 file (`notion_extract.py`, `adapter_notion.py`, `notion_publish.py`, ecc.).
Il grep dichiarato nel docstring era reale (le tre cose cercate davvero non
c'erano) ma incompleto: ha mancato l'unico componente rilevante per la
decisione che stava giustificando.

**Lezione generale:** le lezioni precedenti (2026-09-13) coprivano il caso
"il modulo dichiara di riusare X, verificare se è vero". Questo è il caso
speculare, altrettanto pericoloso: "il modulo dichiara che X non esiste nel
repo, quindi reimplementa da zero" — va verificato con lo stesso rigore.
Un grep dichiarato nel docstring (anche con termini di ricerca elencati
esplicitamente, es. "grepped: no X, no Y, no Z") non è evidenza sufficiente:
i termini di ricerca stessi possono essere sbagliati/incompleti. Prima di
accettare "nessun precedente esistente" come giustificazione per una nuova
astrazione (qui: gestione token), fare il proprio grep indipendente per il
tipo di componente realmente rilevante (qui: non "dropbox"/"OAuth"/"secrets
vault" ma "credential"/"token" a livello di funzione riusabile), non solo
ripetere i termini che l'autore del modulo ha già cercato.
