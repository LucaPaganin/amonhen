---
id: TASK-86
title: La spesa è al netto dei rimborsi
status: Done
assignee: []
created_date: '2026-11-01 09:00'
updated_date: '2026-11-01 09:00'
labels: []
dependencies: []
type: feature
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La spesa contava solo le uscite: una spesa anticipata per altri restava intera anche dopo il rimborso. Un accredito in una categoria che non è Entrata ora abbassa quella categoria. Il blocco degli accrediti da chiarire e le quote del cointestato sono passi successivi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una sola definizione di spesa, letta da metriche, mese, grafici e budget
- [x] #2 Le categorie che hanno solo accrediti diventano Entrata alla migrazione
- [x] #3 Un rimborso esce dalle entrate; un accredito senza categoria non conta come rimborso
- [x] #4 Il segno Entrata si gestisce da Categorie e regole
- [x] #5 Rimborsi riassegnati alle categorie vere sul ledger vivo
<!-- AC:END -->
