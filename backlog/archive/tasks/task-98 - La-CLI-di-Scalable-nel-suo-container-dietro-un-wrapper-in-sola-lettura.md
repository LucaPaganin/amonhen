---
id: TASK-98
title: La CLI di Scalable nel suo container, dietro un wrapper in sola lettura
status: To Do
assignee: []
created_date: '2026-11-18T05:53:00Z'
updated_date: '2026-11-18T07:05:00Z'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Dalla documentazione ufficiale della CLI (github.com/ScalableCapital/scalable-cli: README, public-docs/commands.md, configuration.md, automation.md), letta il 18 novembre 2026, non ancora provata:
- La CLI è 'sc', Apache-2.0, binari Linux x86_64 e aarch64 che richiedono glibc 2.38 o più (Debian 12 no, Alpine no): l'immagine del container va scelta di conseguenza (Debian 13 o Ubuntu 24.04).
- Login: 'sc login' con device code OAuth nel browser, dichiarato 'human-oriented'. Va abilitata prima in Profilo → Sicurezza → Agentic Investing. Token di 20 minuti rinnovato da solo, scadenza per inattività di 24 ore (le letture la azzerano), durata massima 7 giorni dal login, che il rinnovo non estende. Quindi il login NON regge senza interazione: serve rifare 'sc login' a mano almeno ogni 7 giorni. Su un server senza Secret Service: [auth] session_backend = "file" in ~/.config/scalable-cli/config.toml.
- Storico: 'sc broker transactions --json' con paginazione '--cursor' e dettaglio 'sc broker transaction details --transaction-id'. Filtri per data, profondità dello storico e campi non documentati: vanno visti sul vero output.
- Posizioni: 'sc broker holdings --json' (campi non documentati). Liquidità: 'sc broker cash-breakdown --json'. Prezzi storici: 'sc broker candlesticks --isin --timeframe max --json' (OHLC), da cui si ricava la chiusura di fine mese; non c'è un comando di fine mese.
- Scritture da bloccare nel wrapper: trade buy/sell/cancel, savings-plans add/remove, watchlist add/remove, price-alerts add/remove, portfolio-groups create/update/delete/assign/unassign, context select, login/logout. Nessuno scope di sola lettura lato piattaforma; 'sc login --local-read-only' blocca le scritture solo localmente. Il wrapper resta quindi necessario: una allowlist di comandi di lettura, non una denylist.
- 'sc capabilities --json' dà l'elenco dei comandi della versione installata; la compatibilità del JSON fra versioni non è garantita.
Restano da provare con l'account vero: la profondità di 'sc broker transactions' e i suoi campi, e come si vive con il login da rifare ogni 7 giorni (un avviso nell'app quando la sessione scade).

Annullata il 18 novembre 2026 (specifica 1.51): la CLI del broker esce dal sistema. Login da rifare a mano almeno ogni 7 giorni, storico delle transazioni senza filtri né profondità documentati, nessun permesso di sola lettura sulla piattaforma. Al suo posto: i contratti e l'estratto titoli del broker letti da payslip-parser via Paperless (task del template), e il prezzo di fine mese dell'ETF da Borsa Italiana.
<!-- SECTION:NOTES:END -->
