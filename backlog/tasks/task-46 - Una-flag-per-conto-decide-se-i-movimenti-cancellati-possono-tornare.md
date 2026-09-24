---
id: TASK-46
title: Una flag per conto decide se i movimenti cancellati possono tornare
status: Done
assignee: []
created_date: '2026-09-24 18:39'
updated_date: '2026-09-24 19:57'
labels: []
dependencies:
  - TASK-45
references:
  - amonhen/ledger.py
  - amonhen/sync.py
  - amonhen/api.py
  - web/src/screens/Accounts.tsx
documentation:
  - doc-1
type: feature
ordinal: 45500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sopprimere per sempre non va bene per tutti: un consenso riautorizzato puo restituire movimenti cancellati per sbaglio, o cancellati durante una prova. La decisione e per conto, sta nel ledger accanto al conto, ed e spenta di default perche cancellare deve significare cancellare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `accounts.reimport_deleted` esiste, default 0 su un ledger esistente, e si legge e si scrive per un conto reale rispondendo con lo stato
- [x] #2 Con la flag spenta il sync sopprime i movimenti cancellati, come da default
- [x] #3 Accesa la flag, il sync successivo reinserisce il movimento dal payload conservato nel tombstone, con la sua nota, e il tombstone registra che e tornato invece di sparire
- [x] #4 Sync ripetuti con la flag accesa non producono duplicati, e spegnere la flag non ricancella cio che e tornato
- [x] #5 Il pannello Conti mostra la flag con il suo effetto, e il testo dice cosa succedera al prossimo sync
- [x] #6 La specifica (§5.1, §6) e CLAUDE.md dicono che la flag esiste e cosa fa; la versione dell'API sale
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. db.py: accounts.reimport_deleted INTEGER NOT NULL DEFAULT 0 in _ADDED_COLUMNS (un ledger esistente la prende).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
db.py: accounts.reimport_deleted (default 0) in _ADDED_COLUMNS. models.py: RecordAction guadagna "reimported".
<!-- SECTION:NOTES:END -->
