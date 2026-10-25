---
id: TASK-70
title: 'Il budget si pianifica mese per mese, con le voci dentro il tetto'
status: Done
assignee: []
created_date: '2026-10-25 19:22'
labels: []
dependencies: []
ordinal: 69500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Desiderata 5.12 (spec 1.12). Il budget per categoria diventa un default che vale da un mese in avanti, sovrascrivibile per un mese solo; dentro il tetto si scrivono voci con descrizione, importo, data facoltativa, priorità e nota, da zero, da un movimento passato o copiate dal mese prima. Lo speso resta per categoria. Il budget ha una sezione sua.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Cambiare il default da un mese lascia i mesi prima con il budget che avevano
- [x] #2 Un mese può avere un budget suo, e toglierlo lo riporta al default
- [x] #3 Le voci si leggono per priorità e la sezione dice quali non ci stanno più, senza scegliere cosa tagliare
- [x] #4 Una voce si precompila da un movimento passato e resta modificabile prima di salvarla
- [x] #5 Le voci di una categoria si copiano dal mese prima senza duplicarsi
- [x] #6 I budget scritti prima diventano default validi da sempre
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Nuovo modulo amonhen/budgets.py con tabelle budgets (per from_month), budget_months e budget_items; migrazione _date_budgets. API 21: ogni scrittura risponde con il mese intero. Sezione Budget nella barra in basso al posto di Conti, che passa nel menu. Verificato a 390 e 1280 px su una copia del ledger con Playwright.
<!-- SECTION:FINAL_SUMMARY:END -->
