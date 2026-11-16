---
id: TASK-97
title: La distribuzione dai rendimenti storici
status: To Do
assignee: []
created_date: '2026-11-16T20:18:00Z'
labels: []
dependencies:
  - TASK-94
references:
  - desiderata-monitoring-finanziario.md
  - docs/investments.md
type: feature
ordinal: 97000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sesta fetta della fase 12 (sezione 5.16): tre scenari nascondono che conta l'ordine dei rendimenti, e un crollo vicino all'obiettivo pesa più di uno lontano. La proiezione si ripete su molte traiettorie con rendimenti mensili reali estratti dallo storico, senza ipotesi gaussiana. Arriva dopo gli scenari, che ne sono il controllo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Bootstrap a blocchi di 12 mesi sui rendimenti mensili reali di un indice azionario globale deflazionato, caricato una volta da file
- [ ] #2 Il risultato si legge come percentili, e si dichiara come distribuzione del passato, non come stima
- [ ] #3 Il generatore ha un seme mostrato accanto al risultato, così una cifra si riproduce
- [ ] #4 Un test verifica che la mediana stia vicina allo scenario centrale con gli stessi rendimenti medi
<!-- AC:END -->
