---
id: TASK-85
title: Salvare una regola non rilegge tutto il ledger per ogni movimento
status: Done
assignee: []
created_date: '2026-10-31 23:30'
updated_date: '2026-10-31 23:30'
labels: []
dependencies: []
type: bug
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Salvare una regola era lento perché `postings` non aveva un indice su `transaction_id`: la lettura dei movimenti scorreva l'intera tabella tre volte per ogni movimento, e un salvataggio la esegue più volte.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 I lati di un movimento e la sua coppia si trovano con un indice
- [x] #2 Un ledger esistente riceve gli indici all'avvio, senza altre migrazioni
- [x] #3 Il conteggio delle regole legge i movimenti una volta sola
- [x] #4 All'avvio il sync non si scontra con la migrazione delle regole
<!-- AC:END -->
