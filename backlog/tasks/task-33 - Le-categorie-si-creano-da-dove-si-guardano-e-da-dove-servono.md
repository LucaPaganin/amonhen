---
id: TASK-33
title: Le categorie si creano da dove si guardano e da dove servono
status: Done
assignee: []
created_date: '2026-09-13 18:17'
labels: []
dependencies: []
type: feature
ordinal: 32500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 In Conti e budget il pannello Categorie ha un campo per crearne una, visibile anche quando non ce n'e' nessuna
- [ ] #2 Nella tendina di una proposta l'ultima voce e' Nuova categoria: apre il campo sul posto e la categoria arriva gia' scelta
- [ ] #3 Il testo spiega che una categoria non categorizza niente da sola
- [ ] #4 Verificato end to end: creata da Conti e budget compare nell'API e in lista; creata da una proposta viene scelta e accettarla scrive la regola con quella categoria e ci sposta il movimento
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La creazione esisteva solo dentro il pannello che si apre da un movimento: da Regole o dalle proposte non c'era modo, ed e' il motivo per cui la domanda era come si fa. Ora c'e' dove si guardano le categorie (Conti e budget, con il campo in cima al pannello e il testo che spiega che una categoria non categorizza niente da sola) e dove servono (l'ultima voce della tendina di una proposta apre il campo sul posto, e il nome appena creato arriva gia' scelto per quella proposta). Verificato end to end in entrambi i posti, fino alla regola scritta con la categoria nuova e al movimento spostato.
<!-- SECTION:FINAL_SUMMARY:END -->
