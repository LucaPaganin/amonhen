---
id: TASK-26
title: Costruire la sezione assistente di §5.9
status: Done
assignee: []
created_date: '2026-09-13 12:59'
updated_date: '2026-09-13 15:05'
labels: []
dependencies: []
ordinal: 25500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La specifica c'e' (desiderata 0.5, sezione 5.9): una lettura in prosa delle serie e dei budget gia' calcolati, con proposte confermabili e nessuna aritmetica propria. Manca il codice: sezione nell'app, punti di ingresso contestuali, registrazione di domanda e risposta, tetti alle chiamate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La sezione Assistente esiste, si raggiunge dal menu e dichiara il modello e le chiamate rimaste
- [x] #2 Il pacchetto di dati si costruisce dalle stesse funzioni che leggono le schermate
- [x] #3 Ogni cifra nella prosa è una cifra passata: separatori italiani e date normalizzati, e una lettura che ne citi un'altra viene rifiutata e registrata senza mostrarla
- [x] #4 Una proposta fuori vocabolario viene scartata e registrata nel log; una valida aspetta e non viene applicata
- [x] #5 Un budget proposto si accetta con un gesto e finisce nei budget veri, visibile in Conti e budget
- [x] #6 La stessa domanda sugli stessi dati non raggiunge il modello due volte, e l'impronta è quella delle figure
- [x] #7 Tetto giornaliero, stato della sezione e storico con modello, ora e motivo del rifiuto
- [x] #8 Nessun identificativo nel pacchetto: un IBAN dentro una descrizione diventa un segnaposto
- [x] #9 Punti di ingresso contestuali dal cruscotto e dalle righe di budget, con quella figura come contesto
- [x] #10 Verificato nel browser a 390 px, con un endpoint compatibile al posto del fornitore
- [x] #11 Specifica 5.9, 9 e 10, README, web/README e CLAUDE.md aggiornati
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La fase 5 è costruita: una sezione che legge i numeri già calcolati, con tre guardiani in codice invece che nel prompt. Le cifre della prosa si confrontano una per una con quelle passate e una lettura che ne citi un'altra si rifiuta e si registra; le proposte devono nominare merchant e categorie che erano nella richiesta, e una categoria senza budget per il budget; niente identificativi esce dal processo, con gli IBAN sostituiti da un segnaposto. L'impronta che rende gratuita una domanda ripetuta copre le figure e non l'elenco dei merchant proposti, che cambia proprio perché l'assistente ha risposto: il primo giro dal vivo è servito a scoprirlo. Le proposte di categoria aspettano dove aspettano tutte, i budget hanno la loro tabella e il loro gesto, e i punti di ingresso dal cruscotto e dalle righe di budget passano quella figura come contesto.
<!-- SECTION:FINAL_SUMMARY:END -->
