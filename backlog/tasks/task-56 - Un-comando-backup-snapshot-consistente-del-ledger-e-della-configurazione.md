---
id: TASK-56
title: 'Un comando backup: snapshot consistente del ledger e della configurazione'
status: Done
assignee: []
created_date: '2026-09-26 08:51'
updated_date: '2026-09-26 09:26'
labels: []
dependencies: []
ordinal: 55500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il ledger vive in un volume nominato e la configurazione in una cartella montata, e niente li copia: non esiste un backup. Copiare il file del database mentre l app scrive puo produrre una copia strappata, quindi la copia si fa con l API di backup di SQLite, che lavora su un database vivo. Serve anche il ripristino, perche uno snapshot che non si sa rimettere non e un backup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 amonhen backup --dest DIR scrive uno snapshot in DIR/<2026-09-26T101500Z>/ con amonhen.db, la configurazione (accounts.json e la chiave che nomina) e un manifest.json con created_at, percorso sorgente, sha256 del database scritto, i tre conteggi e l elenco dei file di configurazione copiati
- [x] #2 Il database dello snapshot si legge: amonhen --db <snapshot>/amonhen.db validate esce 0 e la CLI accounts elenca gli stessi conti del ledger vivo
- [x] #3 Un ledger senza conti non produce snapshot: il comando esce 1 e non crea nessuna cartella, perche sqlite3.connect creerebbe un database vuoto e il backup sembrerebbe riuscito
- [x] #4 --keep N tiene gli N snapshot piu recenti e cancella gli altri; --keep 0 non pota niente; una scrittura interrotta non lascia in DIR una cartella che sembra uno snapshot buono
- [x] #5 Il container ha /backups, montato da ./backups, e il cron del NAS puo chiamare il comando dentro il container scrivendo li
- [x] #6 uv run pytest -q passa
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fatto: amonhen/backup.py (Snapshot, make_snapshot: conn.backup su database vivo, scrittura in .<stamp>.partial e rename finale, manifest con created_at/source/db_sha256/conteggi/configurazione copiata, ritenzione su ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$); amonhen/cli.py (sottocomando backup con --dest obbligatorio e --keep 14, cmd_backup che rifiuta un ledger senza conti, HANDLERS, import sqlite3); Dockerfile crea /backups di 10001, compose monta ./backups, .gitignore e .dockerignore la escludono; tre test in tests/test_amonhen_cli.py.

Verifica: uv run pytest -> 380 passed; snapshot preso dentro il container della prova (/backups/<stamp>/ con amonhen.db, accounts.json, private.pem, manifest.json, tutti di 10001) e ripristinato: dopo aver cancellato un movimento dal ledger vivo, il ritorno dallo snapshot lo riporta e /api/transactions torna a 4. Ledger vuoto: esce 1 e non crea la cartella (verificato anche con uv run python -m amonhen e uv run amonhen).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
amonhen backup scrive uno snapshot consistente: amonhen/backup.py copia il database vivo con l API di backup di SQLite (conn.backup, non una copia di file), in una cartella temporanea che prende il nome datato solo alla fine, con manifest.json (created_at, percorso sorgente, sha256, conteggi letti dalla copia, elenco della configurazione copiata), piu accounts.json e la chiave che pem_path nomina. cli.py registra il sottocomando (--dest obbligatorio, --keep 14) e cmd_backup rifiuta un ledger senza conti, perche sqlite3.connect creerebbe un database vuoto e il backup sembrerebbe riuscito. Il container ha /backups (Dockerfile) montato da ./backups (compose). Verificato con uv run pytest -q (380 passed, tre test nuovi, di cui uno sul caso fuori ordine della ritenzione) e dentro il container della prova: snapshot in /backups/<stamp>/ di proprieta 10001, ripristinato dopo aver cancellato un movimento — il ledger torna a 4 movimenti. Una revisione indipendente ha trovato e fatto correggere due difetti reali: la ritenzione poteva cancellare lo snapshot appena scritto quando il suo nome non era il piu recente (ora la cartella scritta e esclusa dal confronto, con test di regressione che riproduce il caso), e i conteggi del manifest venivano letti dal ledger vivo invece che dalla copia.
<!-- SECTION:FINAL_SUMMARY:END -->
