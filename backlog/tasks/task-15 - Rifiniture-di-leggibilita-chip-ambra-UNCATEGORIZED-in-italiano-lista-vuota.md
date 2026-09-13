---
id: TASK-15
title: 'Rifiniture di leggibilita'': chip ambra, UNCATEGORIZED in italiano, lista vuota'
status: Done
assignee: []
created_date: '2026-09-13 10:05'
updated_date: '2026-09-13 15:05'
labels: []
dependencies: []
ordinal: 14500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Tre punti aperti dalla revisione visiva, nessuno bloccante. (a) Il contrasto del chip ambra Da confermare va misurato, non stimato a occhio. (b) UNCATEGORIZED e' un valore di dominio mostrato all'utente: si puo' tradurre solo se il valore non e' anche chiave di regola o di API. (c) La lista delle righe senza categoria mostra la sua intestazione anche quando e' vuota.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il contrasto del chip ambra è misurato, non stimato: il testo sta fra 9,28 e 11,22 a 1
- [x] #2 I bordi degli stati passano la soglia di 3 a 1 di WCAG 1.4.11 su entrambe le superfici su cui poggiano, misurati
- [x] #3 UNCATEGORIZED resta la chiave che è (guardia delle regole, valore di filtro dell'API, sentinella del ledger) e si traduce solo dove una persona lo legge
- [x] #4 Il nome tradotto arriva dal server con l'handshake, non da una costante del client
- [x] #5 La lista dei movimenti senza categoria non mostra la sua intestazione quando è vuota
- [x] #6 Verificato nel browser a 390 px: nessuno straripamento orizzontale
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il chip ambra è stato misurato: il testo passava già, il bordo no (2,29 a 1 contro la soglia di 3), e lo stesso valeva per ogni chip di stato. I quattro colori di bordo sono stati alzati al primo valore che supera la soglia su entrambe le superfici e la misura è nel commento del foglio di stile. Il sentinella del bucket resta la chiave che è: si traduce solo dove si legge, con il nome preso dall'handshake del server invece che da una costante, e l'intestazione della lista non compare più quando la lista è vuota.
<!-- SECTION:FINAL_SUMMARY:END -->
