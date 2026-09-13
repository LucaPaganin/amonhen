---
id: TASK-10
title: Le regole si gestiscono da una sezione dell'app
status: Done
assignee: []
created_date: '2026-09-12 19:40'
updated_date: '2026-09-12 19:43'
labels: []
dependencies: []
type: feature
ordinal: 9500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi una regola nasce solo accettando una proposta dalla coda (o dalla CLI) e non si può più né vedere né correggere: `GET/POST /api/rules` esistono ma nessuna schermata li usa, e non c'è modo di cambiare categoria o rimuovere una regola. Serve una sezione che le mostri, dica quanto pesa ciascuna, e permetta di crearle, correggerle e rimuoverle — con l'effetto sui movimenti già importati reso esplicito.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una sezione "Regole" elenca ogni regola con la categoria e con quanti movimenti tiene adesso
- [x] #2 Si crea una regola (merchant + categoria) dalla sezione, e i movimenti già importati di quel merchant senza categoria vengono categorizzati subito
- [x] #3 Si cambia la categoria di una regola e i movimenti che teneva la seguono; un movimento categorizzato a mano su un altro merchant non viene toccato
- [x] #4 Si rimuove una regola e i suoi movimenti tornano «senza categoria» in coda; ricreandola tornano come prima
- [x] #5 Movimenti con split e gambe di giroconto non entrano nei conteggi né negli spostamenti
- [x] #6 Verifica: test verdi e uso reale dal browser (creare, correggere, rimuovere, e il badge della coda che cambia di conseguenza)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Nuova sezione Regole. Il backend c'era a metà: GET/POST /api/rules esistevano ma nessuna schermata li usava, e non si poteva né cambiare categoria né rimuovere. Ora MerchantBook.set_rule applica subito il cambiamento (una regola nuova categorizza chi aspettava, una corretta sposta i movimenti che teneva) e remove_rule li riporta in coda, quindi rimuovere è reversibile e la colonna dei conteggi smaschera le regole che non pescano nulla — sul ledger reale ne ha trovata subito una, Cart  Srl con 0 movimenti, morta per un doppio spazio nel nome. La chiave della regola ora passa da rule_key, che comprime gli spazi: un nome scritto a mano arriva alle descrizioni, che hanno solo spazi singoli. Conteggi e spostamenti saltano split e gambe di giroconto, e una regola non può puntare a Uncategorized. Verificato live: creata Iliad Italia (3 movimenti, backlog 215 -> 212, proposta consumata 14 -> 13), corretta (i 3 l'hanno seguita), rimossa (3 tornati in coda, 212 -> 215). Corretto anche un difetto trovato proprio in verifica: accettando una proposta la lista restava vecchia finché non premevi Aggiorna, ora la sezione ricarica quando la apri. 224 test.
<!-- SECTION:FINAL_SUMMARY:END -->
