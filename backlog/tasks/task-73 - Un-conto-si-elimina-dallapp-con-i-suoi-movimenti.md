---
id: TASK-73
title: 'Un conto si elimina dall''app, con i suoi movimenti'
status: Done
assignee: []
created_date: '2026-10-25 22:06'
labels: []
dependencies: []
ordinal: 72500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dalla sezione Conti un conto reale si elimina con movimenti, cestino, saldi dichiarati e regole ristrette a lui; se è collegato a una banca esce anche da accounts.json. L'altra gamba di un giroconto torna in coda. Si conferma scrivendo il nome.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 DELETE /api/accounts/{id} elimina il conto e i suoi movimenti senza lasciare il ledger sbilanciato
- [x] #2 Un conto collegato esce da accounts.json, così il sync non lo ricrea
- [x] #3 Il pulsante si attiva solo dopo aver scritto il nome del conto
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ledger.delete_account e la rotta DELETE; conferma per nome nella sezione Conti. Spec 1.14, sezione 5.6.
<!-- SECTION:FINAL_SUMMARY:END -->
