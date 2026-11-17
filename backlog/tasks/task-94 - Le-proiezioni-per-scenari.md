---
id: TASK-94
title: Le proiezioni per scenari
status: In Progress
assignee:
  - '@claude'
created_date: 2026-11-03 12:00
updated_date: '2026-11-17T20:51:00Z'
labels: []
dependencies:
  - TASK-92
type: feature
ordinal: 94000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La terza fetta della fase 12 (sezione 5.16): ogni obiettivo proiettato in tre scenari, con le ipotesi scritte da una persona accanto al risultato, in euro di oggi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per ogni obiettivo: se si raggiunge al ritmo attuale e quanto servirebbe al mese
- [ ] #2 La scheda della Guida per lo scenario
- [ ] #3 Tre scenari con rendimento reale e inflazione scritti a mano: gli scenari non si stimano dal passato (la distribuzione storica è TASK a parte)
- [ ] #4 La soglia Coast FI: il capitale che senza altri versamenti raggiunge l'obiettivo della pensione nello scenario scelto
- [ ] #5 La scheda della Guida per Coast FI
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Tabella nuova scenarios(name CHECK IN prudente|centrale|favorevole, real_return, inflation): tre righe scritte a mano, senza default nel codice; uno scenario mancante si dice e non si calcola.
2. Core puro (core/projection.py): W(t+1) = W(t)(1+r_m) + c, r_m = (1+r)^(1/12)-1, in euro di oggi; mesi per raggiungere la cifra o il valore a scadenza; versamento mensile necessario (forma chiusa); Coast FI = cifra / (1+r_m)^mesi.
3. Caso d'uso services/projection.py: per ogni obiettivo e per i tre scenari, se si raggiunge al ritmo dato, il valore a scadenza, il mancante e il versamento mensile necessario; il ritmo osservato è la media mensile dei versamenti verso Investimenti sui 12 mesi completi (postings sul conto virtuale), da cui si parte come proposta; capitale di partenza e versamento si possono scrivere nel modulo, senza salvarli.
4. API: PUT/DELETE /api/plan/scenarios/{name}, POST /api/plan/projection; API_VERSION 44 con REQUIRED_API_VERSION.
5. PWA: blocco Scenari e blocco Proiezioni nel Piano; Coast FI sull'obiettivo scelto. Schede della Guida: scenario, Coast FI.
6. Test del core, del servizio e dell'API; suite da checkout pulito; UI in Chromium su ledger sintetico.
7. Spec 1.48 (5.16, 6, 9), docs/investments.md, CLAUDE.md (diciannove tabelle).
<!-- SECTION:PLAN:END -->
