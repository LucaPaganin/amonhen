---
id: TASK-61
title: 'Le schede si aprono da destra sul desktop, non dal fondo'
status: To Do
assignee: []
created_date: '2026-09-26 11:32'
updated_date: '2026-09-26 11:32'
labels: []
dependencies:
  - TASK-60
references:
  - >-
    C:\Users\lucap\.omp\agent\sessions\-git_repos-amonhen\2026-09-24T18-25-56-868Z_01a0d4aa-c684-7715-8842-e15e80e3b466\local\desktop-shell-plan.md
type: feature
ordinal: 60500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La scheda di un movimento, l editor dello split e l editor del budget sono un dialog ancorato in fondo alla finestra: a 1484px e un pannello da 720px appoggiato al bordo inferiore, l artefatto che piu si legge come telefono. Sopra i 1024px entrano da destra, alti quanto la finestra, e la lista resta visibile: si passa da un movimento all altro senza riaprire nulla. Sotto i 1024px resta il foglio dal basso che c e oggi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Sopra i 1024px la scheda entra da destra, e larga 460-520px e alta quanto la finestra, e la lista sotto resta visibile
- [ ] #2 L entrata muove solo transform e opacity, e prefers-reduced-motion la azzera come le altre
- [ ] #3 Esc, il clic sul backdrop e il focus trap sono invariati, e la pagina dietro non scorre mentre la scheda e aperta
- [ ] #4 Lo split editor resta usabile: il selettore categoria non si tronca (misurato) e il totale resta visibile senza scorrere
- [ ] #5 Sotto i 1024px il foglio dal basso e identico a prima (confronto di screenshot a 390)
<!-- AC:END -->
