GMV OBJECT SYSTEM

Versione: 1.0
Data: 2026-07-03
Stato: Fondativo

⸻

1. Scopo

Il presente documento definisce il modello universale degli Object del GMV Core.

L’Object è l’unità fondamentale della rappresentazione della realtà nel GMV OS.

Ogni entità persistente è rappresentata come un Object identificato da un OID.

⸻

2. Principio fondamentale

Il GMV Core non memorizza file.

Non memorizza persone.

Non memorizza servizi.

Il GMV Core memorizza esclusivamente Object.

Ogni altra classificazione deriva dagli attributi dell’Object.

⸻

3. Universal Object Principle

Qualunque elemento che soddisfi almeno una delle seguenti condizioni deve essere rappresentato come Object:

* possiede identità;
* può essere referenziato;
* può partecipare a relazioni;
* può evolvere nel tempo;
* possiede una storia;
* deve essere ricercabile;
* deve essere documentato.

⸻

4. OID

Ogni Object possiede un OID permanente.

L’OID:

* non cambia;
* non viene riutilizzato;
* identifica un solo Object;
* rimane valido per tutta la vita del sistema.

⸻

5. Proprietà minime

Ogni Object possiede almeno:

* OID
* Type
* Name
* Status
* Created At
* Updated At

Queste proprietà costituiscono l’identità minima.

⸻

6. Struttura logica

Ogni Object è composto da:

OID
│
├── Identity
├── Attributes
├── Relations
├── Timeline
├── Documents
├── State
├── Metadata
└── Metrics

Ogni sezione è indipendente ma riferita allo stesso OID.

⸻

7. Identity

L’identità rappresenta ciò che rende l’Object univoco.

L’identità non viene modificata.

Può essere estesa.

Non può essere sostituita.

⸻

8. Attributes

Gli attributi descrivono l’Object.

Sono modificabili.

Possono aumentare nel tempo.

Non alterano l’identità.

⸻

9. Relations

Ogni Object può possedere relazioni.

Le relazioni sono esplicite.

Una relazione collega sempre due OID.

Le relazioni non utilizzano nomi.

Utilizzano esclusivamente identificatori.

⸻

10. Timeline

Ogni Object possiede una Timeline.

La Timeline è append-only.

Ogni evento è permanente.

Gli eventi non vengono cancellati.

Possono essere corretti mediante nuovi eventi.

⸻

11. Documents

Ogni Object può essere collegato a uno o più documenti.

I documenti non rappresentano l’Object.

Sono fonti che descrivono l’Object.

⸻

12. State

Lo State rappresenta la situazione corrente.

È una vista derivata.

Non sostituisce la Timeline.

⸻

13. Metadata

I Metadata descrivono la qualità dell’Object.

Esempi:

* livello di completezza;
* affidabilità;
* origine;
* autore dell’informazione;
* data di aggiornamento.

⸻

14. Metrics

Le Metriche rappresentano informazioni quantitative.

Esempi:

* confidence;
* completeness;
* popularity;
* importance;
* activity score.

⸻

15. Tipi di Object

Il tipo identifica la natura dell’Object.

Tipi iniziali:

* Person
* Organization
* Artwork
* Building
* Property
* Collection
* Project
* Event
* Document
* Service
* Plugin
* Company
* Institution
* Place
* Concept
* Task
* Deal
* Contact
* Asset

L’elenco è estendibile.

⸻

16. Nessun privilegio

Nessun tipo possiede privilegi speciali.

Un Service è un Object.

Un Plugin è un Object.

Una Persona è un Object.

Un Documento è un Object.

Il comportamento deriva dagli attributi e dalle relazioni.

⸻

17. Ricerca

Ogni ricerca nel GMV Core parte dagli Object.

I filtri vengono applicati su:

* Type;
* Attributes;
* Relations;
* Timeline;
* Metadata.

⸻

18. Evoluzione

Gli Object possono acquisire:

* nuovi attributi;
* nuove relazioni;
* nuovi documenti;
* nuovi eventi.

L’OID rimane invariato.

⸻

19. Eliminazione

Un Object non viene eliminato.

Può essere:

* archiviato;
* ritirato;
* marcato come inattivo.

L’identità rimane preservata.

⸻

20. Oggetti di sistema

Anche i componenti interni del GMV OS sono Object.

Esempi:

* Knowledge Engine
* Morning Brief
* Daily Log
* Market Engine
* Compatibility Layer
* GMV Core

Questo consente di documentarne la storia, le relazioni e l’evoluzione con gli stessi strumenti utilizzati per qualsiasi altra entità.

⸻

21. Regole fondamentali

Ogni Object deve:

1. possedere un OID;
2. appartenere a un Type;
3. poter essere referenziato;
4. possedere una Timeline;
5. essere ricercabile;
6. poter essere documentato;
7. poter essere esteso senza cambiare identità.

⸻

22. Definizione finale

Un Object è la rappresentazione persistente e universale di un’entità del GMV OS.

Ogni Object è identificato da un OID permanente, descritto da attributi, collegato ad altri Object mediante relazioni, documentato da fonti, evoluto attraverso una Timeline e gestito dal GMV Core.

L’Object costituisce l’unità fondamentale attraverso la quale il GMV OS rappresenta la realtà.

Questo documento chiude il modello dati fondamentale del GMV Core. Da questo punto in poi, i documenti successivi (API, CLI, Versioning) descriveranno il funzionamento del sistema costruito su questi principi, non introdurranno nuovi concetti fondamentali.