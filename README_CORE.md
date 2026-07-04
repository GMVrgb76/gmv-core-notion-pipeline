# GMV CORE — Mac mini local hard disk

Questo è il nucleo operativo locale del GMV Master System.

## Principio

Il Mac mini esegue.
Dropbox conserva, sincronizza e archivia.

## Cartelle

- 00_CONFIG: configurazioni, percorsi, regole operative.
- 01_RUNTIME: script, motori, funzioni esecutive.
- 02_INDEXES: indici locali generati dai materiali archiviati.
- 03_STATE: stato corrente di progetti, persone, immobili, opere, deal.
- 04_LOGS: log tecnici e giornalieri.
- 05_OUTPUT: report, morning brief, market report, snapshot.
- 06_CACHE: dati temporanei rigenerabili.
- 07_IMPORT: materiali in ingresso da classificare.
- 08_BACKUP_LOCAL: copie locali critiche.

## Regola

Nessuno script deve dipendere direttamente da Dropbox per funzionare.
Dropbox viene letto come archivio e aggiornato come destinazione di output/sync.

## Contratto di sviluppo

GMV Core supporta:

- CPython `3.14.x` (baseline verificata: `3.14.6`);
- SQLite `3.51.x` (baseline verificata: `3.51.0`);
- macOS sul Mac mini operativo.

Le versioni degli strumenti di sviluppo sono bloccate in `requirements-dev.txt`. Per creare l'ambiente locale riproducibile:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
python -m pip check
python -m build
```

Gli artefatti generati (`.venv`, `build`, `dist`, cache e metadata `egg-info`) non fanno parte del repository.

## Piano del console entrypoint

Il comando operativo rimane lo script `11_CLI/gmv`, attualmente esposto tramite il collegamento `$HOME/.local/bin/gmv`. S001-02 non modifica questo percorso né il comportamento della CLI.

Il target futuro del package Python è un console script equivalente a:

```toml
[project.scripts]
gmv = "gmv_core.cli:main"
```

L'entrypoint Python non sarà attivato finché il package `gmv_core`, i test di caratterizzazione della CLI e una migrazione con parità esplicita non saranno stati implementati in task approvati. Fino ad allora lo script Bash resta l'unico entrypoint autorevole.
