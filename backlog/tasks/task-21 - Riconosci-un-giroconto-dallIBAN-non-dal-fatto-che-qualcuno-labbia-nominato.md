---
id: TASK-21
title: 'Riconosci un giroconto dall''IBAN, non dal fatto che qualcuno l''abbia nominato'
status: Done
assignee: []
created_date: '2026-09-13 12:15'
updated_date: '2026-09-13 12:16'
labels: []
dependencies: []
ordinal: 20500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il matcher confrontava la sola presenza di un conto controparte, mai l'IBAN: due accrediti dello stesso importo nello stesso giorno erano un sorteggio, e sul ledger reale il 17 agosto il sorteggio e' caduto sull'accredito sbagliato. La prova diventa l'IBAN che ciascuna banca stampa sulla propria gamba, e per averla il sync legge i dettagli del conto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una gamba che nomina un conto diverso da quello dell'altra rifiuta la coppia, anche quando l'altra la corrobora
- [x] #2 Con due accrediti dello stesso importo nello stesso giorno il matcher sceglie quello che nomina il conto mittente e lascia l'altro sul libro (verificato sul ledger reale il 17 agosto)
- [x] #3 Se una sola gamba identifica il conto dell'altra la coppia si crea lo stesso, con metodo amount-date-counterparty-one-sided
- [x] #4 Se l'IBAN del conto non e' noto la coppia ricade su chi nomina una controparte e il metodo lo dichiara (unverified), senza spacciarsi per corroborata
- [x] #5 L'IBAN del conto si legge da GET /accounts/{uid}/details e il sync lo registra quando manca, senza sovrascrivere altro e senza far fallire il sync se la banca non risponde
- [x] #6 La card della coda mostra il metodo in italiano e la confidenza, e le etichette coprono tutti i metodi che il backend emette
- [x] #7 Nessuna regressione sul ledger reale: gli otto accoppiamenti confermati restano intatti, la spesa di agosto non cambia (2.934,61 EUR), il clearing netta a zero e validate passa
- [x] #8 Otto test nuovi (matcher, sync, provider) e suite completa verde (277); build tsc e vite pulita
- [x] #9 Specifica alla 0.4 (5.3 e 9) con CLAUDE.md e web/README aggiornati
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
L'IBAN del conto non era nel ledger: la sessione Enable Banking restituisce per ogni conto solo uid, identification_hash e identification_hashes, quindi normalize_account non aveva niente da leggere e accounts.iban restava vuoto su tutti e tre i conti reali. Verificato dal vivo con una sonda usa e getta su /sessions/{id}: niente account_id. /accounts/{uid}/details invece risponde account_id.iban, e per i due Revolut gli IBAN trovati coincidono con quelli che avevo dedotto dai movimenti (chi nomina chi). Fineco resta senza IBAN (consenso scaduto) e senza controparte sulle gambe, quindi non perde niente.

Il caso reale: il 17 agosto 2026 il conto cointestato ha due accrediti da 350,00, uno da Chiara (IT14J...) e uno dal conto personale (IT68C...). Il vecchio matcher li pesava uguali e ha scelto quello di Chiara, che l'utente aveva anche confermato. Con il confronto IBAN la gamba 205 (personale -350,00, controparte IT07Q... = il cointestato) si accoppia con 393 (accredito che nomina IT68C...), e 391 resta sul libro come entrata. Raccontato all'utente: il link esistente e' una sua conferma, non lo riscrivo io.

Rieseguito da zero sul ledger reale (copia, legami rimossi): riproduce tutti gli accoppiamenti veri e sceglie 205-393, spesa di agosto invariata 2.934,61, clearing 0,00, validate ok. Il nono legame (343-88) riappare solo perche' la copia cancellava anche la riga di un rifiuto dell'utente, cosa che il codice non fa.

Aggiunto anche il caso che prima era rifiutato a priori: se una sola gamba nomina il conto dell'altra, la coppia si crea (peso 80, metodo one-sided). Senza, i giroconti fra una banca che riporta la controparte e una che non la riporta restavano invisibili.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La prova di un giroconto e' l'IBAN che ciascuna banca stampa sulla propria gamba, non il fatto che entrambe ne nominino una. Una gamba che nomina il conto dell'altra e' evidenza, una che ne nomina un altro e' contraddizione e la coppia si rifiuta (la contraddizione batte la corroborazione); una sola gamba che identifica l'altra basta; se l'IBAN del conto non e' noto si ricade sul vecchio conteggio e il metodo lo dichiara (unverified). Perche' la prova esistesse, il sync legge l'IBAN del conto da GET /accounts/{uid}/details (la sessione elenca solo uid) e lo registra quando manca, best-effort. Sul ledger reale il 17 agosto ora si accoppia 205-393 (dal conto personale) invece di 391 (da Chiara), con la spesa di agosto invariata, clearing a zero e validate verde; la card della coda dice l'evidenza in italiano. 277 test, otto nuovi. Il link sbagliato che il ledger porta oggi e' una conferma dell'utente: il cambiamento impedisce di crearlo, non riscrive una decisione umana.
<!-- SECTION:FINAL_SUMMARY:END -->
