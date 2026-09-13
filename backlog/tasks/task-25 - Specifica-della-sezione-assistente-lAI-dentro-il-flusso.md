---
id: TASK-25
title: 'Specifica della sezione assistente, l''AI dentro il flusso'
status: Done
assignee: []
created_date: '2026-09-13 12:59'
updated_date: '2026-09-13 13:00'
labels: []
dependencies: []
ordinal: 24500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Serve la definizione di prodotto di una sezione che interpreta spese e budget e propone: cosa puo' fare, come tratta i numeri (che restano quelli del backend), cosa non puo' fare, come si difende dalle descrizioni che arrivano da fuori, come si controlla il costo, e dove sta nell'app.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La specifica 5.9 dice cosa fa l'assistente: lettura in prosa dei numeri calcolati altrove piu' proposte confermabili
- [x] #2 Sui numeri: nessuna aritmetica propria, le cifre sono citazioni, e il testo generato e' marcato come tale
- [x] #3 I divieti: nessuna scrittura nel ledger, niente nel percorso del sync, niente SQL, nessun identificativo
- [x] #4 Difese dagli input: le descrizioni entrano come dati e la risposta fuori schema si scarta
- [x] #5 Controlli: modello dall'ambiente, domanda limitata, chiamate contate, nessuna ripetizione, degrado senza bloccare il resto
- [x] #6 Registrazione di domanda, risposta, modello e impronta dei dati
- [x] #7 Sezione 8, 9 (fase 5) e 10 (quattro rischi) aggiornate; specifica alla 0.5
- [x] #8 Il lavoro di implementazione e' tracciato a parte (TASK-26)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
La sezione 5.9 definisce cosa fa l'assistente, come tratta i numeri (nessuna aritmetica propria: le cifre sono citazioni di quelle del backend, e il testo generato e' marcato come tale), i divieti (nessuna scrittura nel ledger, niente nel percorso del sync, niente SQL, nessun identificativo), le difese dagli input (le descrizioni sono dati, non istruzioni; l'unica risposta accettata e' quella conforme allo schema), i controlli (modello dall'ambiente, domanda limitata, chiamate contate, nessuna ripetizione, degrado senza bloccare il resto), la registrazione di domanda e risposta con modello e impronta dei dati, e i punti di ingresso contestuali.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La specifica dell'assistente e' la sezione 5.9, e la specifica sale alla 0.5: una sezione dell'app che discute i numeri gia' calcolati e propone, senza aritmetica propria, senza scrivere nel ledger, senza identificativi in uscita e con la risposta validata contro lo schema. Aggiornate la sezione 8 (un divieto in piu'), la 9 (fase 5, specificata e non costruita) e la 10 (quattro rischi con la loro mitigazione). L'implementazione e' tracciata a parte, in TASK-26.
<!-- SECTION:FINAL_SUMMARY:END -->
