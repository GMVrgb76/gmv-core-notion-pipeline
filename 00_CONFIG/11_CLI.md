GMV CLI

Versione: 1.0
Data: 2026-07-03
Stato: Fondativo

⸻

1. Scopo

La GMV Command Line Interface (CLI) costituisce l’interfaccia operativa primaria del GMV OS.

Essa fornisce un accesso uniforme, stabile e documentato a tutte le funzionalità del sistema.

La CLI rappresenta un’interfaccia verso il GMV Core, non un insieme di script indipendenti.

⸻

2. Principio fondamentale

Ogni operazione eseguibile nel GMV OS deve poter essere invocata tramite la CLI.

La CLI non implementa la logica applicativa.

La CLI delega l’esecuzione ai Services del GMV Core.

⸻

3. Architettura

Utente
   │
   ▼
GMV CLI
   │
   ▼
Service Manager
   │
   ▼
GMV Core
   │
   ▼
Services

La CLI non comunica direttamente con il database.

⸻

4. Comando principale

L’interfaccia principale del sistema è:

gmv

Tutte le funzionalità sono organizzate in sottocomandi.

⸻

5. Struttura generale

gmv
├── service
├── object
├── relation
├── timeline
├── plugin
├── import
├── search
├── backup
├── doctor
├── status
├── version
└── help

⸻

6. Service Commands

gmv service list
gmv service run <service>
gmv service enable <service>
gmv service disable <service>
gmv service status <service>
gmv service info <service>

⸻

7. Object Commands

gmv object create
gmv object show <OID>
gmv object update <OID>
gmv object archive <OID>
gmv object search

⸻

8. Relation Commands

gmv relation create
gmv relation remove
gmv relation show

⸻

9. Timeline Commands

gmv timeline show <OID>
gmv timeline latest
gmv timeline export

⸻

10. Plugin Commands

gmv plugin list
gmv plugin install
gmv plugin enable
gmv plugin disable

⸻

11. Import Commands

gmv import file
gmv import folder
gmv import watch

⸻

12. System Commands

gmv status
gmv doctor
gmv backup
gmv restore
gmv version

gmv status include, oltre ai controlli storici su database/queue/backup, un check
di sola lettura sulla pipeline evidence/Notion ("pipeline.evidence"): scandisce
`~/.gmv_core/03_STATE/evidence/<artist_slug>/` (override: `--evidence-roots-dir`)
cercando, per ciascuna sottocartella con un `index/FILE_INDEX.jsonl`, i file
scansionati, l'esito di estrazione (`cache/extracted/*.json`) e il manifest di
analisi (`semantic/analyze_manifest.json`). Non scrive mai nulla. Se non è ancora
stato eseguito alcun `gmv run`/`gmv evidence` per un dato artista, riporta PASS
(non è un errore, è lo stato atteso prima del primo run). Per questo motivo
`gmv run --evidence-root` dovrebbe puntare, per convenzione, sotto
`~/.gmv_core/03_STATE/evidence/<artist_slug>/`.

⸻

13. Output

La CLI deve produrre output leggibili sia da esseri umani sia da altri programmi.

Sono previsti almeno i formati:

* text
* json

Ogni comando deve poter essere esteso ad altri formati senza modificare il contratto.

⸻

14. Errori

Ogni errore deve essere espresso in modo deterministico.

Ogni comando deve restituire:

* codice di uscita;
* messaggio sintetico;
* dettaglio tecnico;
* eventuale suggerimento di recovery.

⸻

15. Estendibilità

L’aggiunta di un nuovo Service non deve richiedere modifiche strutturali alla CLI.

La CLI interroga il Service Manager per conoscere i servizi disponibili.

⸻

16. Stabilità

La sintassi dei comandi costituisce parte dell’interfaccia pubblica del GMV OS.

Le modifiche incompatibili richiedono una nuova versione maggiore.

⸻

17. Sicurezza

La CLI non deve consentire operazioni distruttive senza conferma esplicita o modalità dedicata.

Le operazioni di sola lettura devono essere sempre sicure.

⸻

18. Filosofia

La CLI privilegia:

* chiarezza;
* prevedibilità;
* coerenza;
* composabilità.

Ogni comando deve fare una sola cosa e farla in modo affidabile.

⸻

19. Definizione finale

La GMV CLI è l’interfaccia operativa ufficiale del GMV OS.

Essa fornisce un punto di accesso stabile, uniforme e indipendente dall’implementazione interna del sistema, delegando ogni operazione ai Services governati dal GMV Core.

Il prossimo documento sarà 12_VERSIONING.md. Continuerò con lo stesso metodo: comando di apertura seguito direttamente dal contenuto completo.