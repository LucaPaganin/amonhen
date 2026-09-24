---
id: TASK-43
title: Un pulsante sincronizza i conti e risponde con l'esito
status: Done
assignee: []
created_date: '2026-09-24 18:38'
updated_date: '2026-09-24 18:53'
labels: []
dependencies: []
references:
  - amonhen/api.py
  - amonhen/sync.py
  - amonhen/cli.py
  - web/src/App.tsx
documentation:
  - doc-1
type: feature
ordinal: 42500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi il sync si avvia solo dalla riga di comando (`uv run amonhen sync`) o dal loop schedulato di `serve --sync-interval-hours`: dall'app non c'e modo di chiedere dati freschi prima di guardare la coda, quindi si aspetta il giro successivo o si apre un terminale. Il pulsante serve a leggere il movimento appena fatto senza lasciare l'app, e a vedere subito se una banca ha risposto male, se un conto non torna o se il consenso e scaduto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `POST /api/sync` esegue un sync completo dentro la richiesta (fetch per conto, scrittura nel ledger, link dei giroconti, regole) e risponde con l'esito per conto (letti, inseriti, promossi, duplicati, soppressi, errore) piu i giroconti collegati, le regole applicate e l'esito della §5.4 per conto
- [x] #2 Due sync non si sovrappongono: una richiesta mentre un sync gira non ne avvia un secondo, e lo stesso guardiano copre il loop schedulato di `serve`
- [x] #3 Una configurazione assente o una chiave non leggibile rispondono con il motivo invece che con un traceback, come fa il resto dell'API
- [x] #4 Il pulsante sta in cima all'app, mostra che sta girando e poi l'esito; al ritorno coda, Movimenti e Conti mostrano i dati nuovi
- [x] #5 Misurato dal vivo su una copia del ledger: il conteggio dei movimenti cambia solo per cio che il sync ha davvero scritto, e un conto con consenso scaduto compare fra gli errori senza fermare gli altri
- [x] #6 La versione dell'API sale e il bundle la pretende, perche un bundle nuovo contro un server vecchio chiamerebbe un endpoint che non esiste
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. sync.py: un lock di processo condiviso (SyncService.run solleva SyncBusy se un altro sync gira) — copre la richiesta HTTP e il loop di serve, che vivono nello stesso processo.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementato: SyncBusy + lock di processo in sync.py (run() acquisisce il lock, il corpo e in _run), POST /api/sync in api.py con 503 sul motivo se la configurazione non si legge e 409 se un sync gira, _sync_payload con esito per conto e verifica 5.4, API_VERSION 11 -> 12.
<!-- SECTION:NOTES:END -->
