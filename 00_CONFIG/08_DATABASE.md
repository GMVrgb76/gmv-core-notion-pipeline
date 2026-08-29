GMV DATABASE

Versione: 1.0
Data: 2026-07-03
Stato: Fondativo

⸻

1. Scopo

GMV.db è il database centrale del GMV Core.

Rappresenta l’unica fonte della verità persistente del sistema.

Nessun Service può considerare un file, una cache o una memoria temporanea come fonte primaria della verità.

⸻

2. Principio fondamentale

Il database non è un archivio di file.

È una rappresentazione strutturata della realtà osservata dal GMV OS.

I file sono documenti.

Il database contiene conoscenza strutturata.

⸻

3. Obiettivi

Il database deve garantire:

* persistenza;
* consistenza;
* integrità;
* tracciabilità;
* ricostruibilità;
* indipendenza dal modello AI utilizzato.

⸻

4. Fonte della verità

Il GMV Core utilizza esclusivamente GMV.db come fonte primaria della conoscenza strutturata.

Sono considerate copie o derivazioni:

* file Markdown;
* report;
* output;
* cache;
* documenti esportati.

⸻

5. Persistenza

Ogni informazione persistente deve essere registrata nel database oppure essere raggiungibile tramite un OID presente nel database.

Nessuna informazione critica deve vivere esclusivamente in memoria.

⸻

6. Identità

Ogni entità persistente possiede un OID.

L’OID non cambia mai.

L’OID rappresenta l’identità permanente dell’entità.

⸻

7. Object

Ogni OID identifica un Object.

Gli Object rappresentano qualsiasi elemento persistente del sistema.

Esempi:

* Persona
* Organizzazione
* Opera
* Immobile
* Documento
* Evento
* Service
* Plugin

⸻

8. Timeline

Ogni Object possiede una Timeline.

La Timeline è append-only.

Gli eventi storici non vengono modificati.

Possono solamente essere integrati.

⸻

9. Stato

Lo stato corrente di un Object è derivato dalla Timeline e dagli attributi persistenti.

Lo stato non sostituisce la storia.

⸻

10. Tabelle fondamentali

Le tabelle permanenti previste sono:

objects
attributes
relations
timeline
documents
services
service_runs
plugins
tags
sources

Queste rappresentano il modello logico del GMV Core.

⸻

11. Tabelle transitorie

Durante la migrazione possono esistere tabelle temporanee.

Esempi:

engines
engine_runs
compatibility
migration

Queste tabelle sono considerate provvisorie.

Quando il modello definitivo sarà completo, verranno migrate verso il modello Object.

⸻

12. Regola di migrazione

Ogni migrazione deve soddisfare tre condizioni:

1. nessuna perdita di dati;
2. OID invariati;
3. cronologia preservata.

⸻

13. Compatibilità

Il Compatibility Layer può leggere strutture legacy.

Può trasformarle.

Può registrarle nel Core.

Non deve alterare direttamente gli archivi legacy.

⸻

14. Integrità

Ogni relazione deve essere verificabile.

Ogni Object deve essere raggiungibile.

Ogni riferimento deve puntare a un OID valido.

⸻

15. Versione dello schema

Il database possiede una versione dello schema.

Ogni modifica deve incrementare la versione.

Le migrazioni devono essere riproducibili.

⸻

16. Backup

Il database deve poter essere salvato integralmente.

Un backup deve consentire il ripristino completo del GMV Core.

⸻

17. Ricostruibilità

Partendo esclusivamente da:

* GMV.db;
* documenti collegati;
* repository del GMV OS;

deve essere possibile ricostruire l’intero sistema.

⸻

18. Indipendenza

GMV.db non dipende da:

* ChatGPT;
* Claude;
* Gemini;
* modelli locali;
* API esterne.

I modelli AI interrogano il database.

Il database non appartiene ai modelli.

⸻

19. Evoluzione

Il database deve poter evolvere senza modificare i principi fondamentali del GMV Core.

Nuove tabelle possono essere introdotte.

Gli assiomi non cambiano.

⸻

20. Definizione finale

GMV.db è il nucleo persistente del GMV Core.

Custodisce identità, relazioni, eventi e conoscenza strutturata.

Tutti i Services operano attraverso di esso.

Nessun Service possiede una propria verità persistente.

La verità del sistema appartiene esclusivamente al GMV Core.