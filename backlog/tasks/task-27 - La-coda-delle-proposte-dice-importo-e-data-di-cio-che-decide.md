---
id: TASK-27
title: La coda delle proposte dice importo e data di cio che decide
status: Done
assignee: []
created_date: '2026-09-13 17:10'
labels: []
dependencies: []
type: feature
ordinal: 26500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ogni proposta mostra quanto denaro aspetta, su quanti movimenti e quando sono passati; con un movimento solo, un importo e una data
- [ ] #2 Il totale si legge con lo stesso predicato della coda, quindi non puo contraddire la lista che sta sotto
- [ ] #3 Una proposta i cui movimenti sono gia stati decisi lo dice invece di mostrare uno zero
- [ ] #4 La forma della risposta cambia, quindi la versione dell'API sale e il bundle la pretende
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Una proposta e per merchant, non per movimento: non esiste l'importo di una proposta, esiste quello che un si deciderebbe. La coda ora lo dice, e lo legge con il predicato della coda stessa, estratto in una costante condivisa: dove prima c'erano tre copie della stessa query ora ce n'e una, quindi il totale di una proposta non puo contraddire la lista sotto. Verificato dal vivo sulla contabilita vera: 24 proposte, 4 con piu di un movimento, zero scostamenti fra il testo sullo schermo e la risposta dell'API, nessuno scroll orizzontale a 390 px.
<!-- SECTION:FINAL_SUMMARY:END -->
