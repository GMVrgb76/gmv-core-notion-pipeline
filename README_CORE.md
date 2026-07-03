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
