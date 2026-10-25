---
id: TASK-74
title: 'Una regola fa una cosa a certe condizioni: categoria, cancella o giroconto'
status: Done
assignee: []
created_date: '2026-10-25 22:06'
labels: []
dependencies: []
ordinal: 73500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le regole si restringono a un conto e a un intervallo di importi e, oltre ad assegnare una categoria, possono cancellare i movimenti (quelli che ci sono, dopo l'anteprima, e quelli dei sync futuri) o registrarli come giroconto verso una destinazione. Cancellare vince su giroconto, giroconto su categoria.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una regola che cancella mostra prima quanti e quali movimenti prende, e li porta nel cestino al salvataggio
- [x] #2 I movimenti nuovi che combaciano finiscono nel cestino al sync successivo
- [x] #3 Un movimento che una regola cancellerebbe non si ripristina finché la regola c'è (409 che la nomina)
- [x] #4 A parità di testo vince la regola con più condizioni
- [x] #5 Togliere una regola di giroconto rimanda in coda i movimenti che aveva registrato
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
rules ricostruita con id, action, target, account_id, amount_min, amount_max (_generalize_rules). apply_rule_changes applica cancellazioni, giroconti e categorie in una transazione. /api/rules/preview, API_VERSION 22. Spec 1.14, sezione 5.5. tests/test_rule_actions.py.
<!-- SECTION:FINAL_SUMMARY:END -->
