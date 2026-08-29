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
