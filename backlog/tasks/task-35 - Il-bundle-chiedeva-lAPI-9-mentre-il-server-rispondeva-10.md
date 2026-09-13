---
id: TASK-35
title: Il bundle chiedeva l'API 9 mentre il server rispondeva 10
status: Done
assignee: []
created_date: '2026-09-13 18:59'
labels: []
dependencies: []
type: bug
ordinal: 34500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 REQUIRED_API_VERSION torna in passo con API_VERSION, come dice il commento accanto
- [ ] #2 Un bundle nuovo contro un server vecchio si ferma e lo dice, invece di mandare la categoria scelta e vedersela ignorare
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La costante del client era rimasta a 9 quando TASK-29 ha portato il server a 10. Il caso che il controllo esiste per prendere e' proprio quello: il bundle manda la categoria scelta nella decisione di una proposta, un server vecchio la ignora, e la regola si scrive con quella proposta senza che niente lo dica. Ora e' 10. Nessun cambio all'API: e' la costante che mancava.
<!-- SECTION:FINAL_SUMMARY:END -->
