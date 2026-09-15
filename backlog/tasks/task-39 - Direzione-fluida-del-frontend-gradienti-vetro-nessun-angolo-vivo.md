---
id: TASK-39
title: 'Direzione fluida del frontend: gradienti, vetro, nessun angolo vivo'
status: Done
assignee: []
created_date: '2026-09-15 05:08'
updated_date: '2026-09-15 05:08'
labels: []
dependencies: []
type: feature
ordinal: 38500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Richiesta esplicita: piu gradiente, piu tondo, nessuno spigolo vivo. La direzione piatta e editoriale della fetta precedente e superata: fondo a tre bagliori, superfici di vetro traslucido, capsule galleggianti al posto delle fasce, pillole al posto dei riquadri. Il rischio di questa direzione e la leggibilita, quindi ogni colore e stato misurato sul pixel peggiore che il fondo puo produrre, non scelto a occhio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il fondo porta tre bagliori su un livello fisso e le superfici sono di vetro; in tutte e cinque le sezioni nessun riquadro pieno ha un raggio sotto i 2 px
- [x] #2 Contrasto sul render reale (app nascosta, pixel piu chiaro rgb(38,34,31)): testo 14.5, tenue 6.4, ottone 10.0, entrate 10.3, uscite 8.1, bordo dei controlli 5.4, sopra soglia anche sopra il vetro
- [x] #3 A 390 px il documento e largo quanto il viewport e nessun controllo sta sotto i 44 px in tutte e cinque le sezioni, misurato con prefers-reduced-motion
- [x] #4 Il carattere e Plus Jakarta Sans variabile, scelto misurando le cifre tabellari, servito da /assets/ con la licenza OFL accanto, e il file precedente e rimosso
- [x] #5 I grafici hanno spicchi arrotondati con riempimento sfumato e barre a cappuccio tondo con gradiente
- [x] #6 Nessun cambiamento di contratto: API_VERSION resta 11, nessuna dipendenza nuova, il client non somma ne filtra
- [x] #7 A fine pagina l'ultimo blocco sta 28 px sopra la capsula galleggiante
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Carattere: Plus Jakarta Sans variabile 200-800, sottoinsieme latino, 27348 byte. Scelto misurando nel browser le cifre tabellari (larghezza di 1 uguale a quella di 8 sotto font-variant-numeric): DM Sans e Urbanist hanno fallito quella prova e sono stati scartati, perche in un registro una cifra proporzionale rompe la colonna degli importi.
Colori: fondo #0d0f1a con bagliori ambra, viola e acqua su un livello fisso. Il testo e scelto contro il punto peggiore raggiungibile (un bagliore al centro, due sovrapposti a meta) e poi verificato sul render: nascondendo l'app, il pixel piu chiaro dello schermo e rgb(38,34,31) e li il testo sta a 14.5:1, il tenue a 6.4, l'ottone a 10.0, il bordo dei controlli a 5.4.
Forme: raggi 12/16/20/26/32 piu pillola per i controlli; le due barre sono capsule galleggianti con vetro e blur, il cassetto ha gli angoli destri tondi, il foglio quelli alti, le opzioni del foglio sono pillole separate. Il blur e solo sui quattro elementi che galleggiano: sfocare ogni lista costerebbe un ridisegno che il telefono non ha da dare.
La tecnica dei gap di 1 px come righe e stata rimossa: con gli angoli tondi le metriche sono tessere separate su una griglia. Verificato che a fine pagina nulla resti sotto la capsula (margine 28 px) e che nessuna riga sbordi dalla lastra (raggio 26 px, overflow hidden, zero figli fuori).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
L'interfaccia e passata alla direzione fluida richiesta: campo scuro con tre bagliori, superfici di vetro, capsule galleggianti, pillole e nessun angolo vivo. Verificato a 390x844 su una copia del ledger con misure, non a occhio: zero riquadri pieni con raggio sotto i 2 px e zero controlli sotto i 44 px in tutte e cinque le sezioni (sotto prefers-reduced-motion, perche la cascata distorce le misure); contrasto ricavato dai pixel reali del render; carattere scelto misurando le cifre tabellari; margine di 28 px sopra la capsula a fine pagina. tsc, build e i 314 test passano; nessuna dipendenza nuova, nessuna modifica a route, payload o API_VERSION.
<!-- SECTION:FINAL_SUMMARY:END -->
