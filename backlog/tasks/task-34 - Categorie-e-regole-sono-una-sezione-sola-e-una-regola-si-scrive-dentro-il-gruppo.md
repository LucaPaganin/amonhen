---
id: TASK-34
title: >-
  Categorie e regole sono una sezione sola, e una regola si scrive dentro il
  gruppo
status: Done
assignee: []
created_date: '2026-09-13 18:59'
labels: []
dependencies: []
type: feature
ordinal: 33500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 La barra in basso ha cinque voci: Categorie sostituisce Regole, e il menu la nomina per esteso
- [ ] #2 Una voce per categoria: nome, quanti movimenti e regole tiene, i due flag che le metriche leggono
- [ ] #3 I flag stanno sulla testata che apre il gruppo e non aprono ne' chiudono niente
- [ ] #4 Dentro il gruppo aperto ci sono le sue regole e la riga che ne scrive una: la categoria e' quella del gruppo, quindi non si sceglie
- [ ] #5 Creare una categoria sta in cima; Conti e budget non ha piu' il pannello Categorie
- [ ] #6 Misurato a 390 px: tante voci quante le categorie dell'API, conteggi identici a quelli dell'API, nessuno scroll orizzontale
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Le due cose erano in due sezioni: le categorie in fondo a Conti e budget, le regole in una sezione propria. Ora sono una sezione sola, perche' quello che una categoria e' e quello che ci finisce sono la stessa decisione vista dai due capi. Una voce per categoria con i suoi due flag, le sue regole che si aprono sotto, e in fondo al gruppo la riga che ne scrive una: una regola assegna la categoria sotto cui sta, quindi la tendina della categoria non serve piu'. Creare una categoria e' la barra in cima alla sezione. Misurato a 390 px su una copia del ledger: 13 voci per 13 categorie dell'API, ogni conteggio della testata identico a quello calcolato dall'API, i flag salvati via PATCH senza aprire il gruppo, nessuno scroll orizzontale. Un primo tentativo teneva il modulo della regola in cima e la lista scendeva a 742 px (una voce visibile); il modulo e' finito dentro il gruppo e la lista torna a 361 px, con tre voci intere nella prima schermata. Conti e budget resta i conti e i budget del mese.
<!-- SECTION:FINAL_SUMMARY:END -->
