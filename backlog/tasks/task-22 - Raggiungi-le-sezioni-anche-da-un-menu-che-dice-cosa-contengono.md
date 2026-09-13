---
id: TASK-22
title: 'Raggiungi le sezioni anche da un menu, che dice cosa contengono'
status: Done
assignee: []
created_date: '2026-09-13 12:28'
updated_date: '2026-09-13 12:29'
labels: []
dependencies: []
ordinal: 21500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La barra in basso ha cinque colonne: a 390 px ogni sezione ha diritto a una parola, e una sezione mai aperta resta un'indovinello. Il menu in alto apre un cassetto che le nomina per esteso, dice cosa contengono e mostra il conteggio di quello che aspetta; le due vie rendono dalla stessa lista di sezioni.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 In alto c'e' una barra con l'hamburger, e il tocco apre un cassetto che elenca le cinque sezioni con il nome per esteso, una riga che dice cosa contengono e il conteggio di cio' che aspetta
- [x] #2 Scegliere una voce cambia sezione e chiude il cassetto, e il focus torna all'hamburger
- [x] #3 Il cassetto si chiude anche con Escape e toccando fuori dal pannello
- [x] #4 Da chiuso non intercetta tocchi e non e' raggiungibile da tastiera (inert), e a schermo non copre il contenuto: la barra superiore ha il suo spazio e a 390 px non c'e' scorrimento orizzontale
- [x] #5 La barra in basso continua a cambiare sezione con un tocco, con le stesse etichette e la stessa pastiglia di prima
- [x] #6 Le cinque sezioni e le loro icone sono dichiarate una volta sola e le due vie rendono dalla stessa lista (TabBar.tsx rimossa, Navigation.tsx)
- [x] #7 Verificato in browser a 390 px: apertura, scelta, Escape, tocco fuori, focus nel pannello, aria-expanded e aria-current su entrambe le vie, piu' la lettura visiva a cassetto aperto e chiuso
- [x] #8 Build tsc e vite pulita; README, web/README, CLAUDE.md e specifica alla 0.4 aggiornati
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
La barra in basso resta: cambiare sezione con un tocco e' l'azione piu' frequente, quindi il menu si aggiunge. Se il menu basta, la barra si toglie in una riga e la schermata si allarga di 62 px in fondo.

Il primo tentativo nascondeva il cassetto con visibility piu' transizione: il focus sul pannello al primo apri di una pagina fresca non era affidabile (misurato: document.activeElement restava fuori). Sostituito con inert piu' transform fuori schermo: il pannello e' focusabile appena si apre, e da chiuso non e' ne' un bersaglio di tocco ne' una tappa di tabulazione.

La sonda in scheda headless ha mostrato un rect negativo del pannello (right=-6) mentre il cassetto era aperto: con le transizioni disattivate il rect torna corretto (0..320), quindi era la transizione non avanzata in una scheda in background, non un difetto. Verificato anche in visione, dove il cassetto risulta aperto e in ordine.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Due vie per cambiare sezione: la barra in basso, che cambia con un tocco, e l'hamburger in una barra nuova in alto, che apre un cassetto con nome per esteso di ogni sezione, una riga su cosa contiene e il conteggio di cio' che aspetta. Le cinque sezioni e le icone sono dichiarate una volta in Navigation.tsx (TabBar.tsx rimossa) e le due vie rendono dalla stessa lista: etichette aria, pastiglia del conteggio e ordine restano identici. Il cassetto si chiude su scelta, Escape e tocco fuori, porta il focus dentro di se' all'apertura e lo restituisce all'hamburger alla chiusura; da chiuso e' inert e non intercetta tocchi. Impaginazione aggiornata (--appbar, e .app__main--plain per la schermata del server vecchio). Verificato a 390 px in browser su tutte le interazioni piu' due letture visive senza difetti; build tsc e vite pulita; documenti e specifica 0.4 aggiornati.
<!-- SECTION:FINAL_SUMMARY:END -->
