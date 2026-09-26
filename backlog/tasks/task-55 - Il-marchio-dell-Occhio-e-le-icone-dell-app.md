---
id: TASK-55
title: Il marchio dell Occhio e le icone dell app
status: Done
assignee:
  - '@main'
created_date: '2026-09-26 08:51'
updated_date: '2026-09-26 09:26'
labels: []
dependencies: []
ordinal: 54500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il segno dell app non somiglia all Occhio: l iscrizione disegna una mandorla con una pupilla ellittica sopra una torre di rettangoli, e le icone installate (icon-192, icon-512, apple-touch) sono tre barre ascendenti su fondo scuro, cioe un grafico a barre generico. Il marchio e l identita dell app: sta in cima a ogni schermata e sull icona installata, quindi deve venire da un disegno solo, con i gettoni del tema. Il manifest intanto dichiara ancora la citazione vecchia mentre index.html porta la nuova.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 web/src/assets/eye-mark.svg contiene il disegno: globo in ottone, pupilla a fessura verticale, nove lingue di fuoco, Barad-dur dietro l alone; nessun colore letterale, li da web/src/styles.css dai gettoni del tema
- [x] #2 L iscrizione inietta quel file invece di ricopiare la geometria, e le classi .epigraph__tower, .epigraph__crown, .epigraph__eye, .epigraph__pupil non esistono piu da nessuna parte
- [x] #3 web/public/icon-512.png, icon-192.png e apple-touch-icon.png sono rese dallo stesso disegno, esattamente 512x512, 192x192 e 180x180, al posto del grafico a barre
- [x] #4 Il name di web/public/manifest.webmanifest e la stessa stringa del title di web/index.html
- [x] #5 npm --prefix web run build passa (tsc strict + vite) e la fascia a 390x844 mostra il segno nel browser
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Nuovo web/src/assets/eye-mark.svg: globo in ottone con pupilla a fessura, nove lingue di fuoco, Barad-dur dietro l alone; solo classi eye__*, colori dai gettoni. 2. web/src/styles.css: al posto delle regole .epigraph__tower/__crown/__eye/__pupil, .epigraph__mark a width 56px e aspect-ratio 64/62 piu le regole eye__*. 3. web/src/components/Epigraph.tsx: il disegno si importa come testo e si inietta; citazione e figcaption restano. 4. Icone rigenerate dal disegno: pagina usa-e-getta in dumps/, servita su 8123, screenshot a 512, 192 e 180 px nei tre file di web/public/. 5. web/public/manifest.webmanifest: il name diventa la stringa del title di web/index.html. 6. web/README.md, sezione Design: descrivere il segno nuovo e la misura vera della fascia a 390 px. 7. Verifica: npm --prefix web run build, app servita su una copia del ledger, fascia guardata a 390x844 da un modello di visione, dimensioni dei tre PNG dai metadati.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fatto: web/src/assets/eye-mark.svg (globo, pupilla a fessura, nove lingue di fuoco, torre dietro l alone; classi eye__*, colori solo dai gettoni); blocco .epigraph riscritto in web/src/styles.css (le classi __tower/__crown/__eye/__pupil non esistono piu: verificato con grep) e .epigraph__mark a width 56px + aspect-ratio 64/62; Epigraph.tsx importa il disegno come testo e lo inietta; le tre icone rigenerate dal disegno a 512x512, 192x192 e 180x180 (metadati PNG verificati) e identiche ai byte serviti da /icon-512.png; manifest allineato al title; web/README.md aggiornato con la misura vera (segno 56x54.3, fascia 55.7px a 390).

Verifica: npm --prefix web run build verde (tsc strict + vite); app servita su una copia del ledger (dumps/verify2.db, porta 8124) e fascia guardata a 390x844 con un modello di visione: occhio con pupilla a fessura sopra una torre, niente tagliato. Anche dentro il container della prova: il cruscotto serve il segno nuovo e /icon-512.png e identico al file.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il marchio e ora il disegno vero, in un file solo. web/src/assets/eye-mark.svg porta globo in ottone, pupilla a fessura, nove lingue di fuoco e Barad-dur dietro l alone, con classi eye__* e nessun colore letterale (verificato: zero #hex o rgb() nel file); web/src/styles.css sostituisce le vecchie regole __tower/__crown/__eye/__pupil con le eye__* e porta .epigraph__mark a width 56px con aspect-ratio 64/62; Epigraph.tsx importa il disegno come testo e lo inietta, cosi la fascia e le icone vengono dalla stessa geometria. Le tre icone sono state rese dal disegno a 512x512, 192x192 e 180x180 (misurate dagli header PNG) e il manifest dichiara la stessa stringa del title. Verificato con npm --prefix web run build (tsc strict + vite), con la fascia guardata a 390x844 da un modello di visione (occhio con pupilla a fessura sopra una torre, niente tagliato) e con /icon-512.png servito dal container identico byte per byte al file.
<!-- SECTION:FINAL_SUMMARY:END -->
