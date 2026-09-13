---
id: TASK-9
title: Coda bianca e burn gonfiato dai giroconti non collegati
status: Done
assignee: []
created_date: '2026-09-12 19:02'
updated_date: '2026-09-12 19:02'
labels: []
dependencies: []
type: bug
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Due difetti trovati dall'uso reale: la coda restava bianca quando il server non era aggiornato, e il burn contava come uscite i soldi spostati su un conto proprio non collegato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un server più vecchio dell'app non fa più sparire la schermata: l'app legge `api_version` da `/api/health` e, se manca o è indietro, mostra cosa è successo e il comando da dare
- [x] #2 I movimenti verso un conto proprio non collegato non contano come uscite: dichiarati in `own_accounts`, il loro lato categoria va su un conto virtuale, fuori da burn, spesa e coda
- [x] #3 La lista mostra la destinazione di quei movimenti invece di «senza categoria», e gli arrivi da quei conti non contano come entrate
- [x] #4 Le proposte pendenti su quel merchant vengono rimosse: nessuno categorizzerebbe mai quei movimenti
- [x] #5 Verifica: 213 test, burn reale 4873,50 → 2369,82, coda 330 → 238 righe, 136 movimenti riclassificati, destinazione visibile in `/api/transactions`
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- **Schermo bianco.** Il bundle viene letto dal disco a ogni richiesta mentre il processo Python può girare codice vecchio: un client nuovo contro un'API vecchia moriva su `data.accounts.length` e React smontava tutto (riprodotto: `.app__main` assente, tab bar a zero). Ora `API_VERSION` in `api.py` viaggia con `/api/health`, `REQUIRED_API_VERSION` in `App.tsx` lo confronta e l'app mostra «Server non aggiornato» con il comando di riavvio. Verificato contro il server vecchio vero, non simulato.
- **Burn.** Enable Banking non espone il conto deposito: la sessione del conto personale elenca solo i due conti già tracciati, quindi quel lato non ha controparte e il pairing non può vederlo. `own_accounts` in `accounts.json` dichiara l'etichetta che la banca stampa sul trasferimento (`Conto deposito senza vincoli`); `link_own_account_transfers` gira dopo `link_transfers` (una coppia vera vince sempre) e sposta il lato categoria su un conto virtuale omonimo. Verificato: 136 movimenti, luglio 4873,50 → 2369,82, coda 330 → 238.
- Il conto virtuale tiene visibile la destinazione: `Ledger.transfer_target` restituisce il nome e l'API lo mostra al posto di una categoria vuota, mentre il clearing generico di una coppia resta nascosto perché è un dettaglio interno.
- Le entrate escludono qualsiasi transazione con un posting virtuale (prima solo le coppie linkate): un acquisto finanziato dal deposito resta spesa, l'arrivo dal deposito non è reddito.
- Rimosso `Ledger.move_to_transfer_clearing`, codice morto, generalizzato in `move_to_virtual_account`.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Due difetti trovati usando l'app davvero. Primo: con un server più vecchio del bundle la coda restava bianca, perché il client nuovo leggeva campi che l'API vecchia non manda e React smontava tutto (riprodotto: .app__main assente, zero tab). Ora l'app chiede api_version a /api/health e, se il server è indietro, mostra una schermata che dice cosa è successo e il comando di riavvio — verificato contro il server vecchio reale. Secondo: il burn contava come uscite i soldi spostati sul conto deposito, che Enable Banking non espone (la sessione elenca solo i due conti tracciati): erano la voce più grossa, 2550+2250+1649+900+… Il conto va dichiarato in own_accounts con l'etichetta che la banca stampa sul trasferimento, e link_own_account_transfers sposta il lato categoria su un conto virtuale omonimo, dopo il pairing così una coppia vera vince sempre. Risultato sui dati reali: 136 movimenti riclassificati, luglio 4873,50 → 2369,82, coda 330 → 238 righe; la lista mostra la destinazione invece di «senza categoria», gli arrivi dal deposito non contano più come entrate, e la proposta pendente su quel merchant è stata rimossa. 213 test.
<!-- SECTION:FINAL_SUMMARY:END -->
