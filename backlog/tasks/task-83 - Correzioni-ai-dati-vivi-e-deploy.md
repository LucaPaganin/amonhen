---
id: TASK-83
title: Correzioni ai dati vivi e deploy
status: To Do
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
Lo script privato `dumps/fix_2026_10.py` è provato su una copia del ledger del 31 ottobre. Sul NAS si esegue solo su richiesta esplicita, dopo aver portato il NAS alla nuova versione e fatto uno snapshot.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Viaggi è spesa rara; tag Spesa rara con le regole da 150 € e i due bonifici di Casa
- [ ] #2 Scalable tiene la sola liquidità dal 29 ottobre e i PAC vanno su Investimenti; *Rendimento investimenti* è sparito
- [ ] #3 I due accrediti passano su Immobile, che torna a zero
- [ ] #4 Verifica sul vivo: liquidità, mesi di autonomia, verifica di ogni conto
<!-- AC:END -->
