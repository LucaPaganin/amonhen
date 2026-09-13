---
id: TASK-8
title: 'Coda: proposte in cima, stati per riga e filtro'
status: Done
assignee: []
created_date: '2026-09-12 18:34'
updated_date: '2026-09-12 18:34'
labels: []
dependencies: []
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nella coda le proposte contano, il mucchio no: le proposte vanno in cima, ogni riga del backlog dichiara cosa hanno già provato regole, classificatore e giroconti, l'elenco ha un filtro (stato, testo, conto) e le spese che nessun automatismo ha preso sono segnalate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Nella coda le proposte stanno per prime, poi i giroconti, poi il backlog senza categoria
- [x] #2 Ogni riga del backlog dichiara cosa ha già provato: «proposta: <categoria>» oppure la pillola ambra «sfuggita a regole, proposte e giroconti»
- [x] #3 Filtro sull'elenco applicato dall'API: chip di stato (Tutte / Con proposta / Sfuggite), ricerca testuale case-insensitive, select del conto con i soli conti che hanno righe in coda
- [x] #4 I conteggi dei chip sono il backlog reale e non dipendono dal filtro; il badge della scheda conta le decisioni (proposte + giroconti) e il sottotitolo riporta il resto
- [x] #5 Verifica: 203 test verdi, più prova in browser a 390 px su una copia del ledger reale (ordine, filtro stato, ricerca, filtro conto, categorizzazione end-to-end con i contatori aggiornati dal server)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- `GET /api/review` guadagna `state`, `account_id` e `search`, e restituisce `review_state` e `proposed_category` per riga, più `uncategorized_total`, `proposed_total`, `unhandled_total`, `proposals_total` e la lista `accounts` del filtro. Una riga che arriva nel backlog ha già perso il confronto con il matcher dei giroconti (il linking sposta il posting sul conto di clearing), quindi l'unico automatismo ancora da interrogare è il classificatore: `proposed` = esiste una proposta in attesa per quel merchant, `unhandled` = nessuno l'ha preso.
- La passata leggera sul backlog legge solo `id, description, account_id`: un backlog lungo non deve trascinarsi dietro ogni `raw_payload` solo per essere contato. La pagina poi è una sola query `id IN (…)` sugli id già filtrati e ordinati.
- Il badge della scheda prima contava tutto il backlog (336): ora conta le decisioni, perché il backlog non è una coda di decisioni. Sottotitolo: «30 da decidere · 329 senza categoria, di cui 188 sfuggite».
- Numeri reali al momento della verifica: 330 in coda, 141 con proposta, 189 sfuggite, 24 proposte in attesa.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La coda ora apre con quello che conta: proposte da accettare o rifiutare, poi i giroconti candidati, poi il backlog dei movimenti senza categoria. Ogni riga del backlog dichiara cosa hanno già provato gli automatismi — «proposta: <categoria>» se il classificatore ha proposto qualcosa per quel merchant, altrimenti la pillola ambra «sfuggita a regole, proposte e giroconti» — e le sfuggite sono le uniche che restano da smistare a mano. L'elenco ha un filtro applicato dall'API (chip Tutte/Con proposta/Sfuggite, ricerca testuale case-insensitive, select del conto con i soli conti presenti in coda) mentre i conteggi dei chip restano il backlog intero: un filtro non deve far sembrare il lavoro più piccolo. Il badge della scheda non conta più tutto il backlog ma le decisioni (proposte + giroconti), e il sottotitolo riporta il resto. Numeri reali: 330 in coda, 141 con proposta, 189 sfuggite, 24 proposte in attesa. Verifica: 203 test, più prova in browser a 390 px su una copia del ledger reale — ordine dei pannelli, filtro stato (50 righe tutte segnalate), ricerca «aSPiT» (21 righe, case-insensitive), filtro conto (50 righe tutte del conto scelto) e categorizzazione end-to-end con i contatori aggiornati dal server (330→329, 189→188).
<!-- SECTION:FINAL_SUMMARY:END -->
