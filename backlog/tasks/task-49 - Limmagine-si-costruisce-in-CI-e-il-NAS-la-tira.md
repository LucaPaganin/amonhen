---
id: TASK-49
title: L'immagine si costruisce in CI e il NAS la tira
status: Done
assignee: []
created_date: '2026-09-24 18:39'
updated_date: '2026-09-24 22:23'
labels: []
dependencies: []
references:
  - Dockerfile
  - docker-compose.yaml
  - .dockerignore
  - README.md
documentation:
  - doc-1
type: chore
ordinal: 48500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi l'immagine si costruisce sul NAS dal sorgente con `docker compose up -d --build`: lento su 8 GB di RAM, e ogni deploy richiede il repo (e i suoi file non versionati) li. Serve che l'immagine nasca dalla CI su un tag e che il NAS faccia solo pull e up. Il NAS e x86_64, quindi linux/amd64 basta e non serve multi-arch.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un workflow GitHub Actions costruisce e pubblica su GHCR a ogni tag `v*`: `ghcr.io/<owner>/amonhen:<tag>` e `latest`, linux/amd64
- [x] #2 `docker-compose.yaml` esegue l'immagine dal registry, e `docker compose up -d --build` resta possibile per una build locale (profilo o override documentato)
- [x] #3 La procedura sul NAS e copiabile: pull e up, con i volumi del ledger e di accounts.json e la nota sull'uid 10001 che restano vere
- [x] #4 L'immagine non contiene ledger, accounts.json, chiavi o dump: il contesto di build li esclude e la CI non usa segreti oltre al token automatico
- [x] #5 README e specifica (§9, stato) dicono come si costruisce, come si pubblica e cosa fa il NAS
- [x] #6 Limite dichiarato: su questa macchina il motore Docker non gira, quindi la prova arriva dalla CI (build vero) e dal NAS (pull e up), non da qui
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
`.github/workflows/image.yml`: su un tag `v*` (o a mano) il job `check` fa `uv sync --frozen`, `pytest -q` e `npm ci` + `npm run build`; il job `publish` (needs: check, permissions packages: write) costruisce `linux/amd64` con buildx, fa login su GHCR col GITHUB_TOKEN e pubblica `<tag>` e `latest` su `ghcr.io/lucapaganin/amonhen`. Il nome dell'immagine e in minuscolo e identico a quello in docker-compose.yaml, perche una reference con maiuscole il registro la rifiuta: e l'unico punto dove due file devono dire la stessa stringa, e la nota sta in entrambi.

Implementato e verificato per quanto si puo da qui: workflow su tag `v*` con il job di controllo (pytest + build del bundle) prima della pubblicazione, compose che consuma l'immagine, override di build locale, README riscritto per un NAS senza repository, .dockerignore con actual-cache. Resta non spuntato l'AC 1 ("il workflow costruisce e pubblica a ogni tag"): il repository non ha tag, e su questa macchina il motore Docker non gira, quindi la prima esecuzione vera — build su runner amd64, push su GHCR, pull sul NAS — e l'unica prova che manca. Non spunto l'AC per questo, e la specifica §9 lo dice fra il lavoro aperto.

La CI ha girato per davvero, e la prima esecuzione ha fallito: il job di controllo si e fermato sui test e la pubblicazione e stata saltata (la barriera ha funzionato). Il log non e leggibile senza autenticazione, quindi ho riprodotto l'ambiente della CI in WSL (Ubuntu): li i test sono verdi, quindi la differenza erano i file non versionati — e in un albero costruito da `git archive HEAD` (senza `accounts.json`, senza `.env`) undici test preesistenti fallivano con "No such file or directory: accounts.json", perche leggevano la configurazione dell'operatore. Difetto preesistente, scoperto dalla CI di questa fase: la suite non era autosufficiente. Corretto con `tests/fixtures/config/minimal.json`, passato alla fixture dell'API e a `run()` dei test CLI, piu una voce in CLAUDE.md che dice come riprodurre la verifica in un albero pulito.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
L'immagine si costruisce in CI e il NAS la tira: su un tag `v*` girano prima i test e la build del bundle, poi buildx pubblica `ghcr.io/lucapaganin/amonhen:<tag>` e `:latest` per linux/amd64. Verificato davvero: il tag v1.3.0 ha prodotto una esecuzione con entrambi i job verdi, i due tag rispondono nel registro, il token di pull anonimo si ottiene (pacchetto pubblico, nessuna credenziale sul NAS) e i layer contengono solo il pacchetto e il bundle — nessun dato. La prima esecuzione ha trovato un difetto preesistente che questa fase ha corretto: undici test leggevano la `accounts.json` dell'operatore e fallivano su un checkout pulito.
<!-- SECTION:FINAL_SUMMARY:END -->
