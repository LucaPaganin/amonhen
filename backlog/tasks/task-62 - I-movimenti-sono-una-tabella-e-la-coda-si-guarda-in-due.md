---
id: TASK-62
title: I movimenti sono una tabella e la coda si guarda in due
status: Done
assignee: []
created_date: '2026-09-26 23:36'
updated_date: '2026-09-26 23:57'
labels: []
dependencies: []
references:
  - >-
    C:\Users\lucap\.omp\agent\sessions\-git_repos-amonhen\2026-09-24T18-25-56-868Z_01a0d4aa-c684-7715-8842-e15e80e3b466\local\desktop-shell-plan.md
ordinal: 61500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sopra i 1024px i movimenti diventano una tabella a cinque colonne (data, descrizione, categoria, conto, importo) con l intestazione che resta in cima mentre si scorre, invece di una riga che si allarga fino a 1200px. La coda delle proposte si guarda in due: l elenco da una parte e il dettaglio della proposta scelta dall altra, cosi si categorizza senza aprire niente. Sotto i 1024 resta quello di oggi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Sopra i 1024 i movimenti sono una tabella con intestazione ferma: quattro colonne da 1024 — il conto sta sotto il titolo, misurato: con cinque la descrizione restava 118px, quindici caratteri per riga — e cinque da 1440, con le colonne fisse perche intestazione e righe sono due griglie diverse. Nessuna riga tronca le cifre (colonna importo 144px contro 134 misurati)
- [x] #2 Sopra i 1024 la coda mostra il dettaglio della proposta scelta accanto all elenco, con i comandi nel dettaglio e la scheda scelta raggiungibile anche da tastiera
- [x] #3 Sotto i 1024 movimenti e coda sono identici a prima (otto schermate a 390 e 768, byte per byte)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Misure: intestazione e celle sulla stessa x a 1024, 1280 e 1484 (l etichetta Conto esiste solo da 1440, dove c e la colonna); colonne 83/266/176/144 a 1024 e 83/538/208/144/144 a 1484; intestazione ferma a y=72 (il gettone --appbar 64 piu 8) con la pagina scorsa a 900 su una lista di circa 8600px. Celle peggiori del mese: data 83, conto 126, importo con il progressivo 134, pillola della categoria 293 — quest ultima va a capo nella sua colonna invece di sbordare, e su tutto il mese nessuna cella esce dalla propria colonna.

La coda: .panel--split e 1fr piu 330px, il dettaglio e sticky e contiene select e pulsante veri, la scheda perde i comandi e la riga di quello che la proposta vale (che il dettaglio ripete), una sola scheda e accesa. Il fuoco su una scheda sposta il dettaglio: misurato sulla terza, il pannello passa a Carrefour con l anello di fuoco da 2px. Gli id del campo nuova categoria sono distinti fra i due posti.

Sotto i 1024 non si muove niente: otto screenshot (cruscotto, coda, movimenti, conti a 390 e 768) byte per byte identici al build precedente sullo stesso ledger.

Revisione di gusto, di specifica e di documentazione (tre revisori). Due difetti veri, trovati da due revisori ciascuno: (1) display:contents su .txn__body e .txn__meta non era limitato alla riga dei movimenti, e sopra i 1024 rompeva le righe del cestino in Conti, dove .txn__meta e la riga di testo di una colonna: ora la regola e .txn > .txn__body > .txn__meta e una sonda conferma che fuori dalla riga resta display:flex; (2) sopra i 1024 i comandi vivono nel dettaglio, quindi le schede non avevano piu niente di focalizzabile e onFocusCapture non poteva scattare — la scheda e ora un fermo di tabulazione e il dettaglio segue chi tabula. Poi: id ripetuti fra le due copie dei comandi (il posto entra nell id), il commento a 1440 che prometteva una pillola su una riga sola mentre la colonna resta 208 contro 293 misurati, l intestazione disegnata anche senza righe, due commenti che dicevano cinque colonne sopra i 1024 (sono quattro fino a 1440), e la specifica di prodotto che va registrata a 1.8.

Scostamento dal piano, con la misura che lo giustifica: la fetta 4 chiedeva cinque colonne sopra i 1024 e a 1024 cinque colonne lasciavano alla descrizione 118px, cioe quindici caratteri per riga. Il conto scende sotto il titolo fino a 1440, dove la quinta colonna compare perche c e spazio; il criterio di accettazione e stato riscritto con la misura, non aggirato. Il resto della fetta (coda maestro/dettaglio, intestazione ferma) e consegnato come chiesto.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Sopra i 1024 i movimenti sono una tabella: data, descrizione, categoria, importo, e il conto che si prende una colonna sua da 1440 (a 1024 cinque colonne lasciavano alla descrizione 118px, misurati, quindi il conto sta sotto il titolo come sul telefono). L intestazione resta in cima mentre si scorre, e le colonne sono fisse perche intestazione e righe sono due griglie diverse: con una colonna auto ciascuna l etichetta finiva sopra la colonna sbagliata. Le misure vengono dal contenuto peggiore del mese e una pillola lunga va a capo nella sua colonna invece di sbordare. La coda si guarda in due: le proposte a sinistra, il dettaglio di quella scelta a destra con i suoi comandi, cosi si decide senza aprire niente; i comandi sono scritti una volta e resi in due posti, con il foglio che spegne quello che la larghezza non chiede. Verificato: intestazione e celle sulla stessa x a tre larghezze, niente che sborda su tutto il mese, intestazione ferma a y=72 con la pagina scorsa, il fuoco su una scheda che sposta il dettaglio, e otto screenshot a 390 e 768 byte per byte identici al build precedente. Revisione di gusto, di specifica e di documentazione: due difetti veri corretti (il display:contents che rompeva il cestino in Conti, la coda non raggiungibile da tastiera) piu quattro rilievi minori. Specifica a 1.8, README e CLAUDE.md aggiornati. Build e test verdi.
<!-- SECTION:FINAL_SUMMARY:END -->
