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

## Lezione verificata 2026-09-14 (review gmv_crawler_candidate_extractor.py): vocabolario riusato per import ma con semantica d'uso incompatibile con l'originale — variante del pattern "riuso non verificato"

Il modulo importava davvero `STATUS_PRECEDENCE` da `gmv_evidence_pipeline.py` (nessun
vocabolario inventato ex novo — il grep di superficie "è importato, non duplicato"
era vero). Ma lo usava come whitelist di rigetto (`if status not in STATUS_PRECEDENCE:
raise ValueError`), mentre il codice sorgente che lo definisce dichiara esplicitamente
nel proprio commento che quel campo è "free text, not an enum" e usa la lista solo
per un ranking tollerante (`_better_status`, mai un raise). Riprodotto empiricamente:
un solo status fuori whitelist tra più candidati validi fa collassare `tuple(...)`
dentro una list/generator comprehension e cancella *tutti* i candidati del batch,
non solo quello con lo status incriminato — un local LLM (gemma-class) emette status
come free text senza vincolo enum né nel prompt né nello schema JSON (`"status":
{"type": "string"}`, nessun `enum`), quindi questo non è un edge case ipotetico ma
il comportamento atteso al primo run reale.

**Lezione generale (estende quella del 2026-09-13 su `gmv_projection_adapter_contracts.py`):**
non basta verificare che un vocabolario citato come "riusato, non inventato" sia
davvero importato dal modulo sorgente corretto — bisogna verificare anche che la
*semantica d'uso* (rigetto rigido vs tolleranza/ranking) coincida con quella che il
modulo sorgente stesso applica. Un `grep` che conferma l'import è necessario ma non
sufficiente; leggere anche i commenti/il comportamento reale attorno a quel
vocabolario nel file sorgente (qui: `_better_status`'s commento esplicito "always
loses to a recognized one" era la prova diretta della tolleranza intesa). Inoltre:
quando una validazione di un singolo campo (`status`) vive dentro il `__post_init__`
di un dataclass costruito in una list/tuple comprehension su più item, un'eccezione
da un solo item propaga e cancella l'intero batch — verificare sempre se questo
comportamento all-or-nothing è compatibile con la semantica "per-item" che la spec
dichiara (qui §10: "il candidato è rifiutato", singolare, non l'intero documento).
Un test che valida solo il costruttore in isolamento (item singolo) non rileva
questo effetto collaterale — serve un test esplicito con batch misto (un item
valido + un item che fallisce la validazione) per dimostrarlo.

## Lezione verificata 2026-09-15 (review gmv_crawler_reconciliation.py): un rischio noto e già "earmarked" da un handoff precedente per lo step in revisione va cercato esplicitamente, non solo il rischio in sé

`compute_atom_fingerprint()` (step 7, `gmv_atom_validator.py`) documenta già nel proprio
docstring un trade-off accettato: `_forma()` applicato a OBJECT senza gating su
OBJECT_TYPE puo' far collidere due valori multi-parola genuinamente diversi che
condividono le stesse parole in ordine diverso (es. "Venice Biennale" vs "Biennale
Venice" -> stesso fingerprint). `GMV_CRAWLER_HANDOFF.md` (documento di continuità
del progetto, non solo commento di codice) elenca esplicitamente questo trade-off e
dichiara "likely where [it] needs to be resolved for real" riferendosi proprio allo
step successivo (qui: step 12, Reconciliation engine). Il nuovo modulo step 12
riusa `compute_atom_fingerprint()` come chiave di identità (corretto, per istruzione
esplicita di non reimplementare) ma non menziona mai questo trade-off nel proprio
docstring, nonostante sia insolitamente dettagliato su tutte le altre scelte di
scope. Riprodotto empiricamente: due atomi con OBJECT letterale diverso
("Venice Biennale" / "Biennale Venice"), SOURCE diversa, stesso PREDICATE ->
`reconcile()` restituisce SUPPORTING ("corroborazione indipendente della stessa
claim"), etichetta potenzialmente falsa per un OBJECT che potrebbe riferirsi a
un'entità realmente diversa (rischio concreto per OBJECT_TYPE non-persona:
PLACE/EVENT/DOCUMENT, molto comuni in un crawler d'arte).

**Lezione generale:** quando una funzione riusata ha un trade-off/rischio già
documentato nel proprio file sorgente, cercare *anche* se un documento di
continuità del progetto (handoff notes, roadmap, backlog) ha già dichiarato che
"lo step attuale/successivo è probabilmente dove va risolto per davvero". Se sì,
il silenzio del modulo nuovo su quel rischio non è solo un'eredità neutra — è un
gap di scope-acknowledgment specifico e prevedibile, da segnalare esplicitamente
anche se riprendere/non risolvere il rischio stesso è coerente con la governance
("riusa, non reinventare"). Non basta verificare che il riuso sia corretto
(lo è) — verificare separatamente se il modulo doveva almeno *dichiarare* di
ereditare un rischio già segnalato come "da risolvere qui" da un documento di
processo precedente. Applicabile a ogni step futuro dello stesso crawler pipeline
(`GMV_CRAWLER_HANDOFF.md` §"How to continue" elenca esplicitamente altri
trade-off aperti earmarked per step specifici non ancora costruiti).

## Lezione verificata 2026-09-15 (review gmv_crawler_fulltext_index.py, step 13): un ADR citato va letto fino in fondo, non fino alla clausola che conviene — e un test statico repo-wide "non esiste ancora" va sempre eseguito con il nuovo file *staged*, non solo letto

Il docstring del modulo giustificava un `sqlite3.connect()` grezzo dentro `10_API/`
(bypassando `gmv_core.database`) citando `ADR_CORE_PERSISTENCE_BOUNDARY.md` Decision
§3: il controllo statico "ARC-002" che rifiuterebbe un secondo `sqlite3.connect`
diretto fuori da `gmv_core` "e' deferred" e "non esiste ancora". Falso alla verifica
diretta: lo stesso identico documento ADR contiene, piu' in basso, un
**Addendum datato 2026-07-21** — "ARC-002 static connect-boundary check confirmed
satisfied" — che chiude esplicitamente quella clausola deferred e conferma che il
controllo esiste ed e' attivo: `tests/test_sqlite_connection_boundary.py::
test_only_core_factory_calls_sqlite_connect`, che fa `ast.parse` di ogni file `.py`
tracciato sotto `01_RUNTIME/`, `10_API/`, `gmv_core/` e asserisce `set(calls) ==
{"gmv_core/database.py"}` con **esattamente un** call site `sqlite3.connect`
grezzo in tutto il repo. Riprodotto empiricamente: `git add` dei due file nuovi
(ancora untracked al momento della review) seguito da `pytest tests/
test_sqlite_connection_boundary.py` fa fallire immediatamente quel test — e
`scripts/quality_gate.sh` (il CI reale) esegue `python -m pytest -q` sull'intera
suite, quindi il commit di questo modulo rompe la quality gate al primo push, non
solo in teoria.

**Lezione generale (variante piu' grave delle lezioni precedenti su "riuso non
verificato"):** quando un docstring cita un ADR per giustificare l'aggiramento di
un confine architetturale, non fermarsi alla prima clausola che sembra dare
ragione all'autore — leggere l'intero documento fino alla fine, compresi eventuali
Addendum/Amendment successivi alla Decision originale (qui l'Addendum e' *nello
stesso file*, poche righe sotto la clausola citata, con una data piu' recente che
la supera esplicitamente). Un ADR con un Addendum che "chiude" una clausola
deferred e' un pattern che ricorrera' in futuro in questo repo (il processo Sprint
003 lo usa esplicitamente come meccanismo). Inoltre: quando un modulo nuovo
dichiara "questo controllo statico repo-wide non esiste ancora / non mi si applica
ancora perche' sono untracked", **non fidarsi della lettura del codice del test
da sola** — eseguire `git add` dei file nuovi (rollback subito dopo con `git
restore --staged`) e far girare quel test specifico prima di accettare la
premessa. Qui il test AST-based ignora i file non tracciati per costruzione
(usa `git ls-files`), quindi "il test non fallisce oggi" era vero ma irrilevante:
falliva nel momento esatto in cui il modulo sarebbe diventato cio' che e' stato
progettato per essere (un file tracciato e committato in `10_API/`). Questo e'
un blocker dimostrato, non un rischio plausibile — riprodotto con un comando reale,
non dedotto dalla lettura del codice.

**Nota collaterale:** la giustificazione "architetturale" nel docstring ("FTS e'
dato derivato/ricostruibile, quindi fuori dal confine SEC-006") non regge comunque
come lettura del confine *realmente enforced*: il test statico non distingue dato
canonico da dato derivato — vieta *qualsiasi* secondo call site `sqlite3.connect`
grezzo in `01_RUNTIME/`/`10_API/`/`gmv_core/`, punto. La distinzione
canonico/derivato puo' essere un argomento valido per una *futura* decisione di
Project Owner che amenda l'ADR (es. escludendo esplicitamente indici derivati dal
confine, o spostando questo modulo fuori dalle production roots sorvegliate), ma
non e' il criterio che il controllo attuale applica oggi — presentarla come se il
bypass fosse gia' coperto dalla policy vigente e' un overclaim, non solo una
lettura incompleta.

**Follow-up verificato 2026-09-15, stesso giorno: la remediation ha chiuso il blocker, riverificato indipendentemente.** Il coordinator ha aggiunto `FTS_INDEX_OWNER` in `tests/test_sqlite_connection_boundary.py` e un secondo `_NON_CORE_DML_SITES` in `tests/test_write_authorization.py::test_dml_capability_matrix_matches_source` (un secondo controllo statico distinto, basato su AST/regex su INSERT/UPDATE/DELETE indipendentemente dal tipo di connessione, che il mio primo giro di review non aveva controllato esplicitamente — trovato dal coordinator, poi confermato da me leggendo il file). Entrambe le whitelist restano rigorose (uguaglianza esatta di insiemi, non un permesso generico) e **non** aggiungono la nuova INSERT a `authorization.DML_CAPABILITIES` (che avrebbe erroneamente concesso una capability SEC-006 runtime a un modulo che non passa mai da `AuthorizingConnection`) — la distinzione fra "autorizzato a runtime" e "inventariato/riconosciuto nell'audit statico" e' stata rispettata correttamente. Riverificato in modo indipendente (non fidandosi del resoconto): `git diff --cached` sui due file di test, poi `pytest -q` sull'intera suite con i 4 file nuovi/modificati effettivamente su disco → 951 passed, `ruff check .` pulito, i due test di boundary rieseguiti isolatamente → 48 passed. Cercato attivamente anche un possibile terzo controllo statico non coperto (`tests/identity/test_writer_boundary.py`, `tests/migrations/test_version_fixture_targets.py`, `quality/LEGACY_EXCEPTIONS.md`, `quality/SECURITY_GATE_POLICY.md`) — nessuno di questi si applica (il primo controlla solo le tabelle `objects`/`oid_sequences`, gli altri sono su tutt'altro dominio).

**Lezione generale aggiuntiva:** quando un blocker su un confine SEC-006/ARC-002 viene "risolto" con una whitelist nominata, verificare sempre due cose distinte, non una sola: (1) che il controllo statico che aveva bloccato sia stato aggiornato correttamente (ovvio), e (2) che la nuova voce **non** sia stata aggiunta anche alla matrice di autorizzazione *runtime* (`DML_CAPABILITIES`/`DDL_CALLERS` in `gmv_core/authorization.py`) se il modulo in questione non passa comunque da `AuthorizingConnection` — altrimenti la remediation introdurrebbe silenziosamente una capability SEC-006 reale per un caller che non ne ha bisogno e non dovrebbe averla, un errore opposto ma speculare al blocker originale. In questo caso il coordinator l'ha evitato correttamente, ma va controllato esplicitamente ogni volta, non assunto.

## Lezione verificata 2026-09-15 (review gmv_crawler_derived_views.py, step 14): una funzione che promette "mai un'ambiguita' nascosta" va testata sia contro falsi negativi (alias/governance-equivalenza ignorata) sia contro falsi positivi (duplicati esatti in input)

`derive_current_state()` raggruppa atomi per slot `(_forma(subject), predicate)` e dichiara,
testato con 5 unit test dedicati, di non fare mai una scelta silenziosa fra piu' candidati VALID
in competizione. Due gap reali, riprodotti empiricamente, non coperti da nessuno dei 17 test:

1. **Falso negativo (ambiguita' reale non vista):** il grouping usa la stringa `predicate` grezza,
   non risolta attraverso l'alias table del registry di governance
   (`gmv_atom_validator._known_predicates`, gia' esistente per un motivo esplicito: due predicati
   testualmente diversi ma registrati come alias, es. il caso reale gia' nel registry
   `source_for`/`evidences`, sono la stessa proposizione governata). Due atomi VALID con lo stesso
   subject normalizzato, stesso predicato-per-governance ma alias testuale diverso, OBJECT diverso,
   finiscono in due slot distinti e vengono riportati entrambi RESOLVED invece di un unico
   AMBIGUOUS -- esattamente il fallimento che la funzione dichiara di prevenire sempre. Questo gap
   e' ereditato da `compute_atom_fingerprint()` (step 7, gia' committato), che a sua volta non
   risolve gli alias per PREDICATE (il suo docstring spiega solo perche' non applica `_forma()` al
   predicato, non che salta la risoluzione alias) -- nessuna review precedente lo aveva individuato.
2. **Falso positivo (ambiguita' fittizia):** nessun dedup per `atom_id` prima del raggruppamento --
   lo stesso identico atomo presente due volte nella lista di input (stesso `atom_id`, stessi campi)
   produce un `AMBIGUOUS` fasullo con lo stesso `atom_id` duplicato in `candidates`.

**Lezione generale:** quando una funzione di raggruppamento/deduplicazione dichiara esplicitamente
una garanzia "mai una scelta silenziosa, sempre tutti i candidati in competizione visibili" --
verificare sia il lato "manca qualcosa che avrebbe dovuto unire" (chiavi di raggruppamento che
ignorano un vocabolario di equivalenza gia' costruito altrove nel repo per lo stesso campo, es.
alias di predicato) sia il lato opposto "unisce/segnala qualcosa che non avrebbe dovuto" (input
con voci duplicate esatte trattate come candidati realmente distinti). Un test che copre solo lo
scenario positivo previsto dal design (qui: due nomi persona con ordine parole diverso che devono
correttamente unirsi) non prova che la funzione regga sugli scenari avversariali speculari. Cercare
sempre, nel modulo sorgente da cui si riusa una chiave/normalizzazione (qui: PREDICATE preso alla
lettera), se esiste gia' nel repo un vocabolario di equivalenza governata per quello stesso campo
(qui: alias table del registry ontologico) prima di accettare "confronto per uguaglianza esatta
della stringa" come corretto.

## Follow-up verificato 2026-09-15, stesso giorno: remediation di gmv_crawler_derived_views.py (B1 alias-blindness, B2 falsa ambiguita' su duplicati) confermata chiusa, riverificata indipendentemente

Il coordinator ha risolto entrambi i BLOCKER della review precedente. Riverificato senza fidarsi della
descrizione, con dati diversi da quelli usati nei nuovi test del coordinator:
- B1: `derive_current_state()` ora risolve `predicate` al `predicate_id` canonico via
  `gmv_atom_validator._known_predicates(registry)` (funzione privata ma gia' esistente, riusata non
  reimplementata) prima di costruire la chiave di slot. Riprodotto con atom_id/object diversi da quelli
  del test del coordinator (`source_for`/`evidences`, oggetti "ClaimAlpha"/"ClaimBeta") -> 1 entry
  AMBIGUOUS, corretto.
- B2: dedup via `{atom.atom_id: atom for atom in atoms}.values()` prima del raggruppamento. Riprodotto
  con 3 copie (2 stesso oggetto Python + 1 value-equal ma oggetto Python distinto, stesso atom_id) -> 1
  sola entry RESOLVED, corretto anche nel caso non object-identity ma solo atom_id-equality.
- C1 (overclaim "imported"): ora il modulo importa davvero `FROZEN_PREDICATE_CLASSES` e solleva
  `RuntimeError` a tempo di import se "RELATION" sparisse dal set congelato -- guardia fail-fast reale,
  non solo prosa corretta. Verificato via grep degli import reali, non solo letto il docstring.
- C2 (DISPUTED silenzioso) e il rischio `_forma()` su SUBJECT: non risolti nel codice, ma ora dichiarati
  esplicitamente nel docstring del modulo come rischi noti/ereditati -- coerente con quanto richiesto.
- A2 (ordinamento non deterministico dei campi display): `candidates` ora ordinati per `atom_id` prima
  di scegliere quale atomo fornisce subject/predicate di display -- verificato nel codice.
- Full suite 972 passed, ruff pulito, confermato con esecuzione diretta (non solo fidandosi del resoconto).

**Due residui minori trovati in questo giro di re-verifica, non bloccanti, non menzionati dal coordinator:**
1. Il docstring di apertura del modulo dichiara ancora "no persistence, no engine, no I/O" ma la fix di
   B1 introduce I/O su disco di default in `derive_current_state()` (legge
   `GMV_ONTOLOGY_REGISTRY_v0.1.json` via `_load_ontology_registry()` quando il chiamante non passa un
   `registry` gia' caricato) -- un fix corretto puo' comunque disallineare un claim generale dichiarato
   altrove nello stesso file, se chi corregge non rilegge l'intero docstring per coerenza.
2. Il dedup per `atom_id` assume l'unicita' di `atom_id`: due atomi con contenuto realmente diverso ma
   `atom_id` accidentalmente uguale (bug di integrita' a monte, non generato da questo modulo)
   vengono silenziosamente ridotti a uno solo, senza segnale. Edge case profondo (richiede un bug
   upstream), non introdotto ex novo dal fix in modo peggiore di quanto l'assunzione "atom_id come
   chiave primaria" gia' implichi altrove nel repo -- non bloccante, ma non testato ne' dichiarato.

**Lezione generale:** quando una remediation per un blocker introduce una capability nuova (qui: lettura
di un file di config di default), ricontrollare se un claim generale dichiarato altrove nello stesso
docstring (qui: "no I/O" nel paragrafo di apertura, non nella sezione della funzione corretta) e' ancora
vero dopo la fix -- una remediation mirata e corretta sulla funzione specifica puo' comunque rendere
falsa un'affermazione fatta altrove nello stesso file che nessuno ha pensato di ricontrollare.

## Lezione verificata 2026-09-15 (review gmv_crawler_public_projector.py, step 15): una costante grounded contro il nome giusto di file/riga ma il campo sbagliato — variante ulteriore del pattern "riuso non verificato"

Il modulo dichiarava `BLOCKED_EXTRACTION_STATUS = "BLOCKED"` "matches the real, live literal
`gmv_evidence_pipeline.py:538`", citando riga e file reali, e un test dedicato
(`test_blocked_extraction_status_matches_real_evidence_pipeline_literal`) che fa
`assert '"status": "BLOCKED"' in source` sullo stesso file — verde, ma non prova nulla di
rilevante. Verificato: la riga 538 scrive il campo `"status"` (non `"extraction_status"`) dentro
`run_manifest.json`, a livello dell'intero run della fase SEMANTIC (LLM entity/claim extraction),
per un fallimento irreversibile dopo retry — un concetto e un livello di granularità
completamente diversi dal campo `extraction_status` per-singola-fonte che
`SourceManifestEntry`/questo modulo consultano davvero. Il vocabolario chiuso e reale per
`extraction_status` a livello di singola fonte, sia in `gmv_evidence_pipeline.extract()`
(`EXTRACTION_ABORTED_STALE_HASH`/`FILE_TOO_LARGE`/`SUCCESS`/`EXTRACTION_FAILED`/`str(exc)`) sia
nel layer crawler già committato (`gmv_crawler_extractor.STATUS_VALUES` =
`{SUCCESS, OCR_REQUIRED, UNSUPPORTED_FORMAT, EXTRACTION_FAILED, EXTRACTION_ABORTED_STALE_HASH}`,
validato in `ExtractionDocument.__post_init__`, e riusato letteralmente da
`gmv_crawler_candidate_extractor.py:231` come `"extraction_status": document.status`) **non
contiene mai la stringa "BLOCKED"**. Conseguenza: il gate "inferenze da fonti bloccate" —
uno dei gate che il modulo dichiara "mechanically enforced" — non può mai scattare contro nessuna
fonte realmente illeggibile/fallita prodotta da questa pipeline, esattamente l'opposto di quanto
richiesto dalla citazione che lo stesso modulo fa di crawler spec §24 ("una source illeggibile
deve esistere nel sistema come BLOCKED"). Non è (ancora) un difetto funzionale osservabile oggi —
`SourceManifestEntry` non viene mai costruito da codice reale nel repo, solo da fixture di test —
ma è un bug di grounding concreto che diventerà un gate morto/silenzioso nel momento in cui un
futuro step collega un manifest SOURCES reale a questo projector.

**Lezione generale:** citare un file e un numero di riga reali (`gmv_evidence_pipeline.py:538`) e
avere un test che fa `assert 'stringa letterale' in source_del_file` non è sufficiente come prova
di grounding — verificare sempre (a) il **nome del campo**, non solo la stringa valore, e (b) il
**livello/stage della pipeline** a cui quel campo appartiene, non solo che la stringa esista da
qualche parte nel file giusto. Un test-grounding che fa solo una substring-match su un file intero
(senza distinguere a quale chiave JSON o a quale funzione/stage appartiene la stringa trovata) è lo
stesso pattern di "falsa evidenza" già registrato il 2026-09-13 (test che confermano solo se stessi,
non il modulo esterno citato) — qui la variante è che il test legge davvero il file esterno giusto,
ma verifica il campo sbagliato. Quando un modulo nuovo introduce una costante che deve mirrorare un
vocabolario di stato **per-entità/per-sorgente** (qui: extraction_status di una singola fonte), cercare
esplicitamente il vocabolario chiuso più recente/più vicino a quel livello già committato nel repo
(qui: `gmv_crawler_extractor.STATUS_VALUES`, uno step precedente della stessa pipeline crawler) prima
di accettare come grounding un valore trovato in un file/stage diverso (qui: lo stage SEMANTIC,
livello run intero, non EXTRACT, livello per-fonte) solo perché la stringa letterale coincide.

**Addendum verificato 2026-09-15 (fix re-review):** la remediation applicata (opzione a
raccomandata) ha sostituito il letterale con `from gmv_crawler_extractor import STATUS_VALUES` +
`BLOCKED_EXTRACTION_STATUSES = frozenset(STATUS_VALUES - {"SUCCESS"})`, e il test di grounding è
stato riscritto per importare `STATUS_VALUES` indipendentemente e fare un confronto di insiemi
(`==`), non più una substring-match. Nessun import circolare introdotto (`gmv_evidence_pipeline.py`
non importa nulla del layer crawler). Corroborazione indipendente trovata durante la
ri-verifica: `gmv_crawler_candidate_extractor.py:231` già scrive
`"extraction_status": document.status` con `document` un `ExtractionDocument` reale — conferma che
quando un futuro step costruirà davvero un `SourceManifestEntry`, il valore naturale per
`extraction_status` erediterà lo stesso vocabolario `STATUS_VALUES`, quindi il gate ricostruito
scatterà correttamente, non è più dead code per costruzione. **Pattern di fix generalizzabile:**
quando una costante deve rispecchiare "tutti i valori di un vocabolario chiuso tranne uno/alcuni",
preferire sempre `frozenset(VOCABOLARIO_IMPORTATO - {eccezioni})` a un secondo letterale
enumerato a mano — è automaticamente drift-proof se il vocabolario sorgente cambia, ed è la
remediation concreta che ha chiuso questo blocker specifico.
