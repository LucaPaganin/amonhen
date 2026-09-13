---
id: TASK-3
title: 'Fase 2 — riconciliazione, categorie, prima UI'
status: Done
assignee:
  - '@luca'
created_date: '2026-09-12 12:07'
updated_date: '2026-09-12 14:28'
labels:
  - phase-2
dependencies:
  - TASK-2
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Riconciliazione automatica dei trasferimenti interni (importo opposto, conti diversi, |Δt| ≤ 2 giorni, matching bipartito di peso massimo, confidenza rivedibile), normalizzazione merchant con cache, regole deterministiche, e prima UI mobile-first: coda delle transazioni da confermare e lista movimenti filtrabile. Backend FastAPI, frontend React come PWA dietro Tailscale. Vedi §5.3, §5.5, §9 Fase 2.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il transfer matching appaia le due gambe con importo opposto, conti diversi e |Δt| ≤ 2 giorni, senza usare le descrizioni
- [x] #2 In caso di ambiguità la risoluzione usa matching bipartito di peso massimo, non greedy
- [x] #3 Ogni link ha confidenza, metodo e flag di revisione umana
- [x] #4 Merchant normalizzati con cache e regole esatte sul merchant normalizzato
- [x] #5 UI: schermata coda da confermare + lista movimenti filtrabile, usabile da telefono
- [x] #6 Si può categorizzare una settimana di movimenti dal telefono senza toccare il database a mano
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Core ledger: set/remove category posting, undo del clearing su rifiuto, esclusione delle coppie rifiutate dai candidati.
2. Merchant: normalizzazione deterministica (coda di metadati del descrittore), cache in `merchants`, regole esatte merchant→categoria, applicazione ai movimenti.
3. Riconciliazione §5.3: matching bipartito di peso massimo (non greedy) con confidenza e metodo, rimpiazza il greedy della fase 1; test contro ricerca esaustiva.
4. API FastAPI: lista movimenti filtrabile, coda di revisione, categorizzazione, split, conferma/rifiuto link, categorie.
5. Frontend React PWA mobile-first: schermata "da confermare" e lista movimenti; manifest + service worker; build in Docker, servizio dietro Tailscale.
6. Verifica: test + browser reale su viewport telefono (categorizzare una settimana senza toccare il database).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Chiusura dopo la review finale del branch (commit successivi):
- `/connect` e `/callback` implementati come endpoint dell'applicazione (§7): /connect avvia l'autorizzazione e memorizza lo stato in `settings`, /callback finalizza la sessione e appende gli account autorizzati ad accounts.json. Gli errori della banca vengono riportati testualmente (es. "400 Redirect URI not allowed"), non come 500.
- `tools/phase0_dump.py` (che importava il pacchetto `bank_connector` eliminato) sostituito da `tools/dump_raw.py`, riscritto contro il provider attuale.
- Un numero non parsabile ora è 422 anche su /api/metrics e /api/budgets (ArithmeticError), e la CLI non crasha su `--mortgage` o `budget` malformati.
- compose: la cadenza di sync arriva da MONITOR_SYNC_INTERVAL_HOURS, le variabili LLM/EB documentate raggiungono il container, accounts.json è montato scrivibile (ci scrive /callback) e `serve` fallisce subito se config o chiave non sono utilizzabili.
- Corrette due affermazioni invertite in web/README.md.
- Verifica live di /connect: la chiamata reale a Enable Banking risponde e l'errore della banca è riportato (manca la registrazione del redirect URL sul portale EB, azione dell'utente). Il percorso completo è coperto dai test con provider simulato.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fase 2 completata: riconciliazione dei giroconti con matching bipartito di peso massimo (esatto, non greedy) e confidenza rivedibile, normalizzazione merchant con regole esatte, e la prima UI — backend FastAPI e PWA React mobile-first con la coda da confermare e la lista movimenti filtrabile. Verifica: 115 test allora, e prova in browser sul ledger reale (categorizzazione dalla coda, creazione categoria dal telefono, conferma/rifiuto di un giroconto, schermata movimenti). La review indipendente di questa fase ha prodotto sette difetti, tutti corretti in fase 3.
<!-- SECTION:FINAL_SUMMARY:END -->
