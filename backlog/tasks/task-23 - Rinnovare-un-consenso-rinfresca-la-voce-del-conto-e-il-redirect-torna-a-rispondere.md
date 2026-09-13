---
id: TASK-23
title: >-
  Rinnovare un consenso rinfresca la voce del conto, e il redirect torna a
  rispondere
status: Done
assignee: []
created_date: '2026-09-13 12:59'
updated_date: '2026-09-13 13:00'
labels: []
dependencies: []
ordinal: 22500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il consenso Fineco e' morto mentre la sua sessione risultava ancora autorizzata, e rinnovarlo non poteva riuscire: accounts.json manda il browser a <tailnet>:3000/callback, la porta della vecchia app Flask, dove non ascolta piu' nessuno. In piu' /callback accodava una seconda voce per un conto che c'era gia', e il ledger, che riconosce i conti per nome, l'avrebbe fusa nello stesso conto reimportando la storia sotto di essa.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 /callback rinfresca la voce di un conto gia' noto (stesso uid): sessione nuova, notes e start_sync_date conservati
- [x] #2 Un conto mai visto viene aggiunto, e la risposta dice per ognuno se e' stato rinfrescato o aggiunto
- [x] #3 La voce prende session_expiry dalla sessione appena creata e conserva le chiavi messe a mano
- [x] #4 La ricetta per rinnovare un consenso e' documentata: indirizzo del browser, redirect_url e registrazione Enable Banking devono coincidere, col nome ASPSP esatto (FinecoBank, verificato dal vivo)
- [x] #5 Quattro test nuovi (tre sul writer, uno sul callback) e suite verde (281)
- [x] #6 Specifica 5.1, README e CLAUDE.md aggiornati
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
La diagnosi: la sessione Fineco risponde ancora (elenca 4 uid) mentre transazioni e dettagli danno 401/403, e il redirect_url nel accounts.json vero e' https://sukuna.cormorant-bleak.ts.net:3000/callback - la porta della vecchia app Flask. Il browser del telefono non arriva da nessuna parte, quindi nessun rinnovo poteva completarsi. Le tre cose che devono coincidere: indirizzo del browser, redirect_url nel file, registrazione nel dashboard Enable Banking.

Perche' la chiave del rinfresco e' l'uid: la stessa coppia di uid compare nelle liste di due sessioni diverse (Revolut personale e cointestato, sessioni separate, entrambe elencano entrambi i conti), quindi l'uid e' l'identita' stabile del conto e la sessione no. Chiave su (session_id, account_uid) significava accodare; il ledger riconosce i conti per nome (notes), quindi la seconda voce sarebbe finita nello stesso conto reimportando la storia con start_sync_date di oggi.

Verifiche: nome ASPSP esatto preso dal vivo (FinecoBank), comando di HEALTHCHECK eseguito contro un server vivo (exit 0), suite a 281 test. Non verificato: il rinnovo vero, che ha bisogno del login bancario nel browser.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il rinnovo di un consenso rinfresca la voce del conto invece di accodarne una seconda: la chiave e' l'uid, che sopravvive alle sessioni, e notes e start_sync_date restano perche' il primo e' il nome con cui il ledger conosce il conto e la seconda e' la storia gia' importata. Il callback riporta in written cosa ha scritto (refreshed o added) e registra session_expiry della sessione nuova. Documentata la ricetta completa: le tre URL che devono coincidere, il nome ASPSP esatto (FinecoBank, verificato dal vivo) e tailscale serve per servire la callback su HTTPS. Resta all'utente registrare la URL nel dashboard Enable Banking e fare il login.
<!-- SECTION:FINAL_SUMMARY:END -->
