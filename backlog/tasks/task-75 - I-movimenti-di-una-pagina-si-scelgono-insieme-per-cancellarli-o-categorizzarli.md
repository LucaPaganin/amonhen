---
id: TASK-75
title: I movimenti di una pagina si scelgono insieme per cancellarli o categorizzarli
status: Done
assignee: []
created_date: '2026-10-25 22:06'
labels: []
dependencies: []
ordinal: 74500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In Movimenti, Seleziona apre la scelta delle righe: un tocco sceglie, Seleziona tutti prende la pagina caricata, e una barra che resta in vista cancella o assegna una categoria a tutte.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Seleziona tutti prende tutti i movimenti caricati
- [x] #2 La cancellazione in blocco chiede conferma e lascia i movimenti nel cestino
- [x] #3 La categoria in blocco salta giroconti e movimenti divisi e lo dice
- [x] #4 Un id che non esiste più ferma tutto il blocco prima di scrivere
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
POST /api/transactions/delete (Ledger.delete_transactions, una transazione) e POST /api/transactions/category; barra .batch-bar in Movimenti.
<!-- SECTION:FINAL_SUMMARY:END -->
