GMV VERSIONING

Versione: 1.0
Data: 2026-07-03
Stato: Fondativo

⸻

1. Scopo

Il presente documento definisce il modello di versionamento del GMV Framework, del GMV OS, del GMV Core e di tutti i componenti del sistema.

L’obiettivo è garantire evoluzione controllata, retrocompatibilità e tracciabilità.

⸻

2. Livelli di versionamento

Il sistema utilizza quattro livelli indipendenti.

GMV Framework
↓
GMV OS
↓
GMV Core
↓
Components

Ogni livello evolve autonomamente.

⸻

3. GMV Framework

Il Framework rappresenta il modello teorico.

Comprende:

* Manifesto
* Axioms
* Theory
* Physics
* Constitution

Una modifica del Framework implica una revisione concettuale del sistema.

⸻

4. GMV OS

Il GMV OS rappresenta l’implementazione del Framework.

Comprende:

* Core
* Services
* Plugins
* CLI
* API

Il sistema operativo può evolvere senza modificare il Framework.

⸻

5. GMV Core

Il Core evolve secondo le esigenze del sistema.

Comprende:

* database;
* Object System;
* OID;
* Timeline;
* Registry;
* API.

Ogni modifica del Core deve preservare la consistenza degli OID.

⸻

6. Components

Ogni componente possiede una propria versione.

Esempi:

* Knowledge Engine;
* Service Manager;
* Morning Brief;
* Market Engine;
* Importer.

⸻

7. Semantic Versioning

Il GMV OS adotta Semantic Versioning.

Formato:

MAJOR.MINOR.PATCH

⸻

8. Versione Major

Incrementata quando:

* cambia il Framework;
* cambia il modello dati;
* viene introdotta incompatibilità.

⸻

9. Versione Minor

Incrementata quando:

* vengono aggiunti Services;
* vengono introdotte nuove API;
* vengono aggiunti Plugin;
* vengono estese funzionalità esistenti mantenendo la compatibilità.

⸻

10. Versione Patch

Incrementata quando:

* vengono corretti bug;
* migliorano le prestazioni;
* vengono corrette implementazioni senza modificare il comportamento.

⸻

11. Schema Database

Il database possiede una versione indipendente.

Ogni modifica dello schema deve essere accompagnata da:

* numero di versione;
* script di migrazione;
* procedura di rollback.

⸻

12. Documenti

Ogni documento fondativo possiede:

* numero di versione;
* data;
* stato.

Stati ammessi:

* Draft
* Review
* Approved
* Deprecated
* Archived

⸻

13. Services

Ogni Service possiede:

* versione;
* data di rilascio;
* stato;
* livello di compatibilità.

⸻

14. Compatibility Layer

Il Compatibility Layer è temporaneo.

La sua rimozione costituisce una modifica Major.

⸻

15. Migrazioni

Ogni migrazione deve essere:

* documentata;
* riproducibile;
* reversibile quando possibile.

⸻

16. Retrocompatibilità

La retrocompatibilità è il comportamento predefinito.

Le incompatibilità devono essere esplicite e motivate.

⸻

17. Release

Ogni release del GMV OS deve produrre almeno:

* changelog;
* versione;
* stato del database;
* stato dei Services.

⸻

18. Snapshot

Ogni milestone significativa deve produrre uno snapshot completo del sistema.

Lo snapshot comprende:

* documentazione;
* database;
* configurazione;
* codice.

⸻

19. Evoluzione

Il Framework evolve lentamente.

Il GMV OS evolve regolarmente.

I Services evolvono frequentemente.

Questa separazione garantisce stabilità concettuale e agilità implementativa.

⸻

20. Definizione finale

Il versionamento del GMV OS garantisce che ogni modifica del sistema sia identificabile, documentata, riproducibile e compatibile con l’architettura del GMV Framework.