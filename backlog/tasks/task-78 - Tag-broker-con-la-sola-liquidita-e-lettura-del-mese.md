---
id: TASK-78
title: Tag, broker con la sola liquidità e lettura del mese
status: Done
assignee: []
created_date: '2026-10-31 18:00'
updated_date: '2026-10-31 18:00'
labels: []
dependencies: []
type: feature
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La base delle fette successive: una sola definizione di raro e irrinunciabile, il broker senza portafoglio, il mese contro il solito.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un tag porta gli stessi segni di una categoria e conta allo stesso modo in spesa tipica, riserva, anomalie e mese
- [x] #2 Una regola può mettere un tag, si somma alle altre azioni, e toglierla toglie solo i tag messi da lei
- [x] #3 Un tag messo a mano sopravvive a cancellazione e ripristino
- [x] #4 `/api/month` confronta il mese con lo stesso giorno dei mesi completi precedenti, con le spese rare a parte
- [x] #5 Le anomalie sotto i 100 €, i cambi valuta e le spese rare non si segnalano, e la frase è in italiano
- [x] #6 `savings_flow` e *Rendimento investimenti* non esistono più; API 31
<!-- AC:END -->
