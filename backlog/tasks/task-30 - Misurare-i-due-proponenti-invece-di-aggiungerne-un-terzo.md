---
id: TASK-30
title: Misurare i due proponenti invece di aggiungerne un terzo
status: Done
assignee: []
created_date: '2026-09-13 17:21'
labels: []
dependencies: []
type: spike
ordinal: 29500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il classificatore statistico misurato con validazione incrociata sui merchant, non sulle transazioni
- [ ] #2 Il modello misurato sugli stessi merchant tenuti fuori, con e senza gli esempi delle classificazioni esistenti
- [ ] #3 Decisione presa sui numeri: nessun terzo classificatore, nessun esempio aggiunto se non migliora
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
I due proponenti esistevano gia': il classificatore statistico sui char n-gram (pulsante Proponi categorie) e il modello (Chiedi al modello), ed entrambi si basano sulle classificazioni esistenti, il primo addestrandosi su di esse. Misurati invece di stimati, su 49 merchant con una categoria decisa da una persona: il classificatore, con validazione incrociata a 5 pieghe per merchant, indovina il 42/49 = 86% contro il 47% della categoria piu' frequente, e sopra la soglia di confidenza di 0,6 il 35/38 = 92%, cioe' la soglia e' calibrata: quello che osa proporre e' quasi sempre giusto. Per categoria: Trasporti 23/23, Ristoranti 14/17, Spesa 5/8, Altro 0/1 (una sola decisione, niente da imparare). Il modello, su 20 merchant tenuti fuori e mai mostrati: 18/20 senza esempi (due volte di fila) e 18/20 e 17/20 con gli esempi delle classificazioni esistenti, cioe' 90% contro 87,5%: gli esempi non aggiungono niente di misurabile, quindi non sono stati aggiunti. Nessun terzo classificatore: la coda resta il posto dove la persona corregge, e i due proponenti migliorano con quello che decide.
<!-- SECTION:FINAL_SUMMARY:END -->
