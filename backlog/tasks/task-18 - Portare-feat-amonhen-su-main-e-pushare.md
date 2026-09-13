---
id: TASK-18
title: Portare feat/amonhen su main e pushare
status: Done
assignee: []
created_date: '2026-09-13 10:05'
updated_date: '2026-09-13 15:07'
labels: []
dependencies: []
ordinal: 17500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il branch feat/amonhen non e' mai stato pushato e origin/main e' indietro. La decisione presa e' di schiacciare i commit per fase in uno solo prima del push (nessun force-push necessario). Include la verifica finale: suite verde, build della PWA, e il controllo che la cronologia unita racconti le fasi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La suite è verde su main e la PWA si costruisce
- [x] #2 Il branch è schiacciato in un commit solo, sopra il commit della strumentazione di sviluppo
- [x] #3 La cronologia unita racconta le fasi 0-5, non i passi
- [x] #4 main è su origin come fast-forward del vecchio main
- [x] #5 Nel commit non entra nessun file di dati o segreto: né .env, né il ledger, né i dump, né le chiavi
- [x] #6 Il branch resta in locale con la storia per fasi, come archivio
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il branch è su main e su origin: 24 commit per fase schiacciati in uno che racconta le fasi da 0 a 5, sopra il commit della strumentazione. La suite passa su main e la PWA si costruisce. Nel commit non è entrato niente che non sia codice o documento: il .env, il ledger, i dump e le chiavi restano fuori, e la rinomina meccanica ha disignorato il vecchio monitor.db (un guscio vuoto, verificato: zero righe) che è stato tolto dall'indice e dal disco. Il branch feat/amonhen resta in locale come archivio dei passi.
<!-- SECTION:FINAL_SUMMARY:END -->
