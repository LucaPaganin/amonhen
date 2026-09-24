---
id: TASK-45
title: 'Cancellare un movimento lo sposta in un tombstone, e il sync non lo rimette'
status: Done
assignee: []
created_date: '2026-09-24 18:38'
updated_date: '2026-09-24 19:57'
labels: []
dependencies:
  - TASK-44
references:
  - amonhen/ledger.py
  - amonhen/db.py
  - amonhen/models.py
  - amonhen/transfers.py
documentation:
  - doc-1
type: feature
ordinal: 44500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Una riga sbagliata o doppia resta nel ledger e continua a contare nelle metriche; cancellarla a mano dal database e l'unica via, e il sync successivo la riporta indietro. Serve una cancellazione vera dall'app, che ricordi cosa e stato cancellato (con la sua nota, il payload grezzo e l'identita) e che tenga il sync dal rimetterlo senza che nessuno lo abbia deciso. L'identita del tombstone e quella che il ledger gia usa per deduplicare: identificativo della banca quando c'e, altrimenti l'impronta di contenuto nella forma esatta in cui la riga e stata scritta, suffissi delle ripetizioni compresi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `DELETE /api/transactions/{id}` copia la riga (identita, data, importo, descrizione, stato, sorgente, payload grezzo, nota) in `deleted_transactions` e la toglie dal ledger con le sue gambe, in una sola transazione
- [x] #2 Cancellare una gamba di un giroconto rifiuta il link e riporta l'altra gamba su Uncategorized prima di cancellare, cosi nessuna gamba resta appesa al conto di clearing senza partner; la risposta dice che e successo
- [x] #3 Un sync che riporta lo stesso movimento non lo reinserisce: il tombstone lo sopprime per identita e l'esito lo conta fra i soppressi invece di tacerlo
- [x] #4 La soppressione non tocca i movimenti diversi: due accrediti identici nello stesso giorno, uno cancellato e uno no, lasciano quello vivo nel ledger
- [x] #5 Cancellare un movimento in attesa (`PDNG`) sopprime anche il `BOOK` che la banca manda dopo, quando porta la stessa identita
- [x] #6 Un id inesistente e 404; regole, proposte e budget non vengono toccati dalla cancellazione
- [x] #7 La specifica descrive la cancellazione e il tombstone (§5.1, §6) e la versione dell'API sale
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Schema: deleted_transactions (chiave = external_id se c'e, altrimenti il content_hash come la riga lo portava, suffissi delle ripetizioni compresi; payload grezzo, nota, stato, cancellato_il, ripristinato_il; UNIQUE(account_id, key)). RecordAction guadagna "suppressed"; Ledger.record lo restituisce con id 0, perche niente e stato scritto.
<!-- SECTION:NOTES:END -->
