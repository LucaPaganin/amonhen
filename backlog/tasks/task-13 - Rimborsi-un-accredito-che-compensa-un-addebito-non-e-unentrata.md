---
id: TASK-13
title: 'Rimborsi: un accredito che compensa un addebito non e'' un''entrata'
status: Done
assignee: []
created_date: '2026-09-13 10:05'
updated_date: '2026-09-13 15:05'
labels: []
dependencies: []
ordinal: 12500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi le Entrate contano ogni accredito BOOK su un conto reale senza postings virtuali, quindi un rimborso appare come entrata. Su giugno 2026, dopo aver registrato la ricarica da 2.600 come giroconto, ne restano 1.842,75 e sono tutti di questo tipo: 807,00 (Telefono cellulare, From Marco P) e 420,75 (GADMALAT). Il desiderata lo mette in fase 3. Decisione da prendere: come si riconosce un rimborso (stesso esercente e importo opposto entro N giorni da un addebito, categoria dedicata, marcatura a mano come per i giroconti) e se debba uscire dalle Entrate o restare visibile a parte.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un accredito che non è entrata esce dalle Entrate e resta visibile col nome della sua destinazione
- [x] #2 La dichiarazione sta in accounts.json: una destinazione, i testi che la banca stampa su quei movimenti, e incoming_only per chi non è il titolare
- [x] #3 Un'etichetta incoming_only non tocca il denaro che esce con lo stesso nome: il premio resta spesa
- [x] #4 La decisione è presa sui dati: nessuno degli accrediti di un mese di prova ha un addebito di pari importo, quindi la coppia con l'addebito compensato non si modella
- [x] #5 Verificato sul ledger vero: la voce esce dalle Entrate, la categoria del movimento non viene toccata e i totali di spesa non si muovono
- [x] #6 Quattro test nuovi (destinazione con più testi, direzione, quote, metrica mensile) e suite verde a 299
- [x] #7 Specifica 3, 5.3 e 10, README e CLAUDE.md aggiornati
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il denaro che non è né spesa né entrata si dichiara invece di indovinarlo: una voce passthrough in accounts.json nomina la destinazione (il conto virtuale in cui finisce il lato non reale) e i testi che la banca stampa su quei movimenti, con incoming_only per le etichette che nominano una persona o una ditta. L'euristica della coppia è stata scartata sui dati: negli accrediti di prova nessuno ha un addebito di pari importo, quindi quello che li accomuna è chi li manda. Sul ledger vero la voce esce dalle Entrate e la categoria dei movimenti resta com'era; nessun numero di spesa si muove.
<!-- SECTION:FINAL_SUMMARY:END -->
