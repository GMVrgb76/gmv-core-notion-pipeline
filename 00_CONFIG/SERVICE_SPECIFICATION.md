GMV SERVICE SPECIFICATION

Versione: 1.0
Data: 2026-07-03
Stato: Normativo

⸻

1. Scopo

Questo documento definisce il contratto tecnico minimo che ogni Service del GMV OS deve rispettare.

Un Service può essere nativo oppure compatibile con la V1. In entrambi i casi deve essere registrabile, eseguibile, osservabile, verificabile e riconducibile a uno o più OID.

⸻

2. Principio fondamentale

Ogni Service persistente deve essere rappresentato da un Object.

Di conseguenza ogni Service deve possedere un OID.

Il registro dei servizi non è una struttura separata dal sistema degli Object. È una vista sugli Object di tipo Service.

⸻

3. Contratto minimo

Ogni Service deve dichiarare:

service_oid:
service_name:
service_type:
category:
version:
status:
compatibility_mode:
entrypoint:
description:
inputs:
outputs:
reads:
writes:
requires:
produces:
oid_read:
oid_written:
timeline_events:
logging:
errors:
recovery:
scheduler:
cli:
tests:

⸻

4. Campi obbligatori

service_oid

Identificatore permanente del Service.

Esempio:

SRV-000001

service_name

Nome leggibile del Service.

service_type

Tipo generale.

Valori ammessi:

Service
Engine
Importer
Watcher
Scheduler
API
Compatibility
PluginService

category

Categoria funzionale.

Valori ammessi:

Core
Cognitive
Communication
Domain
Infrastructure
Compatibility
Importer
Scheduler
API
Plugin
Watcher

version

Versione del Service.

status

Stato operativo.

Valori ammessi:

active
pending
disabled
retired
legacy
error

compatibility_mode

0 = native
1 = compatibility

entrypoint

Comando o file di avvio.

⸻

5. Regole operative

Un Service deve:

1. leggere il Core come fonte della verità;
2. scrivere ogni esecuzione in engine_runs o nella futura tabella service_runs;
3. creare almeno un evento nella Timeline;
4. non conservare stato permanente fuori dal Core;
5. produrre log tecnici ispezionabili;
6. essere ri-eseguibile;
7. fallire in modo esplicito;
8. dichiarare input e output;
9. dichiarare gli OID letti e modificati;
10. essere sostituibile senza modificare il Core.

⸻

6. Logging

Ogni esecuzione deve generare:

* timestamp;
* Service OID;
* nome Service;
* stato finale;
* durata;
* comando eseguito;
* stdout;
* stderr;
* summary.

⸻

7. Timeline

Ogni Service deve scrivere almeno un evento nella Timeline.

Eventi ammessi:

service_registered
service_enabled
service_disabled
service_run
service_error
service_recovered
service_retired

⸻

8. Errori

Gli errori devono essere registrati senza interrompere la consistenza del Core.

Ogni errore deve contenere:

* Service OID;
* timestamp;
* codice errore;
* descrizione;
* log stderr;
* possibile recovery.

⸻

9. Compatibility Services

Un Compatibility Service incapsula un componente V1.

Regole:

1. non modifica lo script legacy se non necessario;
2. registra l’esecuzione nel Core;
3. conserva stdout e stderr;
4. permette rollback immediato;
5. deve essere sostituibile da un Service nativo.

⸻

10. Esempio — Knowledge Engine

service_oid: SRV-000001
service_name: Knowledge Engine
service_type: Engine
category: Cognitive
version: 0.1
status: active
compatibility_mode: 0
entrypoint: ~/.gmv_core/01_RUNTIME/knowledge_engine.py
description: Initializes and updates the structured knowledge layer.
inputs:
  - GMV.db
outputs:
  - engine_runs
  - timeline
  - knowledge report
reads:
  - ~/.gmv_core/09_DATABASE/GMV.db
writes:
  - objects
  - timeline
  - engine_runs
  - ~/.gmv_core/05_OUTPUT/knowledge_engine/
requires:
  - python3
  - sqlite3
produces:
  - persistent OID verification
  - execution report
oid_read:
  - PER-000001
oid_written:
  - PER-000001
  - SYS-000001
timeline_events:
  - service_run
logging:
  stdout: true
  stderr: true
  db_run_record: true
errors:
  - database_unavailable
  - schema_mismatch
recovery:
  - verify GMV.db
  - rerun service
scheduler:
  - manual
cli:
  - gmv service run knowledge
tests:
  - latest run status OK
  - timeline contains service_run

⸻

11. Esempio — Morning Brief Compatibility

service_oid: SRV-000002
service_name: Morning Brief
service_type: Compatibility
category: Communication
version: 1.x
status: active
compatibility_mode: 1
entrypoint: ~/.gmv_core/12_SCHEDULER/run_morning_brief_compatibility.sh
description: Runs existing Morning Brief through Compatibility Layer.
inputs:
  - legacy Morning Brief sources
outputs:
  - Morning Brief
  - engine_runs
  - timeline
  - stdout/stderr logs
reads:
  - ~/.gmv_scripts/genera_morning_brief.sh
  - Dropbox archive
writes:
  - GMV.db
  - ~/.gmv_core/05_OUTPUT/compatibility/
  - legacy Morning Brief output
requires:
  - gmv_compatibility.py
  - legacy script
produces:
  - morning brief
  - execution record
oid_read:
  - SYS-000001
oid_written:
  - SYS-000001
  - SRV-000002
timeline_events:
  - service_run
logging:
  stdout: true
  stderr: true
  db_run_record: true
errors:
  - legacy_script_failure
  - mail_failure
  - path_unavailable
recovery:
  - inspect stderr
  - rerun manually
scheduler:
  - LaunchAgent
cli:
  - gmv service run morning_brief
tests:
  - latest run status OK

⸻

12. Esempio — Daily Log Compatibility

service_oid: SRV-000003
service_name: Daily Log
service_type: Compatibility
category: Communication
version: 1.x
status: active
compatibility_mode: 1
entrypoint: ~/.gmv_core/12_SCHEDULER/run_daily_log_compatibility.sh
description: Runs existing Daily Log through Compatibility Layer.
inputs:
  - filesystem changes
  - Dropbox archive
outputs:
  - daily log
  - engine_runs
  - timeline
  - stdout/stderr logs
reads:
  - ~/.gmv_scripts/genera_daily_log.sh
  - Dropbox archive
writes:
  - GMV.db
  - ~/.gmv_core/05_OUTPUT/compatibility/
  - legacy Daily Log output
requires:
  - gmv_compatibility.py
  - legacy script
produces:
  - daily log
  - execution record
oid_read:
  - SYS-000001
oid_written:
  - SYS-000001
  - SRV-000003
timeline_events:
  - service_run
logging:
  stdout: true
  stderr: true
  db_run_record: true
errors:
  - legacy_script_failure
  - path_unavailable
recovery:
  - inspect stderr
  - rerun manually
scheduler:
  - LaunchAgent
cli:
  - gmv service run daily_log
tests:
  - latest run status OK

⸻

13. Esempio — Market Engine Compatibility

service_oid: SRV-000004
service_name: Market Engine
service_type: Compatibility
category: Domain
version: 1.x
status: active
compatibility_mode: 1
entrypoint: ~/.gmv_core/12_SCHEDULER/run_market_engine_compatibility.sh
description: Runs existing Real Estate Market Engine through Compatibility Layer.
inputs:
  - real estate source files
outputs:
  - market report
  - engine_runs
  - timeline
  - stdout/stderr logs
reads:
  - Dropbox real estate files
  - market_engine.py
writes:
  - GMV.db
  - ~/.gmv_core/05_OUTPUT/compatibility/
  - market legacy output
requires:
  - gmv_compatibility.py
  - market_engine.py
produces:
  - market report
  - execution record
oid_read:
  - SYS-000001
oid_written:
  - SYS-000001
  - SRV-000004
timeline_events:
  - service_run
logging:
  stdout: true
  stderr: true
  db_run_record: true
errors:
  - source_unavailable
  - legacy_script_failure
recovery:
  - inspect stderr
  - rerun manually
scheduler:
  - manual
cli:
  - gmv service run market
tests:
  - latest run status OK

⸻

14. Regola di ammissione

Nessun nuovo Service entra nel GMV OS senza:

1. OID;
2. contratto conforme;
3. entrypoint;
4. categoria;
5. stato;
6. log;
7. timeline event;
8. test minimo.

⸻

15. Definizione finale

Un Service conforme al GMV OS è un Object persistente dotato di OID, entrypoint, contratto operativo, tracciamento, logging, recovery e relazione esplicita con il Core.