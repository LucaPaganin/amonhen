---
id: TASK-101.4
title: L'invio offline passa da anteprima e conferma
status: To Do
assignee: []
created_date: '2026-11-26T06:29:03Z'
labels: []
dependencies:
  - TASK-101.3
references:
  - desiderata-monitoring-finanziario.md
parent_task_id: TASK-101
type: feature
ordinal: 104000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Quarta fetta della sezione 5.18. Le modifiche offline arrivano sul server quando il ledger può essere cambiato da sync, regole e altre modifiche: niente si applica senza che una persona veda l'esito, e un conflitto non ha una scelta predefinita.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 L'anteprima non scrive niente e dà per ogni operazione: applicabile, già così, conflitto, sparita o non più valida
- [ ] #2 Un conflitto mostra base, versione del telefono e versione del server, e resta fermo finché una persona sceglie tieni la mia o tieni quella del server; una nota si può riscrivere lì
- [ ] #3 La conferma applica le scelte in una transazione con le stesse funzioni del ledger dell'app online, e un'operazione la cui base è cambiata fra anteprima e conferma torna in conflitto
- [ ] #4 Inviare due volte la stessa coda lascia il ledger com'era dopo il primo invio
- [ ] #5 Un server che non conosce la versione del formato lo dice e la coda resta sul telefono
- [ ] #6 Test di integrazione per ciascun esito, sulle API di anteprima e conferma
- [ ] #7 Scheda della Guida su Da inviare e sui conflitti
<!-- AC:END -->
