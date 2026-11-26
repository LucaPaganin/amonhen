---
id: TASK-101.2
title: Il pacchetto offline si scarica a richiesta
status: To Do
assignee: []
created_date: '2026-11-26T06:29:01Z'
labels: []
dependencies:
  - TASK-101.1
references:
  - desiderata-monitoring-finanziario.md
parent_task_id: TASK-101
type: feature
ordinal: 102000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seconda fetta della sezione 5.18: il pacchetto e le sezioni in sola lettura. Il telefono non ricalcola metriche né abbinamenti: porta con sé ciò che il server ha calcolato al momento del download.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Scarica per l'uso offline chiede un periodo e scarica i movimenti del periodo più l'intera coda da confermare, con postings, tag, nota, giroconto o split e i candidati di abbinamento, più categorie, tag e risposte del cruscotto
- [ ] #2 Il pacchetto sta in IndexedDB con l'ora del download, e lo spazio è chiesto come persistente
- [ ] #3 Senza rete Movimenti, Da confermare e Cruscotto leggono il pacchetto; il cruscotto dice l'ora a cui è congelato
- [ ] #4 Un nuovo download con operazioni ancora da inviare chiede prima di inviare o scartare; Cancella i dati offline toglie tutto
- [ ] #5 Test del payload del pacchetto contro un ledger di prova
<!-- AC:END -->
