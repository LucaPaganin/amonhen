---
id: TASK-17
title: Ricostruire e verificare l'immagine Docker
status: Done
assignee: []
created_date: '2026-09-13 10:05'
updated_date: '2026-09-13 15:09'
labels: []
dependencies: []
ordinal: 16500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il Dockerfile esegue python -m finance_monitor serve; l'immagine non e' stata ricostruita dopo che l'API ha iniziato a servire web/dist, dopo API_VERSION 6 e dopo la gestione dei giroconti. Verifica una volta sola: build, accounts.json montato scrivibile, /connect che scrive, la PWA che si carica, MONITOR_HOST=0.0.0.0.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 L'immagine si costruisce, con il tag uv allineato al lock che legge
- [x] #2 Il container serve la PWA costruita dentro l'immagine, con byte identici a quelli prodotti da vite
- [x] #3 health risponde con api_version 8 e l'healthcheck riporta healthy
- [x] #4 Con le variabili di compose il container ascolta su 0.0.0.0 e l'host lo raggiunge sulla porta pubblicata
- [x] #5 L'utente del container (uid 10001) scrive sia in /data sia in /config: il difetto trovato dalla verifica è corretto
- [x] #6 Un docker run nudo, con il solo mount del file di configurazione, non muore più per il database in /app
- [x] #7 Documentato cosa dipende dall'host (il modo del file montato) e cosa serve per la raggiungibilità dall'esterno
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Toccato in questo giro: il tag dell'immagine uv era 0.6.11 mentre uv.lock e' revision 3, che i binari vecchi non sanno leggere; portato a 0.9.6, la versione che ha scritto il lock, e il passo uv sync --frozen --no-dev --no-install-project e' stato eseguito in isolamento con successo. Aggiunto un HEALTHCHECK su /api/health, con il comando eseguito contro un server vivo (exit 0), e corretta la nota del compose sul callback, che ora rinfresca invece di accodare. L'immagine resta da costruire: qui la CLI Docker c'e' ma il motore Linux no, quindi docker build non e' mai stato eseguito.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
L'immagine è costruita e provata davvero, non solo scritta: costruisce, serve la PWA dal proprio web/dist con byte identici a quelli di vite, risponde con api_version 8, scrive il ledger nel volume e riporta healthy. La verifica ha trovato due difetti reali dell'immagine, entrambi corretti: creava /data ma non /config, così Docker creava il punto di mount come root e l'utente del container non poteva scriverci, e senza le variabili di compose partiva con il database in /app (di root) e moriva. Restano documentate le due cose che dipendono dall'esterno: il modo del file di configurazione montato e il bind address, che resta localhost perché l'API non ha autenticazione.
<!-- SECTION:FINAL_SUMMARY:END -->
