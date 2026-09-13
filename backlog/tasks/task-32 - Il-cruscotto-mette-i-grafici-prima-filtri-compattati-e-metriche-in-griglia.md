---
id: TASK-32
title: 'Il cruscotto mette i grafici prima: filtri compattati e metriche in griglia'
status: Done
assignee: []
created_date: '2026-09-13 18:17'
labels: []
dependencies: []
type: feature
ordinal: 31500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il periodo resta sempre in vista; gli altri filtri aprono dietro un pulsante Filtri, con il numero di quelli attivi
- [ ] #2 I grafici entrano nella prima schermata senza scrollare, misurato a 390 px
- [ ] #3 Le metriche sono una griglia di etichetta e cifra, con le spiegazioni dietro un solo Come si calcolano
- [ ] #4 Il pulsante generico Cosa e' cambiato? in testa al cruscotto e' tolto: l'assistente resta la sua sezione e l'ingresso contestuale dal budget
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Misurato a 390 px, prima e dopo. Prima: il pannello dei filtri era alto 481 px su 844 e spingeva il primo grafico a 679 px, cosi' si vedeva il titolo della torta e non la torta; le otto metriche erano 873 px di card incolonnate; la pagina era 3470 px. Dopo: i filtri sono una barra con i chip del periodo e un pulsante Filtri (a un tocco, con il conteggio di quelli attivi), il grafico comincia a 243 px e finisce a 651, quindi entra tutto nella prima schermata; le metriche sono una griglia alta 405 px con la spiegazione di ognuna dietro un Come si calcolano; la pagina e' 2639 px, un quarto in meno. Tolto anche il Cosa e' cambiato? sempre presente in testa: una domanda senza contesto e' una domanda che nessuno fa, e la specifica ora lo dice.
<!-- SECTION:FINAL_SUMMARY:END -->
