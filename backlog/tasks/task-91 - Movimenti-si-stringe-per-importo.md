---
id: TASK-91
title: Movimenti si stringe per importo
status: Done
assignee: []
created_date: '2026-11-02 12:00'
updated_date: '2026-11-02 12:00'
labels: []
dependencies: []
type: feature
ordinal: 91000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
**Movimenti** ha un filtro per importo: un minimo e un massimo senza segno, estremi compresi, come le condizioni di una regola (sezione 5.5).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `/api/transactions` accetta `amount_min` e `amount_max`, e un importo illeggibile è un 422
- [x] #2 Il filtro sta fra gli altri e conta nel numero su *Filtri*
- [x] #3 Un importo scritto con la virgola vale
<!-- AC:END -->
