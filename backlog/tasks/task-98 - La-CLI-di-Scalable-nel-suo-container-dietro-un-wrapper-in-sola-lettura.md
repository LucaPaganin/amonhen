---
id: TASK-98
title: La CLI di Scalable nel suo container, dietro un wrapper in sola lettura
status: To Do
assignee: []
created_date: '2026-11-18T05:53:00Z'
updated_date: '2026-11-18T05:53:00Z'
labels: []
dependencies:
  - TASK-95
type: feature
ordinal: 98000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Separata da TASK-96 il 18 novembre 2026: prima di costruirla vanno chiarite due cose che dalla sessione cloud non si possono verificare — quale CLI ufficiale di Scalable Capital si usa e se restituisce lo storico delle transazioni o solo le posizioni, e se il suo login regge su un NAS senza interazione. Se lo storico manca, lo storico del PAC si ricostruisce dai bonifici che il ledger già vede e la CLI riconcilia le quote con la posizione (sezione 5.16). La porta c'è già: BrokerSource in amonhen/ports/portfolio.py, con MemoryBroker nei test; questa fetta scrive l'adapter vero.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le due verifiche (storico delle transazioni, login senza interazione) sono scritte nel task con l'esito
- [ ] #2 La CLI gira in un container a parte e AmonHen la chiama solo attraverso un wrapper che espone posizioni, transazioni, liquidità e prezzi; nulla che prepari un ordine è raggiungibile dal processo di AmonHen
- [ ] #3 Un adapter implementa BrokerSource sopra il wrapper, con i tipi e gli errori della porta
<!-- AC:END -->
