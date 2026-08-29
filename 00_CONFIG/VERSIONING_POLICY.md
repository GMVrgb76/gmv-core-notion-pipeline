# GMV CORE VERSIONING POLICY

Versione documento: 0.1
Data: 2026-07-02

## Principio

Le versioni maggiori del GMV Core devono essere rare.

Una versione maggiore cambia l'architettura.
Una versione minore aggiunge capacità.
Una patch corregge errori.

## Schema

Formato:

MAJOR.MINOR.PATCH

Esempio:

2.0.0

## Significato

MAJOR
- cambia architettura;
- modifica modello dati;
- introduce nuovo paradigma operativo.

MINOR
- aggiunge funzioni compatibili;
- introduce nuovi plugin;
- estende API o database.

PATCH
- corregge errori;
- migliora stabilità;
- modifica testi o configurazioni senza cambiare struttura.

## Versioni principali

V0
- concetto iniziale;
- esperimenti;
- strutture provvisorie.

V1
- sistema attuale;
- script;
- Dropbox come archivio operativo;
- Morning Brief, Daily Log, Market Engine base.

V2
- GMV Core;
- runtime locale;
- Object Architecture;
- OID;
- database SQLite;
- API;
- plugin;
- scheduler.

V3
- solo se necessario;
- agenti cooperanti;
- autonomia avanzata;
- orchestrazione multi-modello.

## Regola

La V2 deve essere considerata la versione storica e stabile del sistema.

Dopo V2, evitare nuove rivoluzioni architetturali salvo necessità reale.

## Stato corrente

Versione corrente: 2.0.0-alpha

Stato:
- Core locale creato.
- PATHS.env creato.
- GMV_CORE_ARCHITECTURE.md creato.
- Object Architecture in definizione.
- Database non ancora creato.
- API non ancora creata.
- Scheduler non ancora creato.
