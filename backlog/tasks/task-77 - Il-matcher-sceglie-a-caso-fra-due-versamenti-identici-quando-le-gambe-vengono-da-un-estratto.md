---
id: TASK-77
title: >-
  Il matcher sceglie a caso fra due versamenti identici quando le gambe vengono
  da un estratto
status: To Do
assignee: []
created_date: '2026-10-29 07:47'
labels: []
dependencies: []
ordinal: 76500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Un estratto CSV non porta la controparte, quindi il matcher accoppia per importo e giorno soltanto. Sul cointestato, quando Luca e Valentina versano la stessa cifra lo stesso giorno, il giroconto dal conto personale si accoppia con uno dei due a caso: nella prova dell'import storico del 2026-10-29 è capitato 6 volte fra aprile e luglio 2026, e tre volte una coppia era del tutto sbagliata (un addebito Scalable con un versamento di Valentina, e due giroconti verso il deposito presi per bonifici Fineco quando Fineco era importato per primo). I totali restano giusti, l'etichetta no. Strade possibili: leggere il nome dell'ordinante dalla descrizione di un estratto, preferire a parità di peso la gamba che nomina il titolare del conto, o far decidere le regole di giroconto prima del matcher.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Fra due candidati di pari importo e giorno il matcher preferisce quello che la descrizione attribuisce al titolare
- [ ] #2 Un movimento che una regola di giroconto prende non viene proposto dal matcher per un'altra coppia
<!-- AC:END -->
