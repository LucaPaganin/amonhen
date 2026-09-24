---
id: TASK-49
title: L'immagine si costruisce in CI e il NAS la tira
status: In Progress
assignee: []
created_date: '2026-09-24 18:39'
updated_date: '2026-09-24 22:04'
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
- [ ] #1 Un workflow GitHub Actions costruisce e pubblica su GHCR a ogni tag `v*`: `ghcr.io/<owner>/amonhen:<tag>` e `latest`, linux/amd64
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
<!-- SECTION:NOTES:END -->
