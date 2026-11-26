---
id: TASK-101.1
title: La shell si apre senza rete
status: Done
assignee:
  - '@claude'
created_date: '2026-11-26T06:28:49Z'
updated_date: '2026-11-26T06:59:11Z'
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
- [x] #1 Con la rete il documento arriva sempre dalla rete: una build nuova si vede al primo caricamento, come oggi
- [x] #2 Senza rete l'app installata si apre sull'ultima build vista, con i suoi asset
- [x] #3 Le sezioni che non hanno dati offline dicono che serve la rete invece di restare vuote o in errore
- [x] #4 docs/frontend.md e il commento di sw.js dicono la regola nuova
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. sw.js: documento network-first con ultima copia come riserva, asset invariati, CACHE v2
2. App: banner "senza rete" e sezioni che servono la rete lo dicono
3. docs/frontend.md e commento di sw.js
4. Build e prova nel browser con rete tagliata
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il service worker già serviva il documento network-first con ripiego; confermato in un Chrome vero (seconda visita, poi offline). Le sezioni senza dati offline rispondono 'serve la rete' dal proxy di api. docs/frontend.md aggiornato.
<!-- SECTION:FINAL_SUMMARY:END -->
