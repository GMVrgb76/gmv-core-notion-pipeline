# GMV Remediator v0.1 — Contratto tecnico per Claude Code

## Contesto operativo

Claude Code, questo componente deve essere sviluppato come prosecuzione diretta del lavoro già svolto sul sistema GMV Core.
Ricorda che i due componenti precedenti della pipeline sono stati sviluppati da te:

1. **GMV Auditor**
   Componente responsabile dell'analisi del corpus, dell'identificazione delle anomalie e della produzione degli output di controllo.
2. **GMV Audit Report / Issue System**
   Componente responsabile della formalizzazione dei problemi rilevati attraverso report strutturati (`issues.json` o formato equivalente).

Il Remediator deve quindi essere sviluppato mantenendo continuità con:

* struttura del codice esistente;
* convenzioni già adottate;
* formati dati già prodotti;
* logica di separazione tra controllo, decisione ed esecuzione.

Non è richiesta una riscrittura dei componenti precedenti.
Prima dello sviluppo deve essere verificata la compatibilità con l'architettura esistente.

## 1. Scopo

GMV Remediator è un componente operativo destinato a ricevere gli output dell'Auditor e trasformarli in azioni di correzione controllate.
Il Remediator non sostituisce l'Auditor.

Responsabilità:

* Auditor → individua anomalie.
* Remediator → interpreta le anomalie secondo regole definite e genera azioni consentite.
* Validazione → verifica che la correzione abbia risolto il problema.

## 2. Principio fondamentale

Il Remediator non deve creare nuova conoscenza.

Può:

* correggere incoerenze deterministiche;
* applicare trasformazioni logiche;
* generare piani di intervento;
* creare richieste di ricerca;
* produrre code operative.

Non può:

* inventare dati mancanti;
* completare informazioni non supportate;
* modificare contenuti curatoriali senza fonte;
* sostituire decisioni umane.

## 3. Input

Il Remediator riceve come input esclusivamente gli output dell'Auditor.

Input principale:

```
issues.json
```

Il Remediator non deve autonomamente reinterpretare il corpus per decidere cosa modificare.
L'Auditor rimane la fonte della diagnosi.

## 4. Output obbligatori

Il Remediator deve produrre:

**Piano di intervento**

Contiene:

* issue originale;
* entità coinvolta;
* campo interessato;
* azione proposta;
* livello di autorizzazione richiesto.

**Log operativo**

Ogni azione deve essere registrata:

* modifica proposta o eseguita;
* motivazione;
* regola applicata;
* timestamp;
* risultato.

## 5. Classificazione delle azioni

Ogni issue deve essere classificata.

**AUTO_FIX**
Correzione deterministica.
Consentita solo quando:

* la regola è esplicita;
* non viene introdotta nuova informazione;
* l'azione è verificabile.

**RESEARCH_REQUIRED**
Il problema richiede recupero di evidenza.
Il Remediator deve generare una richiesta di ricerca, non modificare il dato.

**HUMAN_DECISION**
Il problema richiede valutazione umana.
Esempi:

* testo curatoriale incompleto;
* placeholder;
* interpretazioni;
* decisioni editoriali.

**SCHEMA_CHANGE**
Il problema riguarda la struttura del modello dati.
Richiede approvazione preventiva.

## 6. Regola di scrittura

Nessuna modifica al corpus è consentita senza:

* trasformazione deterministica;

oppure

* fonte verificabile;

oppure

* approvazione esplicita.

Ogni modifica deve rispondere alla domanda:
**Perché questo valore è stato modificato?**

## 7. Separazione delle responsabilità

Devono rimanere separati:

**Auditor**
Responsabile di:

* analisi;
* rilevazione;
* classificazione dei problemi.

**Remediator**
Responsabile di:

* piano di correzione;
* applicazione delle regole;
* tracciamento.

**Operatore umano**
Responsabile di:

* decisioni curatoriale;
* approvazioni;
* validazione dei contenuti.

## 8. Vincolo di non regressione

Ogni intervento deve essere seguito da una nuova esecuzione dell'Auditor.

Una correzione è valida solo se:

* l'errore originale scompare;
* non vengono introdotti nuovi errori;
* la struttura rimane conforme.

## 9. Modalità operative

Devono esistere almeno due modalità.

**Analisi**
Nessuna modifica.
Produce:

* classificazione;
* piano;
* rischio.

**Applicazione**
Esegue esclusivamente azioni autorizzate.

## 10. Conservazione della provenienza

Ogni modifica deve mantenere:

* stato precedente;
* stato successivo;
* motivazione;
* fonte o regola utilizzata;
* autore del cambiamento.

Il sistema deve permettere la ricostruzione completa della storia.

## 11. Limiti

GMV Remediator non è:

* un agente autonomo;
* un sistema curatoriale;
* un generatore automatico di contenuti;
* un sostituto dell'archivista;
* un sistema decisionale indipendente.

È un sistema di controllo, classificazione e applicazione di regole.

## 12. Obiettivo finale

Il Remediator sarà conforme quando sarà possibile eseguire il ciclo:

```
AUDITOR
   ↓
issues.json
   ↓
REMEDIATOR
   ↓
piano interventi
   ↓
azioni autorizzate
   ↓
validazione
   ↓
nuovo AUDIT
```

senza perdita di tracciabilità e senza introduzione di conoscenza non verificata.

## Istruzione finale per Claude Code

Prima di implementare:

1. analizza il codice esistente dei due componenti precedenti;
2. verifica i formati dati realmente prodotti;
3. identifica i punti di integrazione corretti;
4. non modificare l'Auditor salvo necessità documentata;
5. proponi eventuali modifiche prima di applicarle.

Il Remediator deve essere una naturale estensione del sistema GMV Core già costruito, non un nuovo sistema separato.
