---
id: TASK-7
title: Grafici per primi e rinomina in AmonHen
status: Done
assignee: []
created_date: '2026-09-12 18:18'
updated_date: '2026-09-12 18:18'
labels: []
dependencies: []
type: feature
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
I grafici del Dashboard passano davanti alle card delle metriche; il progetto prende il nome AmonHen e il titolo porta una citazione tolkeniana sull'Occhio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Nel Dashboard i tre grafici precedono le card (ordine DOM verificato), con il banner dello storico parziale spostato accanto ai numeri che spiega
- [x] #2 Titolo della app, manifest, apple-mobile-web-app-title e description riportano AmonHen e la citazione
- [x] #3 Il nome AmonHen sostituisce Finanze/finance-monitor in pyproject+uv.lock, package.json+lock, Dockerfile, compose, .env.example, docs e banner della CLI
- [x] #4 Build della PWA verde, compose valido, 201 test verdi
- [x] #5 Restano invariati (scelta esplicita) il pacchetto Python `finance_monitor`, il prefisso `MONITOR_*`, il file `monitor.db` e la cartella del repo
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Citazione usata: «The Eye of Sauron the Terrible few could endure» — J.R.R. Tolkien, Il Silmarillion (verificata su Tolkien Gateway, che la cita dall'Akallabêth). Compare nel `<title>`, nel `name` del manifest e come epigrafe in fondo allo schermo (`App.tsx`), perché la tab bar è fissa e l'epigrafe deve stare dentro l'area che scorre.
- Il service worker rinomina la cache in `amonhen-shell-v1`: il suo handler `activate` cancella ogni cache diversa, quindi le app già installate si aggiornano una volta sola.
- `uv lock` rieseguito dopo il cambio di `name` in pyproject (senza, `uv sync --frozen` in Docker fallirebbe); `npm install --package-lock-only` per il lock del frontend.
- Ordine verificato dal vivo a 390 px: header, chart Spese, chart Entrate, chart Patrimonio, banner, card, Budget, Anomalie, Categorie, Conti.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il Dashboard apre con i grafici (spese per categoria, entrate/uscite, patrimonio) e solo dopo le card, con il banner dello storico parziale accanto ai numeri che spiega; ordine confermato dal vivo a 390 px. Il progetto si chiama AmonHen, dal Seggio della Veduta, e il titolo porta la citazione dal Silmarillion sull'Occhio; il nome vive in pyproject e uv.lock, titolo e manifest della PWA, package.json e lock, banner della CLI, utente del container, servizio e volume compose e documentazione, con la cache del service worker rinominata (le app installate si aggiornano una volta). Restano di proposito invariati il pacchetto Python finance_monitor, il prefisso MONITOR_*, il file monitor.db e la cartella del repo. Verifica: build verde, compose valido, 201 test.
<!-- SECTION:FINAL_SUMMARY:END -->
