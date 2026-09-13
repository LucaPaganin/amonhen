---
id: TASK-31
title: >-
  Il documento dell'app si serve senza Cache-Control e il browser resta su un
  bundle sparito
status: Done
assignee: []
created_date: '2026-09-13 18:17'
labels: []
dependencies: []
type: bug
ordinal: 30500
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 La pagina si serve con Cache-Control: no-cache, quindi il browser chiede prima di usarla e la ricontrollo risponde 304 quando non e' cambiato niente
- [ ] #2 Il service worker non mette in cache il documento: solo gli asset con nome derivato dal contenuto
- [ ] #3 Riprodotto il guasto: la pagina caricava un bundle che non esisteva piu' su disco, con 404 sullo script e schermo bianco
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il sintomo era che un rilascio sembrava non aver cambiato niente, e ogni tanto lo schermo bianco. Due cause, entrambe vere: l'HTML era servito senza Cache-Control, quindi il browser se lo teneva e continuava a puntare agli asset di prima — nomi che un rilascio ha sostituito, quindi 404 sullo script e pagina bianca; e il service worker teneva in cache /index.html, cosi' un documento vecchio sopravviveva anche alla sua scadenza. Riprodotto: la pagina in esecuzione caricava un bundle che non esisteva piu' su disco. Ora la pagina si serve no-cache e il worker cacha solo /assets/, dove il nome viene dal contenuto e quindi non puo' essere stantio. Una shell offline sarebbe inutile comunque: il ledger non si cacha, quindi l'app dalla cache non avrebbe niente da mostrare.
<!-- SECTION:FINAL_SUMMARY:END -->
