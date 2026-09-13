---
id: TASK-11
title: Regole per testo contenuto nella descrizione
status: Done
assignee: []
created_date: '2026-09-13 08:24'
updated_date: '2026-09-13 08:44'
labels: []
dependencies: []
ordinal: 10500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Una regola e' oggi il nome esatto del negoziante ridotto da merchant_name: per coprire le varianti che la banca scrive servono tante regole quanti sono i nomi, ed e' quello che l'utente vede come una pila ingestibile. Il criterio utile e' la sottostringa: la regola e' un testo che la descrizione contiene, cosi' una sola regola copre una famiglia di movimenti (es. i versamenti, gli addebiti SDD, un gestore ricorrente). Da qui discende la precedenza quando due regole combaciano, e cosa succede ai movimenti quando una regola nasce, cambia o sparisce.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una regola e' un testo confrontato con la descrizione, senza distinzione di maiuscole e con gli spazi normalizzati
- [x] #2 Se piu' regole combaciano decide quella con il testo piu' lungo, e a parita' di lunghezza l'ordine alfabetico, cosi' due esecuzioni scelgono la stessa
- [x] #3 Creare o correggere una regola fa seguire i movimenti che essa spiega, anche quelli tenuti da un'altra regola; una categoria scelta a mano non viene sovrascritta
- [x] #4 Rimuovere una regola passa i suoi movimenti alla regola piu' ampia che combacia ancora, e li riporta in coda se non ne resta nessuna
- [x] #5 Le regole esistenti migrano nella nuova tabella mantenendo categoria e peso, e la tabella dei negozianti non serve piu'
- [x] #6 GET /api/rules riporta testo, categoria e peso; POST /api/rules accetta il testo; API_VERSION e REQUIRED_API_VERSION allineati
- [x] #7 La sezione Regole dice che il testo viene cercato nella descrizione e ogni riga mostra il peso attuale
- [x] #8 rules, rule-add e rule-remove parlano di testo e mostrano il peso; categorize resta invariato
- [x] #9 Suite verde e verifica dal vivo su una copia del ledger reale, con una regola larga che assorbe piu' negozianti
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verificato: 239 test verdi; sul ledger reale (copia) le 24 regole migrano con lo stesso peso, 0 movimenti spostati e coda invariata a 203; dal browser una regola larga (iliad) prende 7 movimenti e la coda passa da 203 a 196 e torna; lettura della schermata da parte di un modello di visione senza difetti di layout. La revisione indipendente ha trovato un difetto vero: una regola legacy oscurata da un testo piu' lungo lasciava il movimento sotto una categoria che nessuna regola assegna (peso 0, rimozione che non rilasciava nulla) - corretto decidendo la proprieta' del movimento con qualunque regola che combacia, con test di regressione che fallisce senza la correzione.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Le regole sono un testo cercato nella descrizione: vince il piu' lungo, una categoria che nessuna regola combaciante assegnerebbe resta, e scrivere una regola riscrive subito il ledger (una nuova prende cio' che vince, una corretta sposta cio' che teneva, una rimossa lascia i movimenti alla regola piu' ampia o alla coda). La tabella merchants sparisce, con migrazione che conserva ogni regola. Il contratto /api/rules parla pattern/held e API_VERSION va a 5. Verificato con la suite (239 test), la migrazione sul ledger reale (24 regole, pesi identici, nessun movimento mosso) e la prova dal vivo di lista, creazione e rimozione.
<!-- SECTION:FINAL_SUMMARY:END -->
