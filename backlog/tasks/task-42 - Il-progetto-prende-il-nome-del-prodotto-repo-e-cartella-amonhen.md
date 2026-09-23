---
id: TASK-42
title: 'Il progetto prende il nome del prodotto: repo e cartella amonhen'
status: Done
assignee: []
created_date: '2026-09-23 19:21'
updated_date: '2026-09-23 19:32'
labels: []
dependencies: []
type: chore
ordinal: 41500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il prodotto si chiama AmonHen, il pacchetto e' `amonhen`, le variabili sono `AMONHEN_*`, il database `amonhen.db`, ma il repository su GitHub e la cartella locale portano ancora il nome vecchio, `bank-connector`. TASK-16 ha fermato li' la rinomina di proposito e §7 della specifica lo registra come scelta dichiarata. La richiesta ora e' l'opposta: anche il repo e la cartella prendono il nome del prodotto, cosi' nessun artefatto visibile da fuori — URL del remoto, percorso su disco, titolo di CLAUDE.md, `project_name` del backlog — dice ancora bank-connector. Le frasi che affermano il contrario vanno riscritte, non lasciate accanto a quelle nuove, e il venv va rimesso in piedi perche' contiene il percorso assoluto vecchio nell'installazione editable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il repository GitHub e' LucaPaganin/amonhen e il vecchio URL reindirizza al nuovo
- [x] #2 La cartella locale e' C:\Users\lucap\git_repos\amonhen e origin punta a https://github.com/LucaPaganin/amonhen.git
- [x] #3 Nessun documento vivo afferma piu' che la cartella del repo resta bank-connector: §7 della specifica riscritto con la versione alzata, CLAUDE.md e backlog/config.yml allineati
- [x] #4 uv run pytest verde e uv run amonhen --help funzionante dal nuovo percorso
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Rinomino il repository su GitHub via API (gh non e' installato; il token del credential manager ha scope repo e admin sul repo), poi aggiorno origin.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il repository su GitHub e la cartella locale sono amonhen: il vecchio URL reindirizza al nuovo (301), origin punta a https://github.com/LucaPaganin/amonhen.git, il venv e' stato ricreato perche' l'installazione editable conteneva il percorso assoluto vecchio, e i documenti vivi (CLAUDE.md, §7 della specifica con la versione alzata, backlog/config.yml) non dicono piu' che la cartella resta bank-connector. Verificato dal nuovo percorso C:\Users\lucap\git_repos\amonhen: uv sync --frozen, import di amonhen risolto in amonhen\__init__.py del nuovo percorso, uv run pytest (314 passed), uv run amonhen --help.
<!-- SECTION:FINAL_SUMMARY:END -->
