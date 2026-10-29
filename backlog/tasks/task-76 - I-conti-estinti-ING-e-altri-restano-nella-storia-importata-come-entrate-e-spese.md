---
id: TASK-76
title: >-
  I conti estinti (ING e altri) restano nella storia importata come entrate e
  spese
status: To Do
assignee: []
created_date: '2026-10-28 21:40'
labels: []
dependencies: []
ordinal: 75500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Lo storico importato da Revolut (dal 2025) e quello di Fineco contengono bonifici da e verso conti ormai chiusi: un conto ING chiuso all'apertura di Fineco, forse altri. Nel ledger quei conti non esistono, quindi i giroconti verso di loro non trovano l'altro lato e contano come entrate e spese, gonfiando le metriche a 24 mesi. Per ora lo storico Fineco si importa da quando Fineco esiste. Da decidere: aggiungere i conti estinti a mano con il loro estratto (se ancora scaricabile), dichiararli come destinazione di una regola di giroconto verso un conto virtuale, oppure far partire la storia dall'apertura di Fineco e lasciare fuori il periodo precedente.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Si sa quali conti estinti compaiono nello storico importato, con periodo e totale dei movimenti verso ciascuno
- [ ] #2 I giroconti verso un conto estinto non contano né come entrate né come spese
- [ ] #3 La scelta fatta per i conti estinti è scritta nella specifica
<!-- AC:END -->
