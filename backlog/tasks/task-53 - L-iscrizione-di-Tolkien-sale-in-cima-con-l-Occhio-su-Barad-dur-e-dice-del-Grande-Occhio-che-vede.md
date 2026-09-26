---
id: TASK-53
title: >-
  L iscrizione di Tolkien sale in cima con l Occhio su Barad-dur, e dice del
  Grande Occhio che vede
status: Done
assignee: []
created_date: '2026-09-26 07:40'
updated_date: '2026-09-26 07:47'
labels:
  - feature
dependencies: []
ordinal: 52500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi la citazione e una riga in fondo a ogni schermata (App.tsx, .app__epigraph) e dice "The Eye of Sauron the Terrible few could endure": parla di terribilita, non di sguardo. Deve stare in cima, accompagnata da una stilizzazione del Grande Occhio su Barad-dur, e la frase deve dire del Grande Occhio che tutto vede e osserva — l app si chiama AmonHen, il Sedile del Vedere, dove Frodo sente l Occhio. La riga nuova e verbatim dal passo (FotR, Libro II cap. 10, The Breaking of the Fellowship): "There was an eye in the Dark Tower that did not sleep", con la fonte. Il segno e disegnato con i gettoni di :root (torre in un riempimento basso, Occhio in ottone col suo alone), senza bordi, e l altezza resta quella di una fascia: senza rubare schermo al cruscotto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La citazione nuova e il segno stanno in cima alla schermata, non piu in fondo
- [x] #2 Il segno e una stilizzazione leggibile dell Occhio sopra la torre, disegnata con i gettoni di :root, e non un riquadro o un icona generica
- [x] #3 La frase e quella del passo verificato, con la fonte, e si legge a 390px senza troncare
- [x] #4 Il wizard di primo setup resta senza fascia (la configurazione non ha bisogno di iscrizione)
- [x] #5 Altezza della fascia misurata: non piu di ~72px a 390px
- [x] #6 web/README.md aggiornato se descrive l iscrizione
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Passo verificato prima di scrivere: la riga e da The Fellowship of the Ring, Libro II cap. 10, The Breaking of the Fellowship (Frodo su Amon Hen): "And suddenly he felt the Eye. There was an eye in the Dark Tower that did not sleep." — confermato da due fonti che citano il passo. La citazione precedente ("The Eye of Sauron the Terrible few could endure") e il suo riferimento al Silmarillion escono da App.tsx, dal title di index.html e dal blockquote del README, che ora dicono la stessa riga nuova. Verifica nel browser sul ledger reale: la fascia sta in cima (top 74px, altezza 56px su un tetto di ~72), quote su 2 righe e fonte su 1 senza overflow (scrollWidth = clientWidth su entrambe), nessun overflow orizzontale del documento; su ?setup=1 nessuna fascia e stepper presente; la citazione precedente non compare piu in nessun file. Il segno, ingrandito a 280px e guardato da un modello di visione, si legge come un occhio a mandorla con pupilla a fessura, in ottone e con alone, sopra una torre scura con corona di punte e due sproni laterali, senza contatto fra i due; la torre e passata da --fill-2/--fill-3 (quasi invisibili a 56px) a due tinte del colore del testo.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La citazione e in cima a ogni sezione come fascia: l'Occhio su Barad-dur disegnato con i gettoni, accanto alla riga verbatim del passo di Amon Hen (FotR II.10) con la fonte. Altezza misurata 56px a 390px; niente fascia sul wizard; App.tsx, il title di index.html, il blockquote del README e web/README.md (sezione Design) allineati. Verificato nel browser sul ledger reale, con il segno ingrandito e ispezionato da un modello di visione.
<!-- SECTION:FINAL_SUMMARY:END -->
