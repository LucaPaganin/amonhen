---
id: TASK-90
title: Le statistiche al posto dell'assistente
status: Done
assignee: []
created_date: '2026-11-02 10:00'
updated_date: '2026-11-02 10:00'
labels: []
dependencies: []
type: feature
ordinal: 90000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
L'assistente non veniva usato e per le sue domande mancavano i dati: è tolto, con le sue due tabelle. **Statistiche** legge ogni categoria sui mesi completi e il **Budget** dice quanto prende di solito (sezione 5.15). Rilasciato in v1.16.0.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Sezione, rotte, tabelle e riga *Regge?* dell'assistente non esistono più
- [x] #2 Le proposte del modello per i merchant mai visti restano
- [x] #3 Statistiche mostra mediana, media, intervallo e mesi su 6, 12 o 24 mesi completi
- [x] #4 Una riga del Budget dice *di solito*
<!-- AC:END -->
