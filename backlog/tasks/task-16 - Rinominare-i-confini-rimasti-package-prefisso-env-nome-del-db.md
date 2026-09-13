---
id: TASK-16
title: 'Rinominare i confini rimasti: package, prefisso env, nome del db'
status: Done
assignee: []
created_date: '2026-09-13 10:05'
updated_date: '2026-09-13 15:05'
labels: []
dependencies: []
ordinal: 15500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il prodotto si chiama AmonHen ma il package e' finance_monitor, le variabili d'ambiente MONITOR_* e il database monitor.db; la cartella del repo resta bank-connector. Il rename e' stato fermato li' di proposito. Decisione da prendere: rinominare il package e con esso gli import di tutti i moduli, il Dockerfile, i comandi in README/CLAUDE.md e pythonpath di pytest, oppure tenere i confini come sono.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il pacchetto è amonhen: import, Dockerfile, console script, pyproject, test e strumenti
- [x] #2 Le variabili sono AMONHEN_*: .env, .env.example, launch.json, compose, documenti
- [x] #3 Il database è amonhen.db: default, .gitignore, .dockerignore, compose
- [x] #4 Fuori dai task storici non resta nessun finance_monitor, MONITOR_ o monitor.db
- [x] #5 Suite verde e CLI funzionante dopo la rinomina
- [x] #6 La cartella del repo resta bank-connector, e la specifica dice perché
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
I confini rimasti sono rinominati: pacchetto amonhen, variabili AMONHEN_*, database amonhen.db, con il Dockerfile, la CLI, pyproject, i test, gli strumenti e tutta la documentazione dietro. Resta bank-connector la cartella del repo, che è il nome che l'ha ospitato prima che il prodotto avesse il suo, e la specifica adesso lo dice. La rinomina meccanica ha toccato anche la frase storica della specifica, che è stata riscritta a mano.
<!-- SECTION:FINAL_SUMMARY:END -->
