# Area35 Archive — validatore QA (grounded su schema reale + monade v1.0)

Validatore delle schede Notion di Area35 in vista della proiezione verso **monade**
(`.md`, `GMV_KNOWLEDGE_MONAD_SPEC_v1.0`). Ricostruito il 2026-08-14 leggendo via API
i sei data source reali e la SPEC canonica.

**Limite dichiarato.** Verifica struttura, integrità referenziale, coerenza temporale
(object-time), risolvibilità della fonte, disciplina epistemica dello stato e coerenza
del gate di pubblicazione (SPEC §14). *Non* verifica la verità dei fatti: misura il
rischio di errore, non l'errore.

---

## Stato ricostruito — sei data source (non quattro)

| Entità | data source | titolo | campo Stato (opzioni) | data verifica | campo-fonte | Pubblicabile | Riservatezza |
|---|---|---|---|---|---|---|---|
| ARTISTI | `26def72b` | Nome | Stato scheda (Completa/Parziale/Da verificare) | — | **nessuno** | sì | — |
| MOSTRE | `843880d1` | Titolo | Stato **archivio** (Completo/Parziale/Da verificare) | — | Fonte Dropbox | sì | — |
| PERSONE | `d265f55e` | Nome completo | Stato scheda (Da verificare/Verificata/Archiviata) | Ultima verifica | Riferimento esterno | — | — |
| ISTITUZIONI | `14179b86` | Nome | Stato scheda (Da verificare/Verificata/Archiviata) | Ultima verifica | Sito ufficiale | sì | — |
| OPERE | `2681e72c` | Titolo | Stato scheda (Completa/Parziale/Da verificare) | — | Fonte Dropbox | sì | — |
| SPONSOR | `d62c2764` | Titolo | Stato scheda (Da verificare/Parziale/Verificata/Archiviata) | Ultima verifica | Fonte primaria | sì | Pubblico/Interno/Confidenziale |

Grafo relazionale denso e per lo più duale tra tutte le entità. Le biografie e i testi
critici vivono **nel corpo delle pagine**, non nelle property.

## Quattro incoerenze strutturali verificate

1. **Asse di stato con 4 vocabolari** e due nomi di campo diversi (`Stato scheda` vs
   `Stato archivio`). Nessun consumatore a valle può leggere un unico asse epistemico.
2. **Campo-fonte con 4 nomi diversi** (`Fonte Dropbox`, `Riferimento esterno`,
   `Sito ufficiale`, `Fonte primaria`) — e **ARTISTI senza alcun campo-fonte**. Solo
   `Fonte Dropbox` punta a SUM; gli altri sono URL esterni, epistemicamente più deboli.
3. **Data di verifica** solo in PERSONE/ISTITUZIONI/SPONSOR. Su ARTISTI/MOSTRE/OPERE
   l'obsolescenza non è misurabile.
4. **Gate `Pubblicabile`** assente in PERSONE; `Riservatezza` + dati economici solo in
   SPONSOR (rilevanti per l'esclusione PUBLIC §14).

## Mappatura Notion → monade

La distinzione portante della SPEC è che **completezza editoriale ≠ validità epistemica**.
`Completa/Completo/Parziale` dicono che la *scheda* è piena, non che i *fatti* sono
verificati. Solo `Verificata` mappa su `VALID`; tutto il resto su `UNVERIFIED`;
`Archiviata` su `SUPERSEDED`. Questa mappa è in `config.json → mappa_stato_epistemico`.

La regola costituzionale `ATOM → SOURCE_ID → canonical source in SUM` diventa, al livello
Notion, la risolvibilità del campo-fonte; le esclusioni PUBLIC (§14) diventano il gate
`Pubblicabile`.

## Catalogo regole (famiglia M = monade)

| Cod | Sev | Controllo |
|---|---|---|
| S01/S02/S03 | B/m | Campi obbligatori, tipi (data/anno/intero) |
| R01–R04 | B–M | Relazioni obbligatorie, riferimenti non risolti, asimmetrie, record isolati |
| T01–T05 | B–m | Fine < inizio; mostra vs nascita artista; anni implausibili |
| **M01** | MAJOR | Entità senza campo-fonte: schede non ancorabili a SUM (difetto di schema) |
| **M02** | MAJOR | Campo-fonte presente ma vuoto: scheda non risolvibile verso evidenza |
| **M03** | INFO | Fonte è URL esterno, non locator Dropbox/SUM |
| **M04** | MAJOR | Stato non impostato o non mappabile: nessun segnale epistemico |
| **M06** | MINOR | 'Verificata' senza data, o verifica obsoleta |
| **M07** | MAJOR | `Pubblicabile` ma stato non-VALID, o senza fonte risolvibile (§14) |
| **M08** | BLOCKER | `Pubblicabile` con Riservatezza confidenziale o dato economico privato (§14) |
| Q01–Q08 | B–m | Residui di lavorazione, troncamenti, registro promozionale, stilemi generativi, vaghezza non ancorata, boilerplate |
| D01/D02 | B/M | Chiave duplicata, varianti di denominazione |
| N01/N03/N04 | M/m | Incoerenze trasversali di schema (stato, fonte, entità senza fonte) — emesse una volta |

## Uso

```bash
python3 area35_validator.py --config config.json --rows rows.json --out report
```

`rows.json` è la forma normalizzata `{entita: [ {id, titolo, campi, relazioni, servizio, corpo} ]}`.
Va prodotto da un adattatore che legge Notion — via SQL (`query_data_sources`) o REST col
token dell'integrazione. Nota: le regole di testo (Q) richiedono `corpo` = corpo pagina;
sui soli valori-proprietà restano in gran parte inerti.

Exit code `1` se esiste almeno un BLOCKER → utilizzabile come gate prima dell'export monade.

## Estrattore Notion e launcher

`notion_extract.py` interroga i sei data source indicati in `config.json` e produce
`rows.json` nel contratto normalizzato: `id` e relazioni sono URL Notion, le proprietà
editoriali sono in `campi`, i metadati in `servizio`, le fonti usano
`fonte::<Nome property>`, la fine mostra è `servizio.data_end` e il testo pagina è
`corpo`. L'estrattore usa soltanto la libreria standard Python e non scrive su Notion.

Il token viene risolto in modo unico da `credentials.get_token()` (env → file → errore
esplicito): prima la variabile d'ambiente `NOTION_TOKEN`, poi il file locale
`~/.config/area35-qa/notion_token` (o quello indicato con `--token-file`). Se nessuna
sorgente lo fornisce lo script termina con errore esplicito. La sorgente effettivamente
usata è riportata su stderr (`[info] token Notion letto da env|file`); il token non
viene mai stampato né incluso nei report. Lo stesso helper è usato da `adapter_notion.py`.

Esecuzione su fixture o `rows.json` già disponibile:

```bash
./run_area35_qa.sh --rows test_rows.json --out report
```

Estrazione limitata per collaudo e validazione:

```bash
./run_area35_qa.sh --extract --token-file ~/.config/area35-qa/notion_token \
  --limit 2 --entities artista,mostra
```

L'export verso monade resta separato e non viene eseguito dal launcher.

## Pipeline operativa con Run Ledger

`gmv_pipeline.py` esegue estrazione/ingest, audit, piano di remediation e
finalizzazione dentro un Run immutabile e verificabile. Non modifica Notion,
non applica remediation e non esporta verso monade. Il ledger predefinito è
`~/.gmv_core/runs`; può essere sostituito con `--ledger-root`.

Esecuzione su un file normalizzato già disponibile:

```bash
python3 gmv_pipeline.py --rows rows.json --config config.json
```

Esecuzione con estrazione Notion read-only:

```bash
python3 gmv_pipeline.py --extract --config config.json \
  --token-file ~/.config/area35-qa/notion_token
```

Codici di uscita:

- `0`: pipeline completata, nessun BLOCKER;
- `1`: pipeline completata, gate BLOCKER attivo;
- `2`: errore operativo della pipeline.

Ogni Run contiene `run_manifest.json`, `events.jsonl`, `run_state.json`, log e
artefatti con hash SHA-256. Un Run terminato non resta in `_active`.

Per classificare Run abbandonati e verificare i checkpoint:

```bash
python3 gmv_recovery.py
python3 gmv_recovery.py --run-id GMV-YYYYMMDDTHHMMSSZ-XXXX
```

Il recovery è deliberatamente solo ispettivo: segnala il punto di ripresa ma
non rilancia automaticamente la pipeline. Un ledger corrotto o un Run
inesistente produce exit `2` e `DO_NOT_RESUME`.

Verifica locale:

```bash
python3 -m unittest discover -s tests -v
ruff check gmv_run_ledger.py gmv_pipeline.py gmv_recovery.py tests
```

Le correzioni del draft e i gap intenzionalmente non implementati sono
documentati in `CORRECTIONS.md`.
