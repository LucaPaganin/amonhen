---
id: TASK-48
title: La §5.4 dice quando la differenza sono i movimenti cancellati a mano
status: Done
assignee: []
created_date: '2026-09-24 18:39'
updated_date: '2026-09-24 20:10'
labels: []
dependencies:
  - TASK-45
references:
  - amonhen/ledger.py
  - amonhen/api.py
  - web/src/screens/Accounts.tsx
  - desiderata-monitoring-finanziario.md
documentation:
  - doc-1
type: feature
ordinal: 47500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Cancellare un movimento vero fa divergere il ledger dalla banca per costruzione: il controllo resterebbe rosso per sempre senza dire perche, e un conto che sembra rotto per una decisione presa a mano e rumore che nasconde i guasti veri. La differenza si spiega invece di essere nascosta o sottratta in silenzio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Per ogni figura dichiarata, quando la differenza e esattamente la somma dei movimenti cancellati che quella figura conterrebbe (disponibile: BOOK e PDNG; contabilizzata: solo BOOK, fino alla data della dichiarazione) il conto si legge riconciliato salvo N movimenti cancellati a mano, con l'importo
- [x] #2 Una differenza che i tombstone non spiegano resta un mismatch, con la sua cifra
- [x] #3 Senza movimenti cancellati il controllo e identico a oggi, e il log del sync non cambia
- [x] #4 Il pannello Conti distingue i quattro esiti (verificato, riconciliato salvo cancellati, mismatch, non verificato) e la versione dell'API sale
- [x] #5 CLAUDE.md aggiorna l'invariante: la differenza spiegata non e un assenso silenzioso, e il numero dei cancellati si vede
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
ledger.py: BalanceCheck guadagna suppressed (somma con segno dei movimenti cancellati che quella figura conterrebbe) e suppressed_count, piu la proprieta explained = difference == suppressed con almeno un cancellato; Ledger.deleted_total(account, as_of, kind) legge i tombstone non ripristinati fino alla data (BOOK e PDNG per available, solo BOOK per booked) e check_balance lo passa al check. api.py: _verification risponde con il quarto stato (suppressed) e con explained/suppressed/suppressed_count per ogni check; API_VERSION 16 -> 17. sync.py: _declared_balance_mismatch salta i check spiegati (log a info con importo e numero) e continua a segnalare quelli che i tombstone non spiegano. web: il quarto stato nel tipo, chip dedicato (tono viola, non ambra) con il titolo che riporta banca, ledger e la parte cancellata; importi stampati senza segno perche le due cifre dicono gia la direzione.
<!-- SECTION:NOTES:END -->
