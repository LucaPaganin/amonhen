---
id: TASK-66
title: >-
  Accettare una proposta decide i movimenti, e scrive una regola solo se lo
  chiedi
status: Done
assignee: []
created_date: '2026-09-27 08:08'
updated_date: '2026-09-27 08:26'
labels: []
dependencies: []
ordinal: 65500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Accettare una proposta in coda oggi scrive sempre una regola il cui pattern e il nome del merchant: il numero di regole cresce con ogni proposta accettata e con ogni modo in cui una banca stampa lo stesso esercente, e la persona non sceglie il testo. La scheda di un movimento ha gia la casella («Crea una regola per …») ma nessun posto dove scrivere il testo. Nuova forma: una casella spenta di default decide se una regola nasce, e un dialogo permette di editare il testo prima che venga scritto. Il movimento del singolo movimento resta com e: la coda e il posto dove la decisione e per merchant, e li la casella decide per tutti i movimenti in attesa.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A casella spenta, accettare assegna la categoria scelta ai movimenti in attesa di quel merchant e non scrive nessuna regola: la tabella rules resta identica
- [x] #2 A casella accesa, accettare apre un dialogo con il testo della regola precompilato e modificabile, e quello che si scrive e il pattern salvato nel ledger
- [x] #3 Annullare il dialogo non scrive niente: la proposta resta in coda e i movimenti restano dove erano
- [x] #4 Una categoria decisa a mano resta dopo un giro di Categorizza e dopo la scrittura di un altra regola
- [x] #5 Un testo di regola che non compila si rifiuta con 422 e il ledger resta invariato
- [x] #6 Test in tests/test_api.py coprono i quattro punti sopra e uv run pytest -q passa
- [x] #7 desiderata §5.5 dice che la regola nasce solo se la si chiede e con il testo che si scrive, versione e changelog aggiornati; README, web/README e CLAUDE.md dicono lo stesso, e il messaggio di Categorie e regole che prometteva una regola per ogni accettazione e corretto
- [x] #8 npm --prefix web run build passa
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Backend: una funzione sola per l accettazione (merchants.accept_merchant) con la regola opzionale, e waiting_transactions per i movimenti che un solo si puo decidere. 2. API: il campo rule nella richiesta e lesito (categoria, regola, movimenti) nella risposta; bump di API_VERSION e REQUIRED_API_VERSION a 20. 3. Test: accettare senza regola non scrive regole e decide i movimenti; il testo scritto e il pattern salvato; la decisione a mano non e sovrascritta da una regola con categoria diversa, mentre una con la stessa categoria la adotta; split non appiattita; testo che non compila non lascia niente (nemmeno la categoria). 4. Frontend: casella per merchant in proposalControls (spenta), dialogo che edita il testo, esito nel toast, frase del dettaglio. 5. Documenti: desiderata 1.11 (§5.5, §10, stato §9), README, web/README, CLAUDE.md. 6. Verifica: build, pytest, e nel browser i tre percorsi (spenta, accesa con testo modificato, annulla) contro una copia del ledger vero.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementato: merchants.accept_merchant (regola opzionale, rifiuto del bucket, DECIDABLE_BY_ONE_CATEGORY condiviso con la stake), waiting_transactions, api.py (campo rule, esito nella risposta, API_VERSION 20 e REQUIRED_API_VERSION 20), frontend (casella per merchant in proposalControls, dialogo che edita il testo con annulla/Esc, esito nel toast, frase del dettaglio riscritta, stakeText per il caso «niente che un si possa decidere», .rule-toggle condiviso con il foglio del movimento), CategoryRules (messaggio corretto), documenti (desiderata 1.11 con changelog, §10 e stato §9; README, web/README, CLAUDE.md). Verificato: uv run pytest -q verde; npm --prefix web run build verde; nel browser a 1298 e 390 contro una copia del ledger vero: casella spenta -> nessuna regola scritta (121 -> 121) e movimenti categorizzati, casella accesa -> dialogo precompilato col nome del merchant, testo editato in /coop/ -> una sola regola nuova con quel pattern (122), annulla ed Esc -> proposta e movimenti intatti e rules invariato. Difetto trovato e chiuso durante la revisione: una split con una parte nel bucket veniva appiattita da set_category; ora stake e accettazione escludono cio che un solo si non puo decidere (probe sul ledger vero: split [Spesa 1.00, Uncategorized 48.95] intatta dopo l accettazione) e un test la protegge. Revisione indipendente: quattro rilievi, tutti accettati e applicati (bump di API_VERSION, frase di CLAUDE.md e del §5.5 ristretta al caso vero, frase di web/README, categoria non creata quando la regola si rifiuta).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Accettare una proposta assegna la categoria scelta ai movimenti in attesa di quel merchant e non scrive nessuna regola: la casella «Crea una regola per …» e spenta di default, e quando la si accende il testo della regola si edita in un dialogo prima di scriverlo — il pattern salvato e quello, non il nome del merchant. La decisione a mano resta: una regola con categoria diversa non la rivendica, una con la stessa la adotta, ed e quello che la sua riga conta. Verificato in pytest (accettazione senza regola, testo editato, adozione, split intatta, testo che non compila) e in un browser reale a 1298 e 390 su una copia del ledger: 121 regole prima e dopo l accettazione senza regola, una sola regola nuova /coop/ con la casella accesa, annulla ed Esc senza scrivere niente. API_VERSION e REQUIRED_API_VERSION a 20 (verificato: bundle nuovo con processo vecchio mostra la schermata di server non aggiornato).
<!-- SECTION:FINAL_SUMMARY:END -->
