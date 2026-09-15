---
id: TASK-40
title: 'Design minimale senza bordi: riempimenti, tinte, numeri grandi, piu denso'
status: Done
assignee: []
created_date: '2026-09-15 20:31'
updated_date: '2026-09-15 20:39'
labels: []
dependencies: []
type: feature
ordinal: 39500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Richiesta esplicita: rifare il design nella maniera piu minimale che tiene tutte le funzionalita, con elementi trasparenti e senza bordi (stile Revolut), piu denso. Direzione superata rispetto alla precedente: qui nessun elemento disegna una linea, una superficie si riconosce dal riempimento e uno stato dal colore del suo testo con una tinta che lo regge. L'unica linea rimasta sono i separatori dentro le liste.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Nessun elemento disegna un bordo: zero bordi calcolati su tutte e cinque le sezioni, con la sola eccezione delle caselle a scelta, che tengono il loro segno
- [x] #2 Tre livelli di riempimento (5/8/12%) e tinte di stato al 15%: il testo tiene 4.9 nel caso peggiore e le tinte almeno 5.2
- [x] #3 Contrasto misurato sul render reale (pixel piu chiaro rgb(37,33,31)): testo 14.8, tenue 8.0, ottone 10.7, entrate 10.4, uscite 8.1
- [x] #4 Nessun angolo vivo e nessun controllo sotto 44 px in tutte e cinque le sezioni, misurato con prefers-reduced-motion
- [x] #5 I numeri sono piu grandi: titolo di schermata, valore delle metriche e importi a peso 800; griglia e assi dei grafici rimossi
- [x] #6 Spaziatura piu densa, e il blocco che contiene un grafico ha lo stesso riempimento delle tessere
- [x] #7 A fine pagina l'ultimo blocco sta 25 px sopra la capsula; API_VERSION invariato e nessuna dipendenza nuova
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Difetto trovato dall'audit dei bordi calcolati, non a occhio: 13-17 pulsanti per schermata portavano ancora il bordo di sistema del browser (2 px), perche nella riscrittura era andato perso `border: 0`. Ora una regola globale lo toglie a pulsanti, select e campi di testo, lasciando fuori caselle e radio, dove il segno e il controllo.
Incoerenza trovata dalla revisione visiva: il blocco del grafico non aveva riempimento, quindi grafico e legenda galleggiavano mentre le tessere accanto erano lastre. Risolto con `.panel:has(.chart)`, senza toccare il markup.
Il tetto delle tinte e misurato: al 15% il testo colorato tiene 5.2 nel caso peggiore, al 22% il rosso delle uscite e il viola dei giroconti scendono sotto 4.5. Il compromesso del brief senza bordi e dichiarato: un riempimento sottile non arriva al 3:1 che WCAG 1.4.11 chiede a un segno non testuale (5% sta a 1.15, 8% a 1.27, 12% a 1.46), quindi a identificare un controllo restano l'etichetta o il segnaposto che porta dentro e l'anello di fuoco in ottone.
Due rilievi della revisione visiva sono stati smentiti misurando: l'importo di una riga e peso 800 contro 600 del titolo, e a fine pagina l'ultimo blocco sta 25 px sopra la capsula su quattro schermate.

Revisione indipendente: esito corretto, quattro rilievi minori. Chiusi tre: il cursore del grafico era un colore letterale in una fetta che promette token (ora legge --fill-3); la traccia dell'interruttore spento, senza contorno, stava a 1.27 contro il fondo e ora sta al 12% con il compromesso scritto accanto; l'iscrizione in fondo smette di essere una pillola e resta come testo, che e quello che chiedeva la densita. Il quarto, la classe state--empty resa inerte, resta di proposito: e un segnaposto semantico come app e txn--static, che il codice gia tollera, e toglierla da sei punti sarebbe churn senza effetto osservabile.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
L'interfaccia e minimale e senza bordi: tre livelli di riempimento, stati come tinte, forme tutte a pillola, numeri a peso 800, grafici senza griglia ne assi, spaziatura piu densa. Verificato a 390x844 su una copia del ledger: zero bordi calcolati, zero angoli vivi e zero controlli sotto 44 px su tutte e cinque le sezioni (sotto prefers-reduced-motion, perche la cascata distorce le misure); contrasto ricavato dai pixel reali del render; 25 px di margine sopra la capsula a fine pagina. tsc, build e i 314 test passano; nessuna dipendenza nuova, nessuna modifica a route, payload o API_VERSION.
<!-- SECTION:FINAL_SUMMARY:END -->
