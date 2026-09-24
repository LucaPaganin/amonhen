---
id: TASK-47
title: 'Il cestino: vedere e ripristinare a mano un movimento cancellato'
status: Done
assignee: []
created_date: '2026-09-24 18:39'
updated_date: '2026-09-24 20:10'
labels: []
dependencies:
  - TASK-45
references:
  - amonhen/api.py
  - amonhen/ledger.py
  - web/src/screens/Accounts.tsx
  - web/src/useAccounts.ts
documentation:
  - doc-1
type: feature
ordinal: 46500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il tombstone e una traccia, ma senza un posto dove guardarla l'unico modo di correggere una cancellazione sbagliata e il database. Il cestino sta dove sta la flag che lo riguarda (il conto, nel pannello Conti) e offre il ripristino di una riga sola, che e il gesto che la flag per conto non puo dare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 I movimenti cancellati di un conto si vedono raggruppati sotto il conto, con data, importo, descrizione, nota e quando sono stati cancellati
- [x] #2 Il ripristino di una riga la rimette nel ledger dal payload conservato, con la nota, e la toglie dall'elenco
- [x] #3 Un secondo ripristino dello stesso tombstone e rifiutato, e il ripristino non duplica un movimento che il ledger gia tiene (identita)
- [x] #4 Dopo il ripristino la verifica del conto torna a valere, o dice perche non torna
- [x] #5 La versione dell'API sale e la specifica, dove descrive il ripristino, resta vera
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ledger.restore_deleted ricostruisce il movimento dal tombstone (payload compreso, via IncomingTransaction) e lo riscrive con la stessa impronta; _mark_restored gli ridà la nota del tombstone solo se la riga non ne ha una (una nota piu recente non si sovrascrive) e segna restored_at. deleted_transactions() elenca solo restored_at IS NULL, con il nome del conto. API: GET /api/deleted, POST /api/deleted/{id}/restore (404 se non esiste, 409 se era gia tornato); API_VERSION 15 -> 16.
<!-- SECTION:NOTES:END -->
