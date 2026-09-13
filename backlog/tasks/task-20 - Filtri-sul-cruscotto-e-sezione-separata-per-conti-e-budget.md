---
id: TASK-20
title: Filtri sul cruscotto e sezione separata per conti e budget
status: Done
assignee: []
created_date: '2026-09-13 11:12'
updated_date: '2026-09-13 11:34'
labels: []
dependencies: []
ordinal: 19500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il cruscotto mostra serie fisse: non si puo' chiedere 'le spese di queste due carte negli ultimi 6 mesi' ne' guardare un solo conto. Serve una barra di filtri (periodo, conti, categorie) che piloti cio' che i grafici mostrano. Inoltre conti e budget si gestiscono oggi dentro il cruscotto, mescolati alle metriche: serve una sezione separata dove controllarli. Le scelte di prodotto da fissare prima di implementare: se il periodo scelto valga solo per i grafici o anche per le card delle metriche (che oggi hanno finestre proprie di 6 e 24 mesi), e quali azioni debba offrire la sezione (creare conti e categorie? dichiarare saldi? solo flag e budget?).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il cruscotto si filtra per periodo, conti e categoria, e i tre filtri non pesano uguale: il periodo muove grafici e serie, i conti restringono spesa, liquidita', risparmio e patrimonio, la categoria solo la spesa
- [x] #2 Ogni risposta filtrata dichiara cosa ha applicato in applied; /api/spending non ha piu' month e /api/flows non ha piu' months
- [x] #3 Le card delle metriche seguono conti e categorie ma non il periodo, e ognuna dichiara la finestra di 6 o 24 mesi che ha usato
- [x] #4 La sezione Conti e budget elenca i conti con saldo, figura iniziale ed esito della verifica, i budget del mese scelto e i flag delle categorie
- [x] #5 Un saldo dichiarato dall'app fa dire alla riga e al toast se banca e ledger concordano; allineare il saldo iniziale deriva l'apertura da quella dichiarazione, con la stessa implementazione di anchor
- [x] #6 Un conto reale si crea a mano e un nome gia' in ledger e' rifiutato con 422; il budget si imposta per il mese selezionato e la risposta descrive quel mese
- [x] #7 API_VERSION e REQUIRED_API_VERSION a 7 e la PWA ha cinque schede che stanno nella barra senza tagli
- [x] #8 Dodici test nuovi coprono filtri e scritture; suite completa verde (269) e build tsc + vite pulita
- [x] #9 Verifica dal vivo sul ledger reale: periodo 12 -> 3 mesi, conto (liquidita' 81,35 -> 0,00), categoria (una fetta da 9.955,32 come l'API, burn 2.369,82 -> 1.995,91), dichiarazione sbagliata -> non torna sui sospesi, giusta -> verificato, nuovo conto, budget, nessun difetto visivo
- [x] #10 Specifica alla 0.3 (§5.6 e §9) e README, CLAUDE.md e web/README aggiornati
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Un sottoagente ha costruito la schermata Conti e budget (useAccounts.ts + Accounts.tsx + un blocco CSS in coda) mentre il cruscotto e la navigazione le facevo io: contratto HTTP e tipi congelati prima di partire, nessun file conteso. La sua revisione ha prodotto quattro attriti, tre risolti qui: il PUT del budget rispondeva sempre per il mese corrente (ora prende month), dichiarare un saldo non poteva dire l'esito della verifica (ora la scrittura ritorna l'Account e il toast dice se banca e ledger concordano), e i due sheet potevano inviare un importo che l'API avrebbe rifiutato in inglese (ora il pulsante resta disabilitato finche' non e' valido, con il meno ammesso perche' un saldo puo' essere negativo). Il quarto — Account non espone institution nella riga — l'ho lasciato: il payload ce l'ha, la riga non lo mostra e nessuno lo usa ancora.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il cruscotto si filtra per periodo, conti e categoria e la sezione Conti e budget gestisce conti, saldi e budget. Il LedgerScope attraversa le letture: il periodo muove grafici e serie, i conti restringono tutto cio' che e' di conto (spesa attribuita al conto che l'ha pagata, liquidita', risparmio, patrimonio), la categoria solo la spesa; le card di §5.6 non seguono il periodo perche' le loro finestre di 6 e 24 mesi sono la definizione della metrica, e ogni risposta filtrata dice cosa ha applicato in applied. La sezione nuova ospita elenco conti con saldo, figura iniziale ed esito 5.4, dichiarazione di un saldo letto dalla banca (l'esito compare nella riga e nel toast), allineamento del saldo iniziale derivato da una dichiarazione (la stessa implementazione di anchor, ora in Ledger.anchor_opening), creazione di un conto reale a mano, budget mensili per categoria e flag delle categorie. API_VERSION 7, cinque schede. Verificato con 269 test, build tsc+vite pulita e prova dal vivo sul ledger reale: periodo 12 -> 3 mesi, conto (liquidita' 81,35 -> 0,00), categoria (una fetta da 9.955,32 identica all'API, burn 2.369,82 -> 1.995,91), dichiarazione sbagliata -> non torna sui sospesi, dichiarazione giusta -> verificato, conto nuovo e budget, piu' la revisione visiva di cruscotto filtrato e sezione conti.
<!-- SECTION:FINAL_SUMMARY:END -->
