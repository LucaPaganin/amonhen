---
id: TASK-95
title: Il portafoglio si ricostruisce dalle fonti, su dati finti
status: To Do
assignee: []
created_date: '2026-11-16T20:18:00Z'
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
