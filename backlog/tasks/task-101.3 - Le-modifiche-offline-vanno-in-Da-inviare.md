---
id: TASK-101.3
title: Le modifiche offline vanno in Da inviare
status: To Do
assignee: []
created_date: '2026-11-26T06:29:02Z'
labels: []
dependencies:
  - TASK-101.2
references:
  - desiderata-monitoring-finanziario.md
parent_task_id: TASK-101
type: feature
ordinal: 103000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Terza fetta della sezione 5.18. Ogni modifica fatta senza rete deve poter essere confrontata dopo con lo stato del server, quindi porta con sé la base che aveva il pacchetto: è così che si riconosce un conflitto senza aggiungere colonne di versione al ledger.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Offline si cambiano categoria e split, tag, nota, si cancella un movimento, si abbina un giroconto a un candidato scaricato, si conferma o rifiuta un abbinamento proposto
- [ ] #2 Ogni operazione entra in Da inviare con la sua base; i tag come aggiunte e rimozioni
- [ ] #3 Più operazioni sullo stesso campo dello stesso movimento ne fanno una, con la base della prima; una cancellazione assorbe le altre sullo stesso movimento
- [ ] #4 Le schermate mostrano il pacchetto con le operazioni applicate e una riga modificata si riconosce
- [ ] #5 Le operazioni hanno un formato con una versione propria, separata da API_VERSION
<!-- AC:END -->
