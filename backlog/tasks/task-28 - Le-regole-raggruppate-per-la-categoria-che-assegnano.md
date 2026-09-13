---
id: TASK-28
title: Le regole raggruppate per la categoria che assegnano
status: Done
assignee: []
created_date: '2026-09-13 17:10'
labels: []
dependencies: []
type: feature
ordinal: 27500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le categorie sono le voci di primo livello, chiuse, con quante regole e quanti movimenti tengono
- [ ] #2 Sotto ognuna, espandibile, le regole che assegnano quella categoria, con testo, conteggio, categoria e Rimuovi
- [ ] #3 Cercare apre i gruppi che hanno trovato qualcosa, perche la ricerca rende i risultati la cosa da guardare
- [ ] #4 Verificato sulla contabilita vera: 4 gruppi, 45 regole, 146 movimenti, righe coincidenti con l'API
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Trenta pattern sono trenta decisioni; otto categorie sono un budget. La sezione ora elenca le categorie che le regole assegnano e apre sotto i testi che le assegnano, con i conteggi per gruppo. Verificato dal vivo: i gruppi sono quelli della contabilita vera (una regola, tredici, otto, ventitré: quarantacinque in tutto, centoquarantasei movimenti), le righe mostrate coincidono una per una con quelle dell'API, la ricerca apre esattamente i gruppi che hanno trovato qualcosa, e a 390 px non c'e scroll orizzontale. Nel gruppo la riga si stringe su due linee invece di tre, altrimenti ventitré regole tornano a essere un muro.
<!-- SECTION:FINAL_SUMMARY:END -->
