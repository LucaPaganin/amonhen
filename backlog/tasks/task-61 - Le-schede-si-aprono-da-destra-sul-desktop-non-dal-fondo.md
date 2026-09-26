---
id: TASK-61
title: 'Le schede si aprono da destra sul desktop, non dal fondo'
status: Done
assignee: []
created_date: '2026-09-26 11:32'
updated_date: '2026-09-26 13:26'
labels: []
dependencies:
  - TASK-60
references:
  - >-
    C:\Users\lucap\.omp\agent\sessions\-git_repos-amonhen\2026-09-24T18-25-56-868Z_01a0d4aa-c684-7715-8842-e15e80e3b466\local\desktop-shell-plan.md
type: feature
ordinal: 60500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sopra i 1024px le schede smettono di salire dal fondo: la scheda di un movimento (categoria, nota, split), il giroconto, Dichiara saldo e Nuovo conto entrano da destra come un pannello ancorato al lato, alto quanto la finestra, largo 460-520, cosi quello che si stava guardando resta visibile accanto. Sotto i 1024px resta il foglio dal basso. Il comportamento HTML (dialog, Esc, backdrop, focus trap) non cambia: cambia dove il pannello sta. (Il piano nominava anche un editor del budget: il budget non e una scheda, si modifica nella riga che lo mostra.)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Sopra i 1024px la scheda entra da destra, e larga 460-520px e alta quanto la finestra, e la lista sotto resta visibile
- [x] #2 L entrata muove solo transform e opacity, e prefers-reduced-motion la azzera come le altre
- [x] #3 Esc, il clic sul backdrop e il focus trap sono invariati, e la pagina dietro non scorre mentre la scheda e aperta
- [x] #4 Lo split editor resta usabile: il selettore categoria non si tronca (misurato) e il totale resta visibile senza scorrere
- [x] #5 Sotto i 1024px il foglio dal basso e identico a prima (confronto di screenshot a 390)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
web/README.md e CLAUDE.md, specifica a 1.7, build, pytest, revisioni AGENTS.md, commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Misure a 1484 con la scheda aperta: pannello x=949 (a filo del gutter riservato) largo 520, alto 925, radius 30px 0 0 30px, animation-name sheet-in-right con durata 0.24s (1e-06s con prefers-reduced-motion), maniglia display:none, overflow-y auto; la schermata dietro comincia a x=262, quindi restano 702px di lista visibili accanto; nessuno scorrimento orizzontale. Lo split: il selettore e largo 326 con 270 disponibili (40px se ne vanno nella freccia) e l opzione piu lunga del ledger, Senza categoria, misura 122px col font del controllo, quindi non si tronca; la riga, il totale (232..272) e i pulsanti (282..326) stanno dentro il pannello con scrollTop 0, cioe non c e niente da scorrere.

Comportamento provato con input veri, non con eventi sintetici: la rotellina sopra il backdrop ha lasciato scrollY a 400 (la pagina non si e mossa) mentre la stessa rotellina sopra il pannello ha scorso il pannello a 339 lasciando la pagina a 400; Esc ha chiuso; un clic vero a (400,500) sul backdrop ha chiuso. Un MouseEvent sintetico dispatchato sul dialog NON lo chiude: il top layer vuole hit-testing vero, e come strumento di prova avrebbe mentito.

Sotto i 1024 non si muove niente: il foglio aperto a 390 e 768 e byte per byte identico al build precedente (geometria identica: x=0/y=578/h=266 a 390, x=24/y=780/h=244 a 768, radius 30px 30px 0 0, animazione sheet-in, maniglia presente), e le sei schermate a 390 e 768 restano byte per byte identiche al build pre-rail.

Revisione di gusto, di specifica e di documentazione (tre revisori indipendenti). Il difetto vero l hanno trovato in due: il blocco della pagina toglie la barra di scorrimento, e dove quella barra occupa spazio la pagina si rilayouta - la colonna centrata di meta barra, un pannello a filo di tutta la barra - quindi si apriva con un salto e si chiudeva con il salto inverso. Corretto riservando il gutter (html { scrollbar-gutter: stable }) dentro lo stesso media: le due situazioni hanno la stessa larghezza. In questa sessione headless (barre sovrapposte) il salto non era riproducibile: la correzione e per costruzione, e il difetto e quello che due revisori hanno descritto per piattaforma.

Altri rilievi accolti: la voce 1.7 della specifica nominava un editor del budget che non e una scheda (e inline nella riga che lo mostra) e non nominava le quattro che si ancorano - scheda del movimento con il suo split, giroconto, Dichiara saldo, Nuovo conto: corretti specifica e descrizione del task, che ereditavano l errore del piano; un max-width: 520px morto perche il clamp lo garantisce gia, cancellato; il commento dei keyframes diceva di aver girato il movimento di novanta gradi tacendo il rimpicciolimento tolto, ora dice perche; il README chiamava la scheda card mentre il resto del file dice sheet.

Un rilievo non accolto, con motivo: la regola che spegne la maniglia non era nel piano. Resta. La maniglia e l affordance del foglio dal basso - una pillola che dice si chiude verso il basso - e su un pannello ancorato sarebbe una bugia; il revisore stesso misura che non si perde niente (tutte e quattro le schede hanno la croce con aria-label Chiudi e Esc funziona, e lo pseudo-elemento non e interattivo). L elenco del piano era descrittivo, e la specifica adesso nomina le superfici che si ancorano davvero.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Sopra i 1024px le schede non salgono piu dal fondo: la stessa <dialog> si ancora al lato destro come un pannello alto quanto la finestra, largo clamp(460px,40%,520px), tondo a sinistra e a filo del bordo a destra, e quello che si stava guardando resta visibile accanto (702px di lista a 1484). L entrata e sheet-in-right, che e il movimento del foglio girato di novanta gradi senza il rimpicciolimento, solo transform e opacity, azzerata da prefers-reduced-motion come le altre. La maniglia del foglio dal basso sparisce perche promette una chiusura verso il basso, e la pagina dietro non scorre: body:has(dialog[open]) con il gutter riservato, cosi aprire e chiudere non rilayouta niente. Esc, backdrop e focus trap sono quelli del browser e non sono stati toccati. Misurato: pannello 520x925 a x=949, rotellina sopra il backdrop che lascia la pagina ferma e sopra il pannello che scorre il pannello, selettore categoria dello split largo 326 con 270 disponibili e l opzione piu lunga a 122 (non tronca), totale e pulsanti dentro il pannello senza scorrere. Sotto i 1024 il foglio aperto a 390 e 768 e byte per byte identico al build precedente, e le sei schermate a 390/768 restano byte per byte identiche al build pre-rail. Revisione di gusto, di specifica e di documentazione: quattro rilievi accolti (il salto da barra di scorrimento, la voce di specifica che nominava un budget che non e una scheda, un max-width morto, un commento che taceva un dettaglio) e uno respinto con motivo (la maniglia). Build e 314 test verdi.
<!-- SECTION:FINAL_SUMMARY:END -->
