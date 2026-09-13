---
id: TASK-17
title: Ricostruire e verificare l'immagine Docker
status: To Do
assignee: []
created_date: '2026-09-13 10:05'
updated_date: '2026-09-13 13:00'
labels: []
dependencies: []
ordinal: 16500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il Dockerfile esegue python -m finance_monitor serve; l'immagine non e' stata ricostruita dopo che l'API ha iniziato a servire web/dist, dopo API_VERSION 6 e dopo la gestione dei giroconti. Verifica una volta sola: build, accounts.json montato scrivibile, /connect che scrive, la PWA che si carica, MONITOR_HOST=0.0.0.0.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Toccato in questo giro: il tag dell'immagine uv era 0.6.11 mentre uv.lock e' revision 3, che i binari vecchi non sanno leggere; portato a 0.9.6, la versione che ha scritto il lock, e il passo uv sync --frozen --no-dev --no-install-project e' stato eseguito in isolamento con successo. Aggiunto un HEALTHCHECK su /api/health, con il comando eseguito contro un server vivo (exit 0), e corretta la nota del compose sul callback, che ora rinfresca invece di accodare. L'immagine resta da costruire: qui la CLI Docker c'e' ma il motore Linux no, quindi docker build non e' mai stato eseguito.
<!-- SECTION:NOTES:END -->
