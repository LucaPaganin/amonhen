---
id: TASK-100
title: L'ETF dai documenti del broker e dalla pagina pubblica
status: To Do
assignee: []
created_date: '2026-11-18T07:05:00Z'
labels: []
dependencies:
  - TASK-96
  - TASK-99
type: feature
ordinal: 99000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dalla specifica 1.51 (sezione 5.16) AmonHen non apre sessioni presso il broker. L'ETF del PAC entra come gli altri strumenti: i contratti di esecuzione e l'estratto titoli arrivano da Paperless e li legge payslip-parser (TASK-99), l'adapter documenti li traduce nelle transazioni e nelle posizioni riportate che BrokerSource già porta, e il prezzo di fine mese si legge dalla pagina pubblica dell'ETF su Borsa Italiana con lo stesso schema del valore quota del fondo (adapters/borsa_italiana.py).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un contratto letto da Paperless diventa una transazione dell'ETF (record_trade), una volta sola, e l'esito torna su Paperless come per le buste paga
- [ ] #2 L'estratto titoli diventa la posizione riportata, e la riconciliazione mostra quote dalle transazioni contro quote dell'estratto
- [ ] #3 Il prezzo di fine mese dell'ETF si legge dalla sua pagina su Borsa Italiana, rifiutato se la pagina dà un altro mese; un mese mancante si scrive a mano nel Portafoglio
- [ ] #4 Il versato dalle transazioni si riconcilia con i bonifici del PAC che il ledger vede
- [ ] #5 Guida e specifica dicono da dove viene ogni cifra dell'ETF
<!-- AC:END -->
