---
id: TASK-96
title: Le fonti vere del portafoglio
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-16T20:18:00Z'
updated_date: '2026-11-18T06:05:00Z'
labels: []
dependencies:
  - TASK-95
references:
  - desiderata-monitoring-finanziario.md
  - docs/investments.md
  - https://github.com/LucaPaganin/payslip-parser
type: feature
ordinal: 96000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Quarta fetta della fase 12 (sezione 5.16): sostituisce le sorgenti finte di TASK-95 con quelle vere. I documenti li legge il package payslip-parser (repository privato, seconda fetta, con la sua specifica e il suo backlog): qui si integra come dipendenza, e nessuna fixture derivata da un documento reale entra in questo repository, che è pubblico. Prima di cominciare vanno verificate due cose sulla CLI di Scalable: se restituisce lo storico delle transazioni o solo le posizioni, e se il login regge su un NAS senza interazione.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AmonHen legge da Paperless i documenti di un tipo modificati dopo l'ultima lettura, scarica l'originale e non la copia d'archivio, e non rilegge un documento già letto
- [ ] #2 L'esito torna su Paperless come tag amonhen:importato o amonhen:errore, con le cifre chiave come custom field
- [x] #3 Il valore quota del fondo si legge una volta al mese dalla pagina pubblica della sua classe (Azionario Globale C); se la pagina non si legge l'app chiede il valore a mano invece di saltare il mese
- [x] #4 Il calendario delle cedole nette del BTP Valore si genera da ISIN, nominale e data d'acquisto e si riconcilia con gli accrediti Fineco
- [x] #5 Lo storico dei prezzi di fine mese dell'ETF prima del primo sync si carica una volta sola
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Stesso pattern di TASK-95: core puro, casi d'uso in services/, persistenza nel ledger, adapter dietro le porte di ports/portfolio.py; nessuna fixture da documenti reali entra qui.
A. Fattibile ora, in questo container:
1. payslip-parser come dipendenza git fissata a un tag; il parser si chiama solo dall'adapter documenti, che traduce Payslip/PensionStatement nei tipi di dominio (nessun tipo del parser oltre il bordo). Test della traduzione con oggetti del parser costruiti in memoria, non con PDF.
2. Tabella documents (paperless_id, tipo, letto_il, esito, layout, errore): un documento letto non si rilegge; la porta DocumentSource diventa 'documenti nuovi di un tipo dopo una data' più il write-back dell'esito.
3. Adapter Paperless (API REST): elenco per tipo e modified__gt, download dell'originale (?original=true), tag amonhen:importato / amonhen:errore e custom field con le cifre chiave; testato con HTTP finto (responses). Credenziale chiesta con il modulo sicuro, mai in chat.
4. Dichiarazione degli strumenti da riga di comando (ETF con ISIN, BTP con ISIN, nominale e data d'acquisto, fondo con classe, casa con quota): nessun modulo nell'app, come vuole la 1.46.
5. Calendario del BTP da ISIN, nominale e data d'acquisto con riconciliazione sugli accrediti Fineco (il calcolo c'è da TASK-95; manca il modo di dichiararlo).
6. Storico dei prezzi di fine mese dell'ETF caricato una volta da file, rifiutato la seconda volta.
B. Bloccato, serve una decisione:
7. Valore quota da Borsa Italiana: l'host non è raggiungibile da qui; l'adapter si scrive e si prova solo con la pagina vera (accesso di rete o una copia della pagina).
8. CLI di Scalable nel suo container dietro il wrapper: prima vanno chiarite le due verifiche del task (storico delle transazioni, login senza interazione).
9. Immagine e CI: la dipendenza privata richiede un segreto nella build.
C. Spec 1.50, docs/investments.md, CLAUDE.md, schede della Guida dove nasce un concetto, suite da checkout pulito.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Il criterio della CLI di Scalable (container a parte, wrapper in sola lettura) è passato a TASK-98 su decisione del 18 novembre: le due verifiche richieste non si possono fare dalla sessione cloud.

Verifica (18 novembre): 721 test passati da un checkout pulito, 16 nuovi in tests/test_portfolio_sources.py e 6 in tests/test_portfolio.py. Criterio 3: l'adapter di Borsa Italiana ha letto la pagina vera 4PRGLCA (classe A: 30,331 al 30/10/26) e ha rifiutato la classe C e il mese di settembre; il codice della pagina della classe C non l'ho trovato e va dato con instrument-add --nav-page. Il modulo per il valore a mano è provato in Chromium a 390 e 1280 su una copia sintetica (il mese scritto esce dall'elenco ed entra con fonte 'a mano'; un numero sbagliato dice "'abc' non è un numero"). Criteri 4 e 5: instrument-add del BTP rifiuta i termini mancanti, prices-load si rifiuta la seconda volta (test della CLI); la riconciliazione delle cedole è quella di TASK-95. Criteri 1 e 2 NON spuntati: l'adapter Paperless è provato con un HTTP finto sulla forma documentata dell'API (paginazione, modified__gt, ?original=true, tag e custom field creati al primo uso, l'altro tag tolto), ma l'istanza vera sta sul NAS e da qui non si raggiunge; vanno provati con portfolio-sync sul NAS. Il comando di installazione del Dockerfile è provato in un container con un token finto (il parser si installa, il token non resta in nessun file); il token vero in CI resta da provare al primo tag. La build completa dell'immagine non è provata: deb.debian.org qui è bloccato.
<!-- SECTION:NOTES:END -->
