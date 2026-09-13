---
id: TASK-36
title: 'Una regola può essere un''espressione regolare, scritta fra barre'
status: Done
assignee: []
created_date: '2026-09-13 19:30'
labels: []
dependencies: []
type: feature
ordinal: 35500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un pattern fra barre è un'espressione, tutto il resto resta il testo di prima
- [ ] #2 Il tipo sta nel pattern, non in una colonna: il database e l'API non cambiano forma
- [ ] #3 L'espressione vede lo stesso testo delle regole: spazi collassati, maiuscole ignorate
- [ ] #4 Vince il pattern più lungo, testo o espressione che sia: la più stretta
- [ ] #5 Un'espressione che non compila è rifiutata con 422 e il motivo, e non scrive niente
- [ ] #6 Una barra sola e // restano testo, così un pattern con una data non diventa un'espressione
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Le regole accettano un'espressione regolare scritta fra barre: /amazon (eu|payments)/ tiene una famiglia che la banca scrive in troppi modi per elencarli, dove i testi sarebbero una lista che cresce a ogni grafia nuova. Il tipo sta nel pattern e non in una colonna, quindi il ledger, l'API e la CLI non hanno un campo in più; rule_pattern() e Rule.expression sono gli unici due lettori delle barre, e l'espressione è compilata una volta per sorgente perché un sync la confronta con ogni descrizione del ledger. L'espressione vede lo stesso testo delle regole — spazi collassati, maiuscole ignorate — così una parola e un'espressione descrivono gli stessi movimenti. Misurato sul ledger vero (copia): /(srl|spa|snc)/ tiene 32 movimenti dove i tre testi ne tenevano 27+1+3, con una regola sola; /^srl(/ è rifiutata con 422 e il motivo (missing ), unterminated subpattern at position 4) e non scrive nessuna regola. Prima versione: l'espressione vinceva sempre sul testo, e misurandola prendeva 56 movimenti invece dei 31 dei tre testi, cioè rubava a regole di testo più strette. L'utente ha chiesto le espressioni, non una precedenza nuova: vince il più lungo, testo o espressione che sia, che è la promessa che c'era già. Da lì l'espressione ne prende 32: prende i suoi e non toglie niente a chi dice di più. API_VERSION 10 -> 11 con REQUIRED_API_VERSION, perché un server vecchio avrebbe risposto 201 tenendo l'espressione come testo: il caso che l'handshake esiste per prendere. 314 test verdi.
<!-- SECTION:FINAL_SUMMARY:END -->
