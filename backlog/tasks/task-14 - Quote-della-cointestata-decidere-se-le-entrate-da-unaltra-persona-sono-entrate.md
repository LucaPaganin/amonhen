---
id: TASK-14
title: >-
  Quote della cointestata: decidere se le entrate da un'altra persona sono
  entrate
status: Done
assignee: []
created_date: '2026-09-13 10:05'
updated_date: '2026-09-13 15:05'
labels: []
dependencies: []
ordinal: 13500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Giugno 2026: 300,00 + 300,00 + 15,00 da From Chiara B sono la quota dell'altra intestataria del conto cointestato, e contano come Entrate (615,00 su 1.842,75 dopo la ricarica registrata come giroconto). Decisione di prodotto: trattarle come contributo fuori dalle Entrate (come i giroconti), come categoria a se', o lasciarle dove sono.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La quota dell'altra intestataria non è più un'entrata
- [x] #2 È dichiarata come tutto il resto: una destinazione e i testi dei mittenti, senza indovinare
- [x] #3 Il denaro resta visibile sul libro (una gamba sul conto virtuale) e la riga in Movimenti lo dice
- [x] #4 Un test che copre il caso al livello delle metriche mensili
- [x] #5 Specifica e documenti aggiornati nello stesso cambiamento
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La quota della cointestata è dichiarata come il resto del denaro non proprio: una destinazione e i testi dei mittenti, con incoming_only perché quei nomi non devono toccare il denaro che esce. Non è più un'entrata, resta sul libro col nome della destinazione, e un test lo fissa al livello delle metriche mensili.
<!-- SECTION:FINAL_SUMMARY:END -->
