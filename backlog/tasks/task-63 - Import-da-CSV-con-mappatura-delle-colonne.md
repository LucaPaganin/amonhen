---
id: TASK-63
title: Import da CSV con mappatura delle colonne
status: Done
assignee: []
created_date: '2026-09-26 23:36'
updated_date: '2026-09-27 00:10'
labels: []
dependencies: []
ordinal: 62500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Un file CSV di movimenti si carica dall app: si scelgono le colonne (data, descrizione, importo o entrate e uscite, conto), il formato della data e dei decimali, e si vede un anteprima delle prime righe con la mappatura applicata. L import scrive nel ledger con lo stesso percorso dei movimenti sincronizzati: un movimento gia presente si salta invece di duplicarlo. Prima passata, da raffinare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il CSV si carica dall app e le colonne si mappano a mano
- [x] #2 Anteprima delle righe mappate prima di importare
- [x] #3 L import scrive nel ledger e riporta quanti movimenti sono entrati e quanti erano gia presenti
- [x] #4 Un file con righe rotte non ferma l import: si riportano le righe rifiutate
- [x] #5 Test del percorso di import (mappatura, decimali, segno, duplicati)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Backend scritto da un implementer delegato e verificato da me: amonhen/csv_import.py (mappatura -> CsvProfile, la frase di cosa manca, il file temporaneo, l anteprima, la lettura mappata), i due endpoint in api.py (anteprima e import, con API_VERSION 18 -> 19 e il tetto di 8 MB), tests/test_csv_import.py. La lettura tollerante sta nell adattatore (read_csv) e parse_csv resta severo: i suoi test, compreso il match su line 3, sono invariati e verdi.

Prova vera nel browser a 1484 con un estratto di tre righe in forma Fineco (punto e virgola, date e decimali italiani, Dare e Avere, una riga con abc): il file si carica, col separatore sbagliato i menù offrono una colonna sola, con il punto e virgola ne offrono quattro; mappando data, formato, descrizione, Dare, Avere e decimali l anteprima mostra 2 righe (-12,30 € Spesa supermercato, 1500,00 € Stipendio) e la riga rifiutata (riga 4: unparseable amount abc). Il primo import risponde 2 movimenti entrati su 2 piu 1 riga da rileggere; reimportando lo stesso file risponde 0 movimenti entrati su 2, 2 gia presenti: e l idempotenza che la specifica chiede, vista dall interfaccia.

Un secondo file con un altra forma (virgole, date ISO) nella stessa sessione: i menù si ripopolano da soli e i nomi di colonna del file precedente cadono (prune), quindi si mappa senza ricaricare la pagina; le scelte di forma (separatore, formato della data, decimali) restano quelle della banca di prima, e vanno rifatte — il separatore per primo, perche con quello sbagliato l intestazione si legge come una colonna sola.

Sotto i 1024: otto screenshot (cruscotto, coda, movimenti, conti a 390 e 768) byte per byte identici al build precedente. Cassetto e rail guadagnano la voce Importa per progetto; la barra in basso no, perche la sezione e inBar: false, ed e per questo che le quattro schermate combaciano.

Revisione di gusto, di specifica e di documentazione (tre revisori). Due difetti veri: (1) i due posti della descrizione si richiudevano al salvataggio, quindi una parte mappata nella Seconda saltava al primo posto e spariva appena si riempiva il primo — corretto tenendo i due posti come due posti e lasciando al server lo scarto di quelli vuoti, verificato mappando la seconda per prima; (2) vicolo cieco su un secondo file con un altra intestazione: l anteprima lo rifiutava e il client svuotava i menù che costruisce dalla risposta, lasciando il file non mappabile fino al ricaricamento — corretto chiedendo prima la sola intestazione (che non puo essere rifiutata) e lasciando cadere i nomi che in questo file non esistono, verificato con due file di forma diversa nella stessa sessione. Altri rilievi accolti: l esito leggeva solo entrati e duplicati delle cinque azioni, quindi un movimento riportato dal cestino si leggeva come zero entrati (ora promoted, reimported e suppressed sono nominati come nella riga del sync); mancava la codifica del file, che per un estratto italiano e latin-1 (aggiunta: UTF-8 o Windows-1252/Latin-1, decodificata nel browser); la versione 18 era rimasta in due documenti; i conteggi delle sezioni in due paragrafi di navigazione; e la specifica diceva che un export CSV non porta un external_id mentre la schermata offre quella colonna (e quando la si mappa e l identificativo, non l impronta, a fare da identita).

Bordi ruvidi dichiarati di questa prima passata, da raffinare: il motivo di una riga rifiutata e la frase inglese del parser (come ogni detail del backend); un secondo file di un altra banca richiede di rifare le scelte di forma; la colonna dell identificativo della banca e offerta ma niente spiega quando serve; e la prova dell idempotenza fatta dalla schermata e file contro se stesso, mentre la sovrapposizione fra sync e import e coperta dal test del ledger che c era gia.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Un estratto conto in CSV entra nel ledger dall app: la sezione Importa prende il file, si scelgono le colonne (separatore, righe da saltare, data e suo formato, importo oppure Dare e Avere, decimali, una o due colonne di descrizione, identificativo della banca, segno), il conto, e la codifica del file; l anteprima mostra le righe mappate con i loro numeri di riga prima che qualcosa venga scritto, e l import dice quanti movimenti sono entrati, quanti erano gia presenti, quanti sono tornati dal cestino, quanti sono stati lasciati fuori e quante righe non si leggono. Sotto il cofano e il percorso della riga di comando: la mappatura diventa un CsvProfile costruito a runtime, le righe passano da read_csv a record_batch e poi da giroconti, passthrough e regole. Verificato nel browser a 1484 con un estratto italiano di tre righe, una rotta: 2 movimenti entrati, la riga rotta riportata con la sua riga, e reimportando lo stesso file 0 entrati e 2 gia presenti (l idempotenza che la specifica chiedeva). Un secondo file di forma diversa si mappa nella stessa sessione. Sotto i 1024 otto schermate byte per byte identiche. Revisione di gusto, specifica e documentazione: due difetti veri corretti (i due posti della descrizione, il vicolo cieco sul secondo file) piu cinque rilievi minori (l esito che ignorava cestino e soppressi, la codifica mancante, due documenti con la versione vecchia, i conteggi delle sezioni, la specifica sull external_id). API 18 -> 19 su entrambi i lati, specifica a 1.9, README, CLAUDE.md e web/README.md aggiornati. 394 test verdi.
<!-- SECTION:FINAL_SUMMARY:END -->
