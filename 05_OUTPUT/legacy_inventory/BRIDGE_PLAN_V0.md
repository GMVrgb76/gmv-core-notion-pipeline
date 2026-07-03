# BRIDGE PLAN V0

## Obiettivo

Collegare progressivamente gli engine V1 ancora utili a GMV.db senza riscriverli.

## Principio

Nessun componente funzionante viene riscritto se può essere incapsulato.

## Primo gruppo BRIDGE

1. Morning Brief
2. Daily Log
3. Market Engine
4. LaunchAgent Morning Brief
5. LaunchAgent Daily Log

## Esclusioni temporanee

Apprentice non viene bridgiato.
Verrà assorbito nel Knowledge Engine.

## Regola di migrazione

Ogni engine deve:

1. continuare a produrre il proprio output V1;
2. registrare una riga in GMV.db;
3. scrivere un evento nella timeline;
4. non dipendere da Dropbox per l'esecuzione;
5. leggere PATHS.env dove possibile.

## Stato

V0 pronta.
