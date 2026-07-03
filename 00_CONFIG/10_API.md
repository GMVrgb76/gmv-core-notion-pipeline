GMV API

Versione: 1.0
Data: 2026-07-03
Stato: Fondativo

⸻

1. Scopo

Le API del GMV Core costituiscono l’unico punto di accesso autorizzato alla conoscenza persistente del sistema.

Nessun Service, Plugin o componente esterno può leggere o modificare direttamente il database.

Ogni operazione deve transitare attraverso le API del Core.

⸻

2. Principio fondamentale

Le API rappresentano il contratto stabile tra il GMV Core e tutti i componenti del GMV OS.

L’implementazione interna del Core può evolvere.

Il contratto delle API deve rimanere stabile e versionato.

⸻

3. Responsabilità

Le API devono:

* validare ogni richiesta;
* garantire la consistenza del Core;
* gestire le transazioni;
* registrare gli eventi nella Timeline;
* impedire modifiche non autorizzate;
* mantenere la compatibilità tra le versioni.

⸻

4. Architettura

GMV OS
    │
    ▼
 Services / Plugins
    │
    ▼
   GMV API
    │
    ▼
 GMV Core
    │
    ▼
 GMV.db

Le API costituiscono l’unico percorso consentito verso il database.

⸻

5. Categorie

Le API sono suddivise in sei gruppi.

Identity API

Gestione degli OID.

Operazioni:

* create_oid
* resolve_oid
* validate_oid

⸻

Object API

Gestione degli Object.

Operazioni:

* create_object
* read_object
* update_object
* archive_object
* search_objects

⸻

Relation API

Gestione delle relazioni.

Operazioni:

* create_relation
* remove_relation
* list_relations
* validate_relation

⸻

Timeline API

Gestione degli eventi.

Operazioni:

* append_event
* list_events
* latest_event

⸻

Document API

Gestione delle fonti documentali.

Operazioni:

* attach_document
* detach_document
* list_documents

⸻

Service API

Gestione dei Services.

Operazioni:

* register_service
* run_service
* enable_service
* disable_service
* service_status

⸻

6. Regole

Ogni API deve essere:

* deterministica;
* idempotente quando applicabile;
* documentata;
* testabile;
* osservabile.

⸻

7. Transazioni

Ogni operazione di scrittura deve essere atomica.

Una transazione incompleta non deve lasciare il Core in stato inconsistente.

⸻

8. Logging

Ogni chiamata API deve produrre:

* timestamp;
* Service chiamante;
* operazione;
* esito;
* durata;
* eventuale errore.

⸻

9. Sicurezza

Le API devono impedire:

* modifica diretta del database;
* creazione di OID duplicati;
* relazioni non valide;
* scritture prive di tracciabilità.

⸻

10. Compatibilità

Le API devono mantenere la retrocompatibilità quando possibile.

Una modifica incompatibile richiede una nuova versione maggiore.

⸻

11. Evoluzione

Nuove API possono essere aggiunte.

Le API esistenti non devono cambiare comportamento senza una migrazione documentata.

⸻

12. Convenzioni

Le API utilizzano verbi espliciti.

Esempi:

create_object
update_object
append_event
register_service

Sono evitati nomi ambigui.

⸻

13. Errori

Ogni errore deve restituire:

* codice;
* descrizione;
* causa;
* suggerimento di recovery.

⸻

14. Test

Ogni API deve possedere almeno:

* test di successo;
* test di errore;
* test di integrità;
* test di regressione.

⸻

15. Definizione finale

Le API del GMV Core costituiscono il contratto permanente tra il Core e tutti i componenti del GMV OS.

Nessun componente accede direttamente alla persistenza.

Ogni operazione passa attraverso un’interfaccia stabile, verificabile e versionata.

Osservazione architetturale importante

Qui voglio fermarmi un istante perché emerge una conseguenza che non avevamo esplicitato.

Nel documento abbiamo scritto:

“Nessun Service può leggere o modificare direttamente il database.”

Questo implica una decisione tecnica significativa: gli script attuali (Morning Brief, Daily Log, Market Engine) sono ancora una soluzione di transizione. Oggi leggono e scrivono direttamente dove serve; nel modello definitivo dovranno passare attraverso le API del Core.

Questa distinzione è importante perché evita di considerare l’implementazione attuale come il modello finale. Il Compatibility Layer serve proprio ad accompagnare questa migrazione. Quando arriveremo a implementare realmente le API del Core, i Service verranno progressivamente adattati fino a non avere più accesso diretto al database o ad altre strutture persistenti. È una delle tappe principali che rimangono da realizzare.