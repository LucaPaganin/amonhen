---
id: TASK-57
title: 'Provare in Docker il primo avvio e il ripristino, da zero e ripetibile'
status: Done
assignee: []
created_date: '2026-09-26 08:51'
updated_date: '2026-09-26 09:26'
labels: []
dependencies:
  - TASK-55
  - TASK-56
ordinal: 56500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il primo avvio non e mai stato provato in un container: il setup guidato scrive accounts.json e private.pem dentro una cartella montata scrivibile, e la prova e sempre stata fatta con uv run sull host. Il NAS sara la prima installazione vera, e li un errore di proprieta o di percorso si scopre solo davanti alla cosa rotta. Serve una prova ripetibile che riproduca la forma del NAS (cartella di configurazione di uid 10001, volume del ledger, immagine costruita dal checkout, wizard pilotato dal browser) e che non consumi un consenso vero: uno stub di Enable Banking che risponde dalle fixture anonimizzate gia nel repo copre i cinque passi del wizard senza toccare il pannello EB.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 tools/eb_stub.py risponde ad aspsps, auth, sessions, details, balances e transactions dalle fixture in tests/fixtures/enable_banking, senza verificare la firma del JWT, e ascolta su tutte le interfacce del suo container
- [x] #2 tools/rehearse_local.sh prepara la cartella di prova (albero copiato su ext4, deploy con il compose del repo e un override, chiave RSA), costruisce l immagine dal checkout, avvia lo stub e l app, e passa dal container per il chown di /config e /backups
- [x] #3 Scrivere in /config fallisce prima del chown ed e permesso dopo: e la prova che la nota del README sul NAS e vera
- [x] #4 Il wizard si percorre per intero nel browser: passo 1 scrive accounts.json e private.pem posseduti da 10001 10001 dentro il mount, il passo 2 elenca le banche dello stub e la scelta porta al callback, i passi 3-5 arrivano al saldo dichiarato e il conto risulta verificato
- [x] #5 docker compose exec -T amonhen python -m amonhen backup --dest /backups produce lo snapshot, e ripristinarlo nel volume riporta l app agli stessi movimenti
- [x] #6 README.md, CLAUDE.md e desiderata-monitoring-finanziario.md (nuova sezione sul backup, versione alzata) descrivono comando, cron, ripristino e la prova locale
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fatto: tools/eb_stub.py (rotte aspsps/auth/sessions/details/balances/transactions dalle fixture, ascolta su 0.0.0.0, nessuna verifica di firma, ogni richiesta a stdout con rotta e parametri); tools/rehearse_local.sh (copia il checkout su ext4 dentro WSL, scrive l override con !override per le porte, genera la chiave RSA, costruisce l immagine dal checkout, provo /config prima e dopo il chown passando dall immagine, aspetta healthy, stampa i controlli e la chiusura); documentazione in README.md, CLAUDE.md e desiderata (versione 1.5, §5.11, fase 8).

Verifica (tutta eseguita): motore avviato con Docker Desktop, integrazione WSL gia attiva; prova rilanciata due volte da zero. Scrivere in /config prima del chown e rifiutato e dopo e permesso; il wizard percorso davvero (credenziali -> key_loads vero, conti scritti di 10001 dentro il mount; banca -> Fineco e Revolut dallo stub e ritorno su /?setup=1; conti -> start_sync_date 2025-01-01 in accounts.json; primo sync -> 4 nuovi, 2 saldi, conto verificato; saldi -> dichiarato CLBD -339.30 registrato come manual:booked); cruscotto col segno nuovo; snapshot e ripristino; docker compose config verde. Corretto un difetto trovato dalla prova: la chiusura stampata non poteva cancellare i file di proprieta 10001 — ora la sequenza passa dall immagine, ed e stata verificata sul caso reale. Il container non propaga il codice di uscita dei comandi exec (verificato con exit 7 e sys.exit(3)): limite dell ambiente, i codici della CLI sono corretti sull host.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La prova del primo avvio ora si fa prima del NAS. tools/eb_stub.py risponde alle rotte che il client EB usa davvero (aspsps, auth, sessions, details, balances, transactions) leggendo le fixture anonimizzate, senza verificare la firma: provato rotta per rotta, con CLBD contabile distinto da ITAV dove le fixture hanno righe PDNG e uguale dove sono tutte BOOK. tools/rehearse_local.sh copia il checkout su ext4 dentro WSL, scrive override e .env, genera la chiave RSA, costruisce l immagine dal checkout, e passa dall immagine per il chown. Percorsa per intero due volte da zero: la scrittura in /config e rifiutata prima del chown e permessa dopo; il wizard e stato camminato davvero nel browser (credenziali con key_loads vero, conti scritti di 10001 10001 dentro il mount, Fineco e Revolut elencate dallo stub e ritorno su /?setup=1, start_sync_date 2025-01-01 in accounts.json, primo sync 4 movimenti, CLBD dichiarato registrato come manual:booked); cruscotto col segno nuovo; snapshot in /backups e ripristino che riporta il ledger a 4 movimenti. Documentazione aggiornata in README.md, CLAUDE.md e desiderata (1.5, §5.11, fase 8). Difetti trovati e corretti dalla prova e dalle revisioni: la sequenza di chiusura non poteva cancellare i file di proprieta 10001 (ora passa dall immagine, verificata sul caso reale), la prova non falliva se l app non diventava healthy, e la sonda prima del chown accettava come prova anche un container fermo.
<!-- SECTION:FINAL_SUMMARY:END -->
