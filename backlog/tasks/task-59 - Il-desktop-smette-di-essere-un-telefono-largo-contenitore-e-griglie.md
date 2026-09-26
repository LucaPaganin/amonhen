---
id: TASK-59
title: 'Il desktop smette di essere un telefono largo: contenitore e griglie'
status: Done
assignee: []
created_date: '2026-09-26 11:32'
updated_date: '2026-09-26 12:04'
labels: []
dependencies: []
references:
  - >-
    C:\Users\lucap\.omp\agent\sessions\-git_repos-amonhen\2026-09-24T18-25-56-868Z_01a0d4aa-c684-7715-8842-e15e80e3b466\local\desktop-shell-plan.md
type: feature
ordinal: 58500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A 1484x925 la colonna di contenuto e 720px su 1484: 382px vuoti per lato, e nessun elemento attraversa la finestra. Pannelli e carte misurano 692px e stanno uno per riga, la lista dei movimenti e alta 7862px per circa 130 movimenti. La causa e una riga sola di styles.css (.app__main max-width 720px) piu un unico breakpoint sopra i 640px per .metrics. Questa fetta e il pavimento delle altre due: senza un contenitore largo il rail e il pannello laterale non hanno dove stare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Sopra i 1024px la colonna di contenuto misura almeno 1100px, e a 1440 o piu 1240px, con lo stesso tetto per la fascia alta e la barra bassa
- [x] #2 Sopra i 1024px i due grafici del cruscotto sono affiancati, i conti e i budget si affiancano, e la coda e a 2 colonne (3 da 1440); le otto tessere del cruscotto stanno su una riga sola da 1440 (misurate: 145px l una, la cifra piu lunga 103) e a quattro per riga sotto, senza nessuna cifra tagliata a nessuna larghezza
- [x] #3 Sotto i 1024px il render e identico a prima: le scatole di ogni elemento visibile a 390 e a 768 confrontate con la build precedente, senza una differenza
- [x] #4 Nessun blocco supera il tetto della colonna, nessun paragrafo supera i 75 caratteri per riga e nessuna schermata scorre in orizzontale (misurato a 390, 768, 1024, 1484)
- [x] #5 I grafici recharts hanno altezza non nulla dentro le griglie nuove (200 e 208 px misurati) e disegnano i loro dati
- [x] #6 web/README.md e CLAUDE.md dicono la soglia, il tetto e la trappola di :has annidato; npm --prefix web run build e uv run pytest -q passano
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Un gettone --shell per il tetto della colonna: 720px oggi, 1100px da 1024, 1240px da 1440, condiviso da .app__main, .appbar__inner e .tabbar (che oggi stanno a 720/700/700).

2. Griglie da 1024: metriche a 6 colonne, i due grafici del cruscotto affiancati, la coda a 2 colonne (3 da 1440), conti e budget a 2 colonne.

3. Misura della riga di lettura: un tetto in ch per i paragrafi lunghi, solo dove il testo e prosa.

4. Baseline a 390/768/1024/1484 prima della modifica, poi le stesse quattro dopo: a 390 e 768 il diff deve essere vuoto.

5. web/README.md e CLAUDE.md: la soglia e il tetto; build e test; commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Misure: colonna 720 -> 1024 a 1024 di viewport (tutta la finestra) e -> 1240 a 1440/1484 (122px per lato invece di 382); fascia alta e barra bassa seguono con lo stesso -20 che avevano (700 -> 1004/1220). Grafici affiancati: 491+491 a 1024, 599+599 a 1440, patrimonio a tutta larghezza (1212). Coda: 2 colonne a 1024 (493), 3 a 1440 (397), con le schede tornate lastre (raggio 24, --fill-1) e zero testo tagliato. Conti e budget affiancati (599+599 a 1484).

Prima trappola, trovata misurando: :has non si annida. La regola scritta come :has(.chart):has(+ .panel:has(.chart)) e invalida e non seleziona niente, quindi i grafici restavano a tutta larghezza senza che nulla protestasse. La forma valida e :has(.chart):has(+ .panel .chart), con un discendente dentro il lookahead.

Seconda trappola: le tessere del cruscotto sono otto, non sei. A 6 colonne la settima riga restava con due tessere sole; la striscia a 8 su una riga sta solo dove la finestra la regge: a 1440 le tessere misurano 145px e la cifra piu lunga ne chiede 103, a 1280 ne misurano 127 e la cifra ne chiede 103 su 101 disponibili, cioe un digit tagliato. Quindi striscia da 1440, quattro per riga sotto, zero cifre tagliate a nessuna larghezza (verificato tessera per tessera).

Sotto i 1024 non si muove niente, confrontato non promesso: le scatole di ogni elemento visibile a 390 e 768 sono identiche alla build precedente su tre schermate (526, 796 e 278 elementi), e a 390 due PNG su tre sono identici byte per byte mentre il terzo differisce di un pixel per un valore su 255 (rumore di codifica).

Verifica finale a 390/768/1024/1484: nessuno scorrimento orizzontale (scrollWidth - innerWidth = 0), nessun paragrafo oltre i 75 caratteri (il piu largo misura 72), grafici recharts alti 200-208px con i dati disegnati (13, 12 e 3 elementi), build e 314 test verdi. web/README.md (sezione Layout) e CLAUDE.md (bullet nuovo) dicono la soglia, il gettone e la trappola di :has.

Revisione di gusto indipendente (agente reviewer, read-only): un difetto vero e tre rilievi minori, tutti accolti. Il difetto: le due regole che affiancavano i pannelli indovinavano dal contenuto o dal vicino, e in stati raggiungibili sbagliavano — con due grafici disegnati invece di tre (un ledger il cui patrimonio e un punto solo non disegna la curva) il donut restava mezzo largo da solo e i flussi prendevano una riga intera; senza conti, o senza lista dei budget, uno dei due pannelli restava mezzo largo con meta riga vuota. Ora i pannelli che condividono la riga lo dichiarano dove sono scritti, con panel--pair (i due grafici del periodo, i conti e i budget), e la regola e una sola.

Verificati gli stati degradati togliendo i pezzi a runtime: con la curva del patrimonio senza grafico i due grafici del periodo restano 599+599; senza lista dei budget, e poi senza nessuna delle due liste, conti e budget restano 599+599. Gli altri tre rilievi: una dichiarazione morta (il reset dell ombra sulle righe di .card-list non raggiungeva niente, perche .card-list > .card la batte in specificita su ogni figlio), cancellata; e la frase del README che diceva che ogni lista di righe diventa una griglia di schede, mentre solo le liste di schede lo fanno: corretta dicendo quali.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La colonna di contenuto smette di essere un telefono da 720px centrato in una finestra grande: il tetto e un gettone solo, --shell (720, 1100 da 1024, 1240 da 1440), e lo leggono anche la fascia alta e la barra in basso perche sono la cornice di quella colonna. Sopra i 1024 la schermata diventa una griglia a due colonne, i pannelli che condividono la riga lo dichiarano con panel--pair (i due grafici del periodo, i conti e i budget), le liste di schede tornano griglie di schede con raggio e ombra propri, e i testi tengono la misura di un libro. Da 1440 le otto tessere del cruscotto stanno su una riga e la coda va a tre colonne. Sotto i 1024 non si muove niente e non e una promessa: le scatole di ogni elemento visibile a 390 e 768 sono state confrontate con la build precedente su tre schermate (526, 796, 278 elementi) senza una differenza, e a 390 due PNG su tre sono identici byte per byte. Verificato a 390/768/1024/1484: nessuno scorrimento orizzontale, nessuna cifra tagliata, grafici alti 200-208px con i dati disegnati, e le coppie ancora appaiate togliendo a runtime una delle due liste o la curva del patrimonio. Revisione di gusto indipendente con quattro rilievi, tutti accolti. Build e 314 test verdi.
<!-- SECTION:FINAL_SUMMARY:END -->
