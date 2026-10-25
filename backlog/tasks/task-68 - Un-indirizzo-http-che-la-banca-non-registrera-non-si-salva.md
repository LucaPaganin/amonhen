---
id: TASK-68
title: Un indirizzo http che la banca non registrera' non si salva
status: Done
assignee: []
created_date: '2026-09-27 18:12'
updated_date: '2026-09-27 18:13'
labels:
  - connettore
dependencies: []
type: bug
ordinal: 67500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Enable Banking non registra indirizzi http - lo dice il suo pannello - e il passo Credenziali accettava lo stesso un http non-localhost, salvando una configurazione che al connect non poteva che fallire: e' successo con https://sukuna.cormorant-bleak.ts.net:3000/callback, rimasto nel file dall'era Flask. localhost resta l'eccezione, perche' la prova da zero con lo stub (tools/rehearse_local.sh) serve la callback dalla stessa macchina e non ha un certificato da offrire.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un redirect URL http non-localhost viene rifiutato dove si scrive, con la ragione (Enable Banking registra solo HTTPS)
- [x] #2 http su localhost resta accettato: e' l'indirizzo che la prova da zero con lo stub scrive
- [x] #3 Il test dell'indirizzo rifiutato copre i due rami, il rifiuto e l'eccezione
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. _check_redirect_url in amonhen/config.py rifiuta http fuori da localhost/127.0.0.1/::1. 2. Caso in piu' nel test dell'indirizzo rifiutato, piu' l'eccezione localhost verificata. 3. README: la frase del passo dice anche che ogni altro http si rifiuta dove si scrive.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Evidenza: tests/test_setup_api.py::test_an_address_the_bank_could_not_use_is_refused ora mette http://amonhen.example.ts.net/callback fra i rifiutati (422) e verifica che il detail dica https, poi che http://localhost:8000/callback salvi (200) - 15 passed nel file, 399 passed nella suite intera. Il set _LOCAL_REDIRECT_HOSTS copre localhost, 127.0.0.1 e ::1 con la stessa riga, quindi il test ne prova uno. tools/rehearse_local.sh scrive http://localhost:<port>/callback (riga 169), quindi resta dentro l'eccezione; non l'ho eseguito: qui il motore Docker e' fermo.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il passo Credenziali rifiuta un indirizzo http che non sia su localhost, con la ragione che Enable Banking non ne registra nessuno: _LOCAL_REDIRECT_HOSTS in amonhen/config.py tiene l'eccezione per la prova locale con lo stub. Verificato con il test dei due rami (422 con https nella ragione, 200 per localhost) e con la suite intera, 399 passed; README e CLAUDE.md dicono la regola dove si scrive l'indirizzo.
<!-- SECTION:FINAL_SUMMARY:END -->
