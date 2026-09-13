---
id: TASK-12
title: 'Giroconti: riconoscibili e gestibili, e le entrate di giugno'
status: Done
assignee: []
created_date: '2026-09-13 09:09'
updated_date: '2026-09-13 09:09'
labels: []
dependencies: []
ordinal: 11500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Una transazione marcata come transfer non era riconoscibile: l'API mandava un flag is_transfer che nessun componente leggeva, la controparte era invisibile, l'annullamento esisteva solo per le coppie ancora da confermare, e un'entrata di denaro proprio non si poteva dichiarare. Inoltre a giugno l'app mostrava 4.442,75 di entrate: 2.600 erano la ricarica Revolut fatta dall'utente stesso dal conto stipendio, che non e' collegato ne' dichiarato in own_accounts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una riga di giroconto dice a cosa e' attaccata: il conto dell'altra gamba per una coppia, il nome del conto proprio per una gamba sola, con lo stato proposto o confermato; il conto di clearing non esce mai dall'API
- [x] #2 GET /api/transactions accetta transfer=true|false e il filtro in Movimenti restringe ai giroconti o li esclude
- [x] #3 La scheda di un giroconto conferma o annulla, anche per una coppia gia' confermata; l'annullamento di una coppia conserva la riga del link, cosi' il matcher non la ripropone al sync successivo
- [x] #4 Un movimento si registra verso un conto proprio non collegato e due gambe si abbinano a mano; l'abbinamento manuale accetta solo cio' che il matcher accetterebbe (conti reali diversi, importi opposti, nessuna split da perdere)
- [x] #5 Un'entrata registrata come giroconto esce dalle Entrate e l'annullamento la rimette (giugno 4.442,75 -> 1.842,75 -> 4.442,75)
- [x] #6 L'annullamento dice quando un'etichetta di own_accounts rimettra' la gamba al prossimo sync
- [x] #7 API_VERSION e REQUIRED_API_VERSION allineati a 6, con il campo transfer al posto di is_transfer
- [x] #8 Suite verde e verifica dal vivo su una copia del ledger reale: filtro, chip con la controparte, proposta confermata dal browser, coda 1 -> 0, etichette senza duplicati
- [x] #9 README, CLAUDE.md e web/README aggiornati, incluso che un rimborso conta come entrata finche' non viene registrato come giroconto
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verificato dal vivo su una copia del ledger reale (dumps/verify21.db, poi cancellata) con il server avviato e un browser headless a 390px: il filtro Giroconti elenca 45 gambe a giugno con il chip che nomina la controparte; la ricarica da 2.600 registrata come giroconto verso Conto stipendio porta le Entrate di giugno da 4.442,75 a 1.842,75 e l'annullamento le riporta a 4.442,75; una coppia proposta a mano sul DB (2 x 1.234,00) appare con il chip Da confermare, la scheda mostra la gamba opposta e la Conferma svuota la coda (transfers_total 1 -> 0); la lista delle etichette non ha piu' duplicati dopo la correzione (era 'Conto deposito senza vincoli' due volte, config + registrata). Un test ha trovato un difetto vero: riabbinare una coppia rifiutata confermava la riga senza rimettere le gambe fuori dalla spesa. Revisione visiva con modello di visione: nessun difetto nella scheda.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Un giroconto ora e' riconoscibile e gestibile: la riga dice quale conto tiene l'altra meta' (o quale conto proprio e' stato registrato) con lo stato proposto/confermato, il conto di clearing non esce mai dall'API, un filtro restringe ai giroconti, e dalla riga si conferma, si annulla, si registra un movimento verso un conto proprio non collegato o si abbinano due gambe - solo con le coppie che il matcher stesso accetterebbe. Serve al caso di giugno: le Entrate contavano 2.600 euro di ricarica Revolut fatta dall'utente stesso, perche' il conto stipendio non e' collegato ne' dichiarato; ora quel movimento si registra come giroconto e la voce scende a 1.842,75. API_VERSION 6: il campo transfer sostituisce is_transfer. Verificato con 257 test e dal vivo sul ledger reale (filtro, chip, conferma di una proposta, annullamento, etichette senza duplicati).
<!-- SECTION:FINAL_SUMMARY:END -->
