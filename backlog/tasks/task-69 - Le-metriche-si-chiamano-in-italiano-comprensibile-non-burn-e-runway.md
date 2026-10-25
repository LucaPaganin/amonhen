---
id: TASK-69
title: 'Le metriche si chiamano in italiano comprensibile, non burn e runway'
status: Done
assignee: []
created_date: '2026-10-25 14:59'
labels: []
dependencies: []
ordinal: 68500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il cruscotto e la spec usano termini che la persona che usa l'app non capisce: Burn ricorrente, Burn atteso, Runway stressato, Accantonamento episodico, Quota incomprimibile, burn rate. Vanno sostituiti con parole italiane che dicano cosa misurano (es. spesa mensile tipica, spesa mensile attesa, mesi di autonomia), nelle etichette, nelle spiegazioni dei cartellini, nei testi dell'assistente e nella spec. I nomi interni (chiavi API, campi di Metrics) possono restare: si cambia dove una persona legge. Non urgente: chiesto il 2026-10-25, da fare dopo la pianificazione delle spese.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Nessuna etichetta visibile nell'app contiene burn o runway
- [x] #2 Ogni metrica del cruscotto ha un nome italiano e una spiegazione di una riga che una persona senza gergo finanziario capisce
- [x] #3 La spec usa gli stessi nomi dell'app, con il vecchio termine citato una volta per chi legge il codice
- [x] #4 Il prompt dell'assistente e le sue letture usano i nuovi nomi
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Spesa mensile tipica, Riserva per spese rare, Spesa mensile attesa, Mesi di autonomia, Liquidità, Spesa irrinunciabile, Spesa tagliabile, Investito: sono i nomi delle card del cruscotto, con una spiegazione di una riga ciascuna. I flag delle categorie sono Spesa rara e Irrinunciabile. L'assistente riceve le metriche con gli stessi nomi e il prompt gli chiede di non usare gergo. La spec (versione 1.13) usa i nuovi nomi e cita il vecchio una volta in sezione 5.6. Le chiavi dell'API e i campi di Metrics restano invariati, quindi API_VERSION non cambia.
<!-- SECTION:FINAL_SUMMARY:END -->
