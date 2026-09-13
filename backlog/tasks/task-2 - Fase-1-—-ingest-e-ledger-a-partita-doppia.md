---
id: TASK-2
title: Fase 1 — ingest e ledger a partita doppia
status: Done
assignee:
  - '@luca'
created_date: '2026-09-12 12:07'
updated_date: '2026-09-12 12:37'
labels:
  - phase-1
dependencies:
  - TASK-1
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il sistema possiede il proprio ledger SQLite a postings (somma a zero per movimento) e ingerisce da due percorsi convergenti: sync PSD2 e import di export storici CSV/OFX (necessario per il backfill a 24 mesi, dato che le API coprono ~90 giorni). Idempotenza via external_id del provider, fallback hash(data, importo, descrizione, conto). Payload grezzo conservato. Vedi §5.1, §5.2, §5.4, §6 e §9 Fase 1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Schema SQLite a postings con vincolo SUM(postings.importo)=0 per transaction_id
- [x] #2 Modulo di integrazione Enable Banking normalizza verso lo schema comune e scrive nel ledger, verificato contro le fixture della Fase 0
- [x] #3 Un adattatore per formato di export importa CSV/OFX e converge nella stessa tabella con la stessa logica di dedup
- [x] #4 La transizione pending → booked non duplica la transazione
- [x] #5 L'assert saldo_iniziale + Σ movimenti == saldo dichiarato passa su ogni conto
- [x] #6 Reimportare un periodo già sincronizzato non genera duplicati (test esplicito)
- [x] #7 Una query risponde a 'quanto è uscito davvero il mese scorso, esclusi giroconti'
- [x] #8 Il payload grezzo è conservato con indicazione del percorso di provenienza
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Fondamenta: package finance_monitor (settings, modelli, schema SQLite a postings, Ledger con invariante somma-zero e conti categoria/virtuali).
2. Provider Enable Banking: client di fetch (JWT, paginazione, rate limit) e normalizzazione verso il tipo comune, verificato contro le fixture fase 0.
3. Adattatori di import: CSV guidato da profilo per istituto + OFX, stessa tabella e stessa dedup del percorso PSD2.
4. Sync service: dedup external_id + hash di fallback, promozione pending→booked senza duplicati, payload grezzo con provenienza.
5. Riconciliazione deterministica dei giroconti (sottoinsieme di 5.3) e query "speso il mese scorso esclusi giroconti".
6. Assert saldi (5.4) + CLI (sync, import, balance-check, spend).
7. Cutover: rimozione del percorso Actual (actualpy, patch, state.json, scheduler Flask) dal branch a ingest nuovo funzionante.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementazione (commit bd79b73):
- Ledger: `finance_monitor/ledger.py` con postings a somma zero, promozione pending→booked su (conto, importo, ±3 giorni), conto virtuale "Transfer clearing" per i giroconti, conti categoria, `validate()`, `spend_between()`, `movement()`/`balance()`/`check_balance()`, `record_declared_balance()`.
- Dedup a due livelli: `external_id` prima, `content_hash(conto, data, importo, descrizione)` come fallback normalizzato (spazi/case) condiviso da PSD2 e import. L'hash NON è un vincolo UNIQUE: dati reali contengono transazioni identiche nello stesso giorno (4 ricariche da 250 € il 2026-08-29 in Revolut personale) con entry_reference distinti; un indice UNIQUE le scartava, ora il duplicato di contenuto con id diverso viene inserito con hash suffissato.
- Verifica live (dump/phase1-verify.db, post-cutover.db): 306+132 transazioni PSD2 inserite e bilanciate, ri-sync di 13 righe → solo duplicati, 0 inserimenti; import di 79 righe da export Actual → 78 inserite (il periodo Aprile-Maggio non si sovrappone perché l'API PSD2 ha restituito solo dal 2026-06-14 nonostante la richiesta dal 2026-01-01, confermando la premessa della desiderata sul backfill).
- Assert saldi (§5.4) verificato live su entrambi i conti raggiungibili: Revolut personale 67.56 ITAV e Revolut cointestato 153.44 ITAV, difference=0.00, con `anchor` idempotente. Fineco: consenso 401/403, percorso di recupero = import (non verificabile live).
- Query "speso il mese scorso esclusi giroconti": `monitor spend --month 2026-08` → 5276.74 EUR; maggio 2026 → 905.34 EUR (solo grazie al backfill).
- Cutover: rimossi bank_connector, connector.py, fetch.py, import_json.py, test_auth.py, state.json, i test del percorso Actual, le dipendenze actualpy/flask/apscheduler/rich/python-dotenv. Aggiornati Dockerfile/compose/.env.example/README/CLAUDE.md/accounts.example.json.
- `uv run pytest`: 76 passed.

Verifica indipendente (reviewer + security-reviewer) e correzioni:
- Difetti trovati e corretti (commit a2d4b1a): (1) anchor/balance-check confrontavano il ledger a --as-of con un saldo dichiarato di data precedente, assorbendo i movimenti intermedi nell'apertura e rendendo l'assert 5.4 falsificabile solo in apparenza; ora la data del saldo dichiarato decide il confronto e viene stampata. (2) Il matcher dei trasferimenti appaiava su importo+data senza corroborazione: sui dati reali una fattura SEPA di 183,00 € a un fornitore veniva appaiata a un incasso di 183,00 € e spariva dalla spesa (giugno: 6269,80 → 6452,80 corretti); ora un solo lato con conto controparte = coincidenza e non si appaia; confidenza high solo con entrambi i lati corroborati. (3) Due righe identiche nello stesso file di import collassavano in una, perdendo un pagamento Trenitalia reale di 25,60 €: `record_batch` numera le occorrenze, il reimport resta idempotente. Inoltre l'assert 5.4 ora gira dentro `sync` (fallisce nominando il conto) invece di dipendere da un comando manuale.
- Sicurezza: l'anonimizzazione delle fixture era reversibile (sale committato): sale ora in `dumps/.anonymize-salt` (gitignorato) o `MONITOR_ANON_SALT`, fixture rigenerate, nessun importo/data originale sopravvive (verifica posizionale). Rimossi nomi reali, hostname Tailscale privato e percorsi personali dai file tracciati; `monitor.db` gitignorato; permessi 0600 sul file del ledger; `pem_path` risolto rispetto ad accounts.json; un 401 e un 403 ora dicono cose diverse; 429 esaurito o errore di rete non abortiscono gli altri conti.
- Limiti dichiarati (README): la spesa esclude solo i giroconti tra conti tracciati (i flussi verso il conto deposito Revolut restano spesa finché quel conto non è tracciato: metrica di risparmio, fase 3); il matcher è il sottoinsieme greedy di 5.3 (fase 2 lo sostituisce); il profilo CSV Revolut non legge la colonna State (nessun export reale disponibile per verificarlo).
- `uv run pytest`: 84 passed. Verifica live su dumps/verify2.db: 438 righe PSD2 bilanciate, import 79/79 (entrambe le righe Trenitalia), assert saldi 0.00 su entrambi i conti dopo l'anchor, sync che fallisce con mismatch prima dell'anchor.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fase 1 completata: il sistema possiede il proprio ledger SQLite a partita doppia (postings a somma zero, conto di clearing per i giroconti, conti categoria) e due percorsi di ingest convergenti — sync PSD2 e import CSV/OFX — con dedup per external_id e hash di contenuto, promozione pending→booked, payload grezzo e provenienza per riga. Il percorso Actual (actualpy, patch, state.json, Flask, scheduler) è uscito dal branch. CLI: sync, daemon, import, spend, balances, anchor, balance-check, validate.

Verifica: 84 test; live su due conti Revolut 438 righe PSD2 + 79 righe di export storico, ri-sync e reimport senza duplicati, assert 5.4 a differenza 0.00 su entrambi i conti (e fallimento esplicito prima dell'anchor), backfill Aprile-Maggio che conferma il limite ~90 giorni dell'API. Review indipendenti (codice e sicurezza) hanno prodotto 8 finding: corretti i 5 azionabili, documentati i limiti di fase.
<!-- SECTION:FINAL_SUMMARY:END -->
