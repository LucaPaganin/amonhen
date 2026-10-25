---
id: TASK-71
title: Un conto si sincronizza su un periodo scelto, anche nel passato
status: Done
assignee: []
created_date: '2026-10-25 23:00'
updated_date: '2026-10-25 23:59'
labels:
  - connettore
  - sync
dependencies: []
type: feature
ordinal: 70500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi la sync non lascia scegliere il periodo, e alcune banche rifiutano le richieste su intervalli troppo lunghi. Serve poter sincronizzare **un conto** con Enable Banking su un periodo **da-a** scelto da chi la lancia, anche nel passato, senza creare doppioni.

Come funziona oggi (dal codice):
- `SyncService._start_date` decide da solo l'inizio: `MAX(date)` del conto meno `SYNC_OVERLAP_DAYS` (7), oppure `start_sync_date` / 90 giorni su un conto vuoto. La fine è sempre oggi. Un buco in mezzo allo storico non viene mai richiesto di nuovo, perché il cursore è l'ultima data.
- `EnableBankingClient.fetch_transactions` spezza l'intervallo in finestre fisse di 30 giorni (`_WINDOW_DAYS`), uguali per tutte le banche. Se una sola finestra fallisce l'eccezione risale, e `_sync_account` scarta **tutte** le finestre già scaricate di quel conto: non viene scritto niente.
- `link_transfers(since=_earliest_start())` parte dal più piccolo `start_sync_date`: movimenti più vecchi di quella data non vengono mai abbinati come trasferimenti.

Il limite PSD2 resta: molte banche servono circa 90 giorni qualunque periodo si chieda (CLAUDE.md, *PSD2 returns only ~90 days*), e alcune danno più storico solo subito dopo l'autorizzazione. La feature non lo aggira. Deve però rendere visibile cosa la banca ha restituito per ogni finestra, così che un periodo vuoto non sembri un periodo coperto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Si lancia una sync di un solo conto su un periodo `from`/`to` (date incluse) da riga di comando (`amonhen sync --account <nome> --from AAAA-MM-GG --to AAAA-MM-GG`), dall'API e dall'app, dove l'azione sta nel pannello del conto in **Conti**. La sync normale senza periodo resta identica a oggi.
- [x] #2 Il periodo viene validato prima di chiamare la banca: `from <= to`, `to <= oggi`, conto esistente e collegato a Enable Banking (con `account_uid`). Se non va bene risponde 422 con il motivo; con una sync già in corso risponde 409 (`SyncBusy`, lo stesso lock della sync normale).
- [x] #3 La larghezza della finestra si imposta per conto (per esempio `max_window_days` in `accounts.json`, default 30). Quando la banca rifiuta una finestra perché il periodo è troppo lungo, la finestra si dimezza fino a 1 giorno prima di arrendersi. Le finestre restano allineate a giorni interi, perché `record_batch` numera i movimenti identici dello stesso giorno (`:r2`, `:r3`) e un giorno spezzato fra due lotti cambierebbe quella numerazione.
- [x] #4 Un errore su una finestra non butta via le altre. Le finestre riuscite vengono scritte, e il risultato elenca le finestre fallite con date e errore della banca, così si possono riprovare con un periodo più stretto. Il risultato riporta anche quanti movimenti ha restituito ogni finestra.
- [x] #5 Il dedup tiene. Rilanciare lo stesso periodo non scrive nulla (tutto `duplicate`). Un movimento cancellato a mano resta `suppressed`, salvo `reimport_deleted` attivo sul conto. La promozione da `PDNG` a `BOOK` funziona come nella sync normale. Tutto passa da `Ledger.record`, senza un percorso di scrittura parallelo.
- [x] #6 Sovrapposizione con l'import da file. I periodi passati sono proprio quelli che di solito arrivano da CSV/OFX, e lì l'unico discriminante è il content hash, che contiene la **descrizione**. Se la banca scrive la descrizione in PSD2 in modo diverso dall'export, lo stesso movimento entrerebbe due volte. Prima di scrivere c'è un'anteprima: per ogni movimento dice se è nuovo o già presente, e segnala come *probabile doppione* quello con stesso conto, data e importo di un movimento con `source` diversa ma descrizione diversa. **Un probabile doppione non viene scritto**: resta in attesa finché una persona decide, uno per uno, se scriverlo o scartarlo, e il risultato riporta quanti ne aspettano.
- [x] #7 Il cursore della sync incrementale non si sposta. Dopo una sync su un periodo passato, la sync normale successiva parte dallo stesso punto di prima. `start_sync_date` non viene mai modificato, nemmeno da un periodo più vecchio di quella data, e non limita il periodo scelto a mano.
- [x] #8 Dopo la scrittura girano gli stessi passi della sync normale: `link_transfers` con `since` uguale all'inizio del periodo (non `_earliest_start`), poi `link_passthrough_legs`, `validate` e `categorize`.
- [x] #9 La verifica della sezione 5.4 resta leggibile. I movimenti prima di `opening_date` non cambiano il saldo calcolato, perché sono già contati nell'apertura. Quelli che riempiono un buco dopo `opening_date` sì. Il risultato riporta lo stato di verifica di ogni conto dopo la sync: un `mismatch` comparso dopo una sync su un periodo passato è il segnale di un doppione.
- [x] #10 Test con le fixture anonimizzate, e nessuna chiamata di rete vera. Provider: dimezzamento della finestra su un rifiuto, fallimento parziale. Sync: periodo nel passato, rilancio idempotente, tombstone, cursore invariato, trasferimenti nel periodo. API e CLI: validazione e 409.
- [x] #11 Desiderata aggiornato nella sezione della sync, con versione e cosa cambia. `API_VERSION` e `REQUIRED_API_VERSION` aumentati se cambia la forma delle risposte. README e CLAUDE.md descrivono il comando, l'endpoint e il rischio di doppioni con l'import.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Provider: `fetch_transactions` restituisce i movimenti per finestra con l'esito di ciascuna, invece di una lista unica che si perde al primo errore. La finestra si configura e si dimezza quando la banca la rifiuta.
2. `SyncService`: un metodo per un solo conto e un periodo esplicito, che non usa `_start_date`. Scrive ogni finestra riuscita con `record_batch` (una transazione per lotto, già così da v1.4.2), poi abbina i trasferimenti da `from`.
3. Anteprima: lo stesso percorso in sola lettura (le ricerche di dedup senza `_insert`), più la ricerca dei probabili doppioni con l'altra `source`. I probabili doppioni non passano da `record_batch`: vengono tenuti col loro payload e scritti con `record` solo quando una persona dice di sì, uno per uno.
4. Superfici: argomenti di `amonhen sync`; il corpo opzionale `{account, from, to}` su `POST /api/sync` oppure un endpoint dedicato (scelta tecnica, da fare implementando); nel pannello del conto in **Conti** il periodo, il risultato per finestra e la lista dei probabili doppioni con *scrivi* / *scarta*.
5. Test, spec, documentazione.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decisioni dell'utente (2026-10-25):
- I probabili doppioni rispetto all'import non vengono scritti: si chiede caso per caso (AC #6).
- `start_sync_date` non si sposta, nemmeno per un periodo più vecchio (AC #7).
- L'azione nell'app sta nel pannello del conto in **Conti** (AC #1).

Resta da decidere implementando: dove si tengono i probabili doppioni in attesa (tabella nuova o la risposta dell'anteprima rimandata dal client) e se sopravvivono a un riavvio.

Decisioni prese implementando:
- I probabili doppioni stanno in una tabella nuova, `held_transactions`, e sopravvivono a un riavvio: il movimento com'è arrivato, la sua occorrenza nel lotto, la riga a cui somiglia e la decisione (`pending` / `written` / `discarded`). Chiave `(conto, identità)` come la scriverebbe il ledger, così rilanciare il periodo non tiene due volte lo stesso movimento e uno scartato non viene richiesto (`discarded` nell'esito).
- Un endpoint dedicato, `POST /api/sync/period` (`{account_id, from, to, preview}`), invece del corpo opzionale su `POST /api/sync`: la risposta ha un'altra forma. `GET /api/sync/held` e `POST /api/sync/held/{id}/write|discard` per la decisione. `API_VERSION` 23; la riga del conto ha `connected`, che dice al pannello dove offrire l'azione.
- `record` e l'anteprima condividono una sola decisione (`Ledger._plan`), così l'anteprima non promette ciò che la scrittura non fa.
- Rifiuto dell'intervallo = HTTP 400/422 sulla finestra: dimezza fino a 1 giorno, la larghezza ridotta vale per il resto del periodo; un giorno rifiutato fa fallire la finestra com'era stata chiesta e la successiva riparte larga. 401/403 interrompono il periodo (consenso scaduto), ogni altro errore fa fallire solo la sua finestra.
- `max_window_days` stringe anche le finestre della sync normale; il resto della sync normale è invariato e non tiene doppioni.
- Il periodo non scrive saldi dichiarati: la verifica della sezione 5.4 si legge sull'ultimo saldo già registrato.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Un conto collegato si sincronizza su un periodo `dal`/`al` scelto, anche nel passato, dalla CLI (`amonhen sync --account --from --to [--preview]`), dall'API (`POST /api/sync/period`) e dal pannello del conto in Conti. Il provider restituisce una `FetchedWindow` per finestra, con la larghezza per conto (`max_window_days`) che si dimezza quando la banca rifiuta l'intervallo; ogni finestra riuscita è un lotto suo, quindi un errore non butta via le altre, e l'esito dice per finestra quanti movimenti sono arrivati o perché no. Tutto passa da `Ledger.record`: rilancio idempotente, tombstone, promozione PDNG→BOOK come nella sync normale; poi giroconti da `from`, destinazioni dichiarate, validazione, regole e stato della sezione 5.4 del conto. Cursore incrementale e `start_sync_date` invariati. Un movimento con stesso conto, giorno e importo di una riga dell'import ma descrizione diversa non viene scritto: aspetta in `held_transactions` che una persona lo scriva o lo scarti. Verificato con test (provider, servizio, API, CLI) e percorrendo il pannello in un Chromium headless contro lo stub di Enable Banking a 390 e 1484 px.
<!-- SECTION:FINAL_SUMMARY:END -->
