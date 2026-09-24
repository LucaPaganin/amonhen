---
id: TASK-50
title: Specifica e CLAUDE.md allineati alla fase 6
status: Done
assignee: []
created_date: '2026-09-24 18:39'
updated_date: '2026-09-24 20:24'
labels: []
dependencies:
  - TASK-43
  - TASK-44
  - TASK-45
  - TASK-46
  - TASK-47
  - TASK-48
  - TASK-49
references:
  - desiderata-monitoring-finanziario.md
  - CLAUDE.md
  - README.md
documentation:
  - doc-1
type: docs
ordinal: 49500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le decisioni di questa fase (nota locale, cancellazione con tombstone, flag di reimport per conto, differenza spiegata della §5.4, immagine costruita in CI e tirata dal NAS) devono stare nella fonte del prodotto, o la fetta successiva implementa il prodotto vecchio. Un solo proprietario scrive la specifica, cosi la riga di versione e §9 non cambiano sotto i piedi di nessun altro task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La specifica sale di versione con la riga che dice cosa e cambiato, e §9 elenca la fase 6 con il suo stato e i suoi criteri di fatto
- [x] #2 §5.1 e §6 dicono che `notes` e locale, che un movimento si cancella in un tombstone, che una flag per conto decide il reimport e che il cestino ripristina
- [x] #3 §5.4 dice cosa significa una differenza spiegata dai movimenti cancellati, e cosa resta un mismatch
- [x] #4 CLAUDE.md aggiorna mappa dei file, schema del ledger e le voci non ovvie (la nota fuori dal percorso del sync, la soppressione per identita, il guardiano del sync, la flag, il cestino, il deploy)
- [x] #5 Nessuna decisione di questa fase resta fuori da entrambi i documenti
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Specifica a 1.3: riga di changelog, §5.1 (cancellazione con tombstone, flag di reimport per conto, cestino e ripristino), §5.4 (i quattro esiti e la differenza spiegata), §6 (notes locale, deleted_transactions, ripristina_cancellati), §9 (fase 6 con i suoi criteri e la stato aggiornato). CLAUDE.md: tabella dello schema con i conteggi verificati contro PRAGMA table_info (accounts 13, transactions 16, deleted_transactions 18, dodici tabelle, IncomingTransaction 13 campi, Transaction 15 chiavi), mappa dei moduli (SyncBusy, Deletion, DeletedTotal), tabella dei compiti comuni (sync dall'app, nota, ripristino, deploy), quattro voci non ovvie nuove (la nota e locale e fuori dal percorso del sync; cancellare e una scrittura con memoria, con l'identita esatta; il ritorno di una cancellazione e per conto e una riga alla volta; il sync ha un guardiano e un pulsante), la nota sull'immagine riscritta per la CI, e l'invariante 5.4 estesa al quarto stato.
<!-- SECTION:NOTES:END -->
