---
id: TASK-65
title: Il pulsante Accetta nel dettaglio della coda non ha spazio per la scritta
status: Done
assignee: []
created_date: '2026-09-27 08:00'
updated_date: '2026-09-27 08:01'
labels: []
dependencies: []
ordinal: 64500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nel dettaglio della coda, sopra i 1024, i comandi di una proposta sono la tendina della categoria e il pulsante che la conferma, in una colonna di 330 px (260 il minimo dichiarato). Il pulsante eredita la regola dei pulsanti in fila (`flex: 1`) mentre la scheda del telefono ha la sua (`flex: 0 0 auto`): la tendina si prende la riga con la sua opzione piu lunga e al pulsante resta lo spazio libero, che e niente. Risultato visto dall utente a 1298 px: un cerchio giallo con «ccett» invece di «Accetta», cioe un comando che non si legge. La stessa riga di comandi e scritta una volta e vive in due posti (la scheda sotto i 1024, il dettaglio sopra), quindi la regola va data a tutte e due le copie, non all una.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A 1024, 1298 e 1484 px la scatola del testo di «Accetta» sta dentro il pulsante, con il suo padding: verificato misurando il rettangolo del testo e quello del pulsante
- [x] #2 Anche al minimo della colonna del dettaglio (260 px) la scritta sta dentro e il pulsante non esce dal pannello
- [x] #3 Sotto i 1024 la scheda della coda resta come prima: stessa riga, stessa larghezza della tendina e del pulsante
- [x] #4 La tendina continua a mostrare la categoria scelta e a stare nella riga
- [x] #5 npm --prefix web run build passa
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Misurare a 1298 px: riga di 298 px, tendina larga quanto la sua opzione piu lunga, pulsante con la regola dei pulsanti in fila (flex: 1). 2. Dare alla copia del dettaglio la stessa regola della scheda (flex: 0 0 auto), in un posto solo per i due posti in cui la riga vive. 3. Misurare il rettangolo del testo contro quello del pulsante a 1024, 1298 e 1484 px, e al minimo della colonna (260 px). 4. Controllare che sotto i 1024 la scheda non sia cambiata e che la tendina mostri ancora la categoria scelta.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Causa: la riga dei comandi e scritta una volta e resa in due posti; la regola che fa tenere al pulsante la larghezza della sua parola esisteva solo per la copia dentro `.proposal`, quindi la copia nel dettaglio restava con `flex: 1` e si divideva lo spazio libero, che accanto a una tendina larga quanto la sua opzione piu lunga e zero. Corretto estendendo quella regola a `.queue-detail__controls .button`, con il commento che dice perche. Misurato nel browser, rettangolo del testo di «Accetta» contro rettangolo del pulsante: a 330 px di pannello riga 298, tendina 194, pulsante 96, testo 60, dentro; al minimo 260 px riga 228, tendina 124, pulsante 96, testo 60, dentro e dentro il pannello; a 1024 e a 1484 gli stessi numeri. Sotto i 1024 il selettore nuovo non combacia, perche il dettaglio e `display: none`, e la scheda misura come prima: riga 332, tendina 228, pulsante 96, testo dentro. Visione: «Accetta» intero, con la tendina che mostra «Ristoranti».
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il pulsante che conferma una proposta nel dettaglio della coda tiene la larghezza della sua parola: la riga dei comandi vive in due posti (la scheda del telefono, il dettaglio della finestra) e la regola esisteva solo per la prima, quindi nel dettaglio il pulsante si divideva lo spazio libero con una tendina larga quanto la sua opzione piu lunga e restava un cerchio senza scritta. Verificato misurando il rettangolo del testo contro quello del pulsante a 1024, 1298 e 1484 px e al minimo dichiarato della colonna (260 px): testo 60 px dentro un pulsante di 96 px, dentro il pannello, a tutte le misure; sotto i 1024 la scheda e invariata. npm --prefix web run build e uv run pytest -q verdi.
<!-- SECTION:FINAL_SUMMARY:END -->
