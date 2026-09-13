---
id: TASK-37
title: Il rifiuto di una regola si legge dove la regola si è scritta
status: Done
assignee: []
created_date: '2026-09-13 19:30'
labels: []
dependencies: []
type: bug
ordinal: 36500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il motivo di un pattern rifiutato compare sotto il campo che l'ha scritto
- [ ] #2 Il riquadro condiviso in cima non lo ripete
- [ ] #3 Misurato: 6 px sotto il campo, dentro la prima schermata, riquadri in cima 0
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
L'errore di scrittura di una regola era mostrato solo in cima alla sezione. Finché l'unico modo di sbagliare da quel modulo era un nome di categoria inesistente o il secchio della coda — due cose che la tendina non offre — quel riquadro non serviva a niente; con le espressioni il refuso diventa l'errore normale e il motivo finiva fuori schermo, perché il gruppo di una categoria sta in fondo a una lista di tredici. Ora il modulo mostra il rifiuto sotto il campo, e il riquadro in cima non lo ripete: misurato a 390x844, il messaggio sta 6 px sotto il campo, dentro la prima schermata, e i riquadri in cima sono 0.
<!-- SECTION:FINAL_SUMMARY:END -->
