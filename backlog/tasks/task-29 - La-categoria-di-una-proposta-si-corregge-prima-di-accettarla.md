---
id: TASK-29
title: La categoria di una proposta si corregge prima di accettarla
status: Done
assignee: []
created_date: '2026-09-13 17:21'
labels: []
dependencies: []
type: feature
ordinal: 28500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il selettore e' precompilato sulla categoria proposta e offre tutte le categorie tranne il bucket di revisione
- [ ] #2 Accettare scrive la regola, e quindi i movimenti, con la categoria scelta e non con quella proposta
- [ ] #3 Non sceglierne nessuna e' il rifiuto: il pulsante diventa Rifiuta e la proposta esce dalla coda senza creare regole
- [ ] #4 Il contratto della richiesta cambia, quindi la versione dell'API sale e il bundle la pretende
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Una proposta e' un punto di partenza, non un verdetto: la tendina la corregge e accettare scrive la regola con la categoria scelta. Il rifiuto resta, ma come ultima opzione della stessa tendina, perche' una proposta che non merita una categoria non deve restare in coda per sempre. Verificato dal vivo: una proposta di Trasporti corretta a Ristoranti ha scritto la regola in Ristoranti e ci ha spostato il movimento; la scelta vuota ha portato il pulsante a Rifiuta e ha tolto la proposta senza creare regole; selettore e pulsante sulla stessa riga, 44 px, nessuno scroll orizzontale a 390 px.
<!-- SECTION:FINAL_SUMMARY:END -->
