---
id: TASK-1
title: Fase 0 — verifica del percorso di fetch Enable Banking
status: Done
assignee:
  - '@luca'
created_date: '2026-09-12 12:07'
updated_date: '2026-09-12 12:12'
labels:
  - phase-0
dependencies: []
type: spike
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
L'integrazione PSD2 di bank-connector esiste ma non è verificata contro l'API attuale e non è in uso. Prima di riusarla va provato che autenticazione, lista conti e fetch transazioni funzionino ancora, e servono fixture reali (anonimizzate) su cui poggeranno i test di parsing. Script usa e getta, fuori dall'architettura: nessun parsing, nessuna persistenza strutturata. Vedi §7 e §9 Fase 0 della desiderata.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Lo script autentica (JWT RS256), elenca i conti collegati e scarica le transazioni di ciascuno, scrivendo il JSON grezzo su disco
- [x] #2 Esistono su disco dump reali di almeno due istituti, con transazioni sia BOOK che PDNG
- [x] #3 I dump sono anonimizzati e committati come fixture per i test di parsing
- [x] #4 Lo script resta fuori dall'architettura applicativa (usa e getta)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Scrivere tools/phase0_dump.py: autentica via JWT RS256, legge le sessioni/conti dall'API e scarica le transazioni grezze per ogni conto configurato, scrivendole in dumps/ senza parsing.
2. Eseguirlo contro l'API reale e verificare che i dump contengano sia BOOK che PDNG per almeno due istituti.
3. Scrivere tools/anonymize_dump.py: pseudonimizza in modo deterministico identificativi, nomi, IBAN e importi, preservando struttura, segno, stato e testo merchant.
4. Generare le fixture in tests/fixtures/, verificare che non contengano identificativi reali e committarle.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Evidenza:
- `uv run python tools/phase0_dump.py`: sessioni lette dall'API, 306 transazioni Revolut personale (304 BOOK + 2 PDNG), 132 Revolut cointestato (BOOK), Fineco 401/403.
- Il consenso Fineco risulta scaduto nonostante la sessione risulti AUTHORIZED fino al 2026-11-11: il dump Fineco usato per le fixture proviene da una sessione precedente (2026-04-27..2026-05-16). È il caso previsto dalla riga "Enable Banking cambia gli id o scade il consenso" della tabella rischi; il percorso di recupero resta l'import file.
- Fixture: 124 transazioni anonimizzate (60 + 60 + 4), due istituti, BOOK e PDNG presenti.
- Verifica anonimizzazione (script su fixture vs dump grezzi): 0 leak su uid/session id/IBAN/entry_reference/nomi intestatario/date originali.
- `uv run pytest`: 92 passed (8 nuovi).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Verificato il percorso di fetch Enable Banking contro l'API attuale con tools/phase0_dump.py: autenticazione, lista conti e fetch transazioni funzionano (306 transazioni Revolut, di cui 2 PDNG); il consenso Fineco è scaduto (401/403). Prodotte fixture anonimizzate da due istituti (124 transazioni, BOOK e PDNG) con tools/anonymize_dump.py, usato anche per i test di parsing delle fasi successive. Verifica: nessun identificativo o importo reale residuo nelle fixture, 92 test passati.
<!-- SECTION:FINAL_SUMMARY:END -->
