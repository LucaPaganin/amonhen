---
id: TASK-95
title: Il portafoglio si ricostruisce dalle fonti, su dati finti
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-16T20:18:00Z'
updated_date: '2026-11-17T21:03:00Z'
labels: []
dependencies: []
references:
  - desiderata-monitoring-finanziario.md
  - docs/investments.md
type: feature
ordinal: 95000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Terza fetta della fase 12 (sezione 5.16, versione 1.46). Prende il posto di TASK-93, che dichiarava il portafoglio a mano: con la 1.46 le posizioni si ricostruiscono da transazioni e documenti. Questa fetta costruisce il modello e i calcoli con sorgenti finte dietro porte, prima di collegare quelle vere, così un errore è del modello e non della fonte. Come costruirlo sta in docs/investments.md.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Strumenti, transazioni, contributi al fondo, prezzi di fine mese e snapshot hanno tabelle loro, e nessuna scrive un posting: spesa, mesi di autonomia e verifica della sezione 5.4 non cambiano
- [ ] #2 Un contributo nasce trattenuto da una busta paga e diventa investito da un prospetto; trattenuto = investito + in transito vale a ogni data, e il transito si legge
- [ ] #3 Le riconciliazioni (PAC atteso contro posizioni, cedole BTP contro accrediti, trattenuto contro investito, quote contro prospetto) mostrano le due cifre e la differenza, e non correggono nulla
- [ ] #4 BTP Valore al nominale più rateo, con il premio fedeltà solo alla scadenza; fondo a quote per valore quota della sua classe; ETF a quote per prezzo di chiusura
- [ ] #5 TWR e MWR per strumento e per l'insieme, con test su flussi scritti a mano di cui il risultato è noto
- [ ] #6 Il patrimonio complessivo di fine mese somma liquidità, portafoglio, fondo e quota della casa; la liquidità resta la sola cifra dei mesi di autonomia
- [ ] #7 Le schede della Guida per trattenuto e investito, TWR, MWR e rateo
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Forma: docs/architettura.md e docs/investments.md — core puro, persistenza come sotto-dominio del ledger senza repository, casi d'uso in services/, porte solo verso i sistemi esterni (qui con fonti finte in tests/, come MemoryBank).
1. Sei tabelle nuove in db.SCHEMA, nessuna scrive un posting: instruments (tipo etf|btp|fondo_pensione|immobile, isin, classe, fonte, quota_proprietà, orizzonte, termini), instrument_trades, pension_contributions (trattenuto|investito), prices (un valore per strumento e fine mese, con la fonte), expected_flows (cedole, premio, PAC), portfolio_snapshots (mese, strumento, quote, valore, versato). La tabella documents resta a TASK-96 (Paperless).
2. Core puro (core/portfolio.py, core/returns.py): calendario cedole del BTP e rateo (4,10% i primi tre anni, 4,50% gli ultimi due, 12,5% di imposta, premio dello 0,5% solo alla scadenza); la macchina trattenuto→investito con abbinamento per importi in ordine e la conservazione trattenuto = investito + in transito; le quattro riconciliazioni come funzioni da due liste a differenze, senza correggere; la valutazione per strumento a fine mese; TWR a catena; MWR con un cercatore di radice a intervallo (non solo Newton); patrimonio complessivo.
3. Porte in ports/portfolio.py: il broker, i documenti, il valore quota del fondo; tipi ed errori di dominio, nessuno del fornitore. Fonti finte in tests/ per questa fetta; quelle vere sono TASK-96.
4. Persistenza: ledger/portfolio.py, PortfolioMixin. Casi d'uso in services/portfolio.py: leggere i documenti nuovi, sincronizzare il broker, scattare lo snapshot di un mese, ricalcolare le riconciliazioni.
5. API in sola lettura: GET /api/portfolio (posizioni, transito, riconciliazioni, TWR e MWR, patrimonio di fine mese); API_VERSION 45 con REQUIRED_API_VERSION. Sezione Portafoglio sotto Gestione. La liquidità resta la sola cifra dei mesi di autonomia: nulla del portafoglio entra in compute_metrics.
6. Schede della Guida: trattenuto e investito, TWR, MWR, rateo.
7. Test con flussi scritti a mano di cui il risultato è noto (TWR, MWR, rateo, conservazione); un test che spesa, mesi di autonomia e verifica 5.4 non cambiano con il portafoglio pieno; suite da checkout pulito; UI in Chromium su un ledger sintetico popolato dagli stessi casi d'uso con le fonti finte.
8. Spec 1.49, docs/investments.md, CLAUDE.md (venticinque tabelle).
<!-- SECTION:PLAN:END -->
