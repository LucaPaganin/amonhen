---
id: TASK-94
title: Le proiezioni per scenari
status: Done
assignee:
  - '@claude'
created_date: 2026-11-03 12:00
updated_date: '2026-11-17T21:00:00Z'
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
- [x] #1 Per ogni obiettivo: se si raggiunge al ritmo attuale e quanto servirebbe al mese
- [x] #2 La scheda della Guida per lo scenario
- [x] #3 Tre scenari con rendimento reale e inflazione scritti a mano: gli scenari non si stimano dal passato (la distribuzione storica è TASK a parte)
- [x] #4 La soglia Coast FI: il capitale che senza altri versamenti raggiunge l'obiettivo della pensione nello scenario scelto
- [x] #5 La scheda della Guida per Coast FI
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verifica: 670 test passati da un checkout pulito (git archive, senza accounts.json e .env), 16 nuovi in tests/test_projection.py: la forma chiusa coincide con l'equazione mese per mese a 0, 4, -2 e 7,5%, il versamento necessario raggiunge la cifra, Coast FI cresce fino alla cifra senza versamenti, un aggiornamento di liquidità del broker non è un versamento, uno scenario mancante si dice. UI in Chromium su un ledger sintetico (13 mesi, 400 € al mese su Investimenti) servito su copie del ledger e della configurazione: senza scenari la proiezione rifiuta e nomina quelli che mancano; con i tre scritti, Casa a 55 mesi dà 42.000 / 46.432,57 / 49.615,79 € (il prudente è 20.000 + 55×400 a mano), e la Pensione ha Coast FI 168.904,39 € nel centrale. Corretti durante la verifica: una tabella che scorreva la pagina a 390 px (ora ogni tabella sta nel suo riquadro, a 390, 768 e 1280 la pagina non scorre), il ? di Coast FI dopo la cifra.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La quinta fetta della fase 12 (sezione 5.16 della specifica). Tabella nuova scenarios (prudente, centrale, favorevole, scritti a mano, senza default); core puro core/projection.py (rendimento mensile equivalente, valore alla data in forma chiusa, versamento necessario, Coast FI); services/projection.py; /api/plan con scenarios e observed, PUT/DELETE /api/plan/scenarios/{name}, POST /api/plan/projection; API_VERSION e REQUIRED_API_VERSION a 44. Nel Piano i blocchi Scenari e Dove si arriva, due schede della Guida (scenario, Coast FI), specifica 1.48, docs/investments.md e CLAUDE.md allineati. Decisioni: il capitale già messo da parte si scrive nel modulo finché non c'è il portafoglio (TASK-95); il ritmo di versamento parte da quello che il ledger mostra, la media mensile verso Investimenti sui 12 mesi completi senza gli aggiornamenti del broker; la cifra della pensione è il capitale, senza tasso di prelievo; l'inflazione mostra la cifra in euro della data e non cambia nessun risultato. Rischi e seguiti: il versamento osservato conta solo quanto passa da Investimenti (il fondo pensione dalla busta paga arriva con TASK-95 e il parser); TASK-97 aggiunge la distribuzione storica sopra questa proiezione.
<!-- SECTION:FINAL_SUMMARY:END -->
