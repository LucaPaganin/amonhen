---
id: TASK-72
title: >-
  La regola chiesta da un movimento si scrive in un dialogo invece di nascere in
  silenzio
status: Done
assignee: []
created_date: '2026-10-25 22:06'
labels: []
dependencies: []
ordinal: 71500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Bug: in Movimenti (e nella coda), con la casella «Crea una regola» accesa, scegliere la categoria chiudeva il foglio e scriveva subito una regola con il nome del merchant, senza dialogo e senza avviso. Ora si apre l'editor della regola, precompilato e modificabile, e il movimento prende la categoria solo quando la regola si salva.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Con la casella accesa, scegliere la categoria apre il dialogo della regola invece di chiudere tutto
- [x] #2 Chiudere il dialogo non scrive niente
- [x] #3 Il dialogo resta aperto quando si sceglie un'opzione dalle sue tendine
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
RuleSheet (web/src/components/RuleSheet.tsx) si apre da Movimenti e dalla coda; useReviewQueue.categorize non crea più regole. Verificato con un browser vero a 390 e 1280 px.
<!-- SECTION:FINAL_SUMMARY:END -->
