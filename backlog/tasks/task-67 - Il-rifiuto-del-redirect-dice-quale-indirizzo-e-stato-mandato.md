---
id: TASK-67
title: Il rifiuto del redirect dice quale indirizzo e' stato mandato
status: Done
assignee: []
created_date: '2026-09-27 18:01'
updated_date: '2026-09-27 18:10'
labels:
  - connettore
  - documentazione
dependencies: []
type: bug
ordinal: 66500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Riconnettendo FinecoBank dal passo Banca il 502 arriva come 'Enable Banking refused the request: 400 Redirect URI not allowed', e non dice quale dei tre indirizzi che devono combaciare sia quello sbagliato. Enable Banking valida il redirect_url di POST /auth contro la lista registrata per l'applicazione - leggibile con GET /application, che risponde redirect_urls - quindi la diagnosi resta a mano: nella prova di oggi la registrazione conteneva solo l'indirizzo del ponte vecchio, https://dxp4800plus-bfd.cormorant-bleak.ts.net:5006/enablebanking/auth_callback, mentre accounts.json mandava https://sukuna.cormorant-bleak.ts.net:3000/callback. L'app conosce il valore che manda: lo dica.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un POST /auth rifiutato con REDIRECT_URI_NOT_ALLOWED risponde 502 con un detail che nomina l'indirizzo mandato e da dove viene (il redirect_url di accounts.json, passo Credenziali)
- [x] #2 Un rifiuto con un'altra causa resta la frase di prima, senza l'indirizzo
- [x] #3 tests/test_setup_api.py copre i due rami
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. refusal_code nel provider, letto dal campo error che Enable Banking manda nel corpo. 2. start_authorization in amonhen/api.py allunga il detail solo quando quel codice e' quello del redirect. 3. Test dei due rami in tests/test_setup_api.py. 4. README: la frase che spiega quell'errore dice anche come si legge la lista registrata.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Evidence: test_setup_api::test_a_refused_redirect_says_which_address_was_sent passes with the change and fails with the old detail line restored (AssertionError: 'https://amonhen.example.ts.net/callback' in 'Enable Banking refused the request: 400 Redirect URI not allowed'). The other branch is test_oauth::test_a_bank_name_the_provider_rejects_is_reported_as_an_upstream_failure, extended with the assertion that the address is not named. uv run pytest -p no:warnings: 399 passed. Diagnosi sul campo: GET /application risponde redirect_urls=[https://dxp4800plus-bfd.cormorant-bleak.ts.net:5006/enablebanking/auth_callback] per l'applicazione 46937639-5975-4f23-8069-b9a9165c3a13, mentre accounts.json manda https://sukuna.cormorant-bleak.ts.net:3000/callback; quattro indirizzi candidati provati, tutti rifiutati con REDIRECT_URI_NOT_ALLOWED.

Seguito della diagnosi, stesso difetto: la regola scritta a mano era sbagliata. Enable Banking rifiuta un indirizzo http (riferito dall'utente dal pannello), mentre README diceva che http su localhost andava bene. Corretti (non committati): il paragrafo README sulla registrazione, l'hint del passo Credenziali in web/src/screens/Setup.tsx (verificato a 390x844: il testo rende, curl della pagina no, DOM letto dal browser), la nota della prova con lo stub, e il default http://localhost:3000/callback in amonhen/config.py, che era la porta dell'app Flask. uv run pytest -p no:warnings: 399 passed; npm --prefix web run build ok. Aperto: se _check_redirect_url debba rifiutare un http non-localhost (localhost resta per la prova con lo stub) o solo avvisare — decisione dell'utente, non presa.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il 502 di POST /auth nomina ora l'indirizzo mandato quando Enable Banking rifiuta il redirect: refusal_code legge il campo error del corpo e _auth_refusal (amonhen/api.py) allunga solo il detail di REDIRECT_URI_NOT_ALLOWED, lasciando invariata la frase per ogni altra causa. Verificato con i due test qui sopra e con la suite intera (399 passed); README e CLAUDE.md dicono come si legge la lista registrata (GET /application).
<!-- SECTION:FINAL_SUMMARY:END -->
