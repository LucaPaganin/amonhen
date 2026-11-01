---
id: TASK-89
title: I saldi della banca che contano sono un elenco chiuso
status: Done
assignee: []
created_date: '2026-11-01 13:00'
updated_date: '2026-11-01 13:00'
labels: []
dependencies: []
type: feature
ordinal: 89000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Un tipo di saldo sconosciuto valeva come disponibile: una previsione della banca poteva falsare la verifica della sezione 5.4 e la curva della liquidità senza che nulla lo dicesse. Rilasciato in v1.13.0.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Verifica e saldi leggono solo i tipi nell'elenco della sezione 5.4
- [x] #2 Il sync conserva anche i tipi che non legge
- [x] #3 Un tipo sconosciuto si segnala a ogni sync e in Conti, sul conto
<!-- AC:END -->
