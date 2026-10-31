---
id: TASK-83
title: Correzioni ai dati vivi e deploy
status: Done
assignee: []
created_date: '2026-10-31 18:00'
updated_date: '2026-10-31 18:00'
labels: []
dependencies: []
type: feature
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Lo script privato `dumps/fix_2026_10.py` è stato provato su una copia ed eseguito sul NAS il 31 ottobre 2026, con la v1.10.0 e dopo lo snapshot `2026-10-31T193138Z`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Viaggi è spesa rara; tag Spesa rara con le regole da 150 € e i due bonifici di Casa
- [x] #2 Scalable tiene la sola liquidità dal 29 ottobre e i PAC vanno su Investimenti; *Rendimento investimenti* è sparito
- [x] #3 I due accrediti passano su Immobile, che torna a zero
- [x] #4 Verifica sul vivo: liquidità, mesi di autonomia, verifica di ogni conto
<!-- AC:END -->
