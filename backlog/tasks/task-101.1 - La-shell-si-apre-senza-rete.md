---
id: TASK-101.1
title: La shell si apre senza rete
status: To Do
assignee: []
created_date: '2026-11-26T06:28:49Z'
labels: []
dependencies: []
references:
  - desiderata-monitoring-finanziario.md
  - docs/frontend.md
parent_task_id: TASK-101
type: feature
ordinal: 101000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Prima fetta della sezione 5.18. Oggi web/public/sw.js non mette in cache il documento, di proposito: un documento vecchio punta ad asset che una build ha sostituito e la pagina resta bianca. Per aprire l'app offline serve un documento in cache, senza riaprire quel problema quando la rete c'è.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Con la rete il documento arriva sempre dalla rete: una build nuova si vede al primo caricamento, come oggi
- [ ] #2 Senza rete l'app installata si apre sull'ultima build vista, con i suoi asset
- [ ] #3 Le sezioni che non hanno dati offline dicono che serve la rete invece di restare vuote o in errore
- [ ] #4 docs/frontend.md e il commento di sw.js dicono la regola nuova
<!-- AC:END -->
