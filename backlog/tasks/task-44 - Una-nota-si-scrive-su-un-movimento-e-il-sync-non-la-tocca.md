---
id: TASK-44
title: Una nota si scrive su un movimento e il sync non la tocca
status: Done
assignee: []
created_date: '2026-09-24 18:38'
updated_date: '2026-09-24 19:07'
labels: []
dependencies: []
references:
  - amonhen/db.py
  - amonhen/ledger.py
  - amonhen/api.py
  - web/src/screens/Movements.tsx
documentation:
  - doc-1
type: feature
ordinal: 43500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Serve un posto per annotare un movimento senza toccare cio che la banca ha dichiarato: un `notes` locale, scritto a mano, che sopravvive a ogni sync e che il ledger non usa per nessun calcolo. Oggi l'unica annotazione e `postings.note`, che e un'altra cosa (una gamba, non il movimento) e che il sync riscrive. Decisione presa: la nota sta sulla riga del movimento, il sync non la nomina mai, e una copia nel tombstone la fa tornare se il movimento viene reimportato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `transactions.notes` esiste, con migrazione su un ledger scritto prima (colonna aggiunta, righe esistenti invariate)
- [x] #2 `PUT /api/transactions/{id}/notes` scrive o cancella la nota (stringa vuota = nessuna nota) e risponde con il movimento aggiornato; un id inesistente e 404
- [x] #3 Nessun altro campo e scrivibile da questo percorso: il corpo porta solo `notes`
- [x] #4 Una promozione PDNG->BOOK e ogni sync successivo lasciano la nota intatta, anche quando la banca riscrive data, descrizione o identificativo della stessa riga
- [x] #5 La nota si legge e si scrive dal foglio del movimento (Movimenti e coda), e `search` la trova oltre a descrizione e controparte
- [x] #6 La specifica dice che `notes` e un campo locale del ledger (§6) e la versione dell'API sale
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. db.py: notes TEXT nel CREATE TABLE transactions e in _ADDED_COLUMNS (la migrazione guarda PRAGMA table_info, quindi un ledger esistente prende la colonna).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Schema: notes TEXT nel CREATE TABLE transactions piu la voce in _ADDED_COLUMNS (un ledger esistente la prende dall'ALTER, un database nuovo dalla SCHEMA). Ledger.set_notes scrive o azzera (spazi via, stringa vuota = NULL, id inesistente = KeyError). API: PUT /api/transactions/{id}/notes, notes nel payload di _transaction (quindi anche nella coda), search che guarda anche le note; API_VERSION 12 -> 13.
<!-- SECTION:NOTES:END -->
