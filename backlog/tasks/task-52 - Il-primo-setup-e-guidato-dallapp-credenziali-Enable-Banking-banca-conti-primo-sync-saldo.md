---
id: TASK-52
title: >-
  Il primo setup e guidato dall'app: credenziali Enable Banking, banca, conti,
  primo sync, saldo
status: Done
assignee:
  - '@main'
created_date: '2026-09-25 19:45'
updated_date: '2026-09-25 20:28'
labels:
  - feature
dependencies: []
ordinal: 51500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il primo avvio e oggi una decina di passi a mano, e nessuno di essi e nel prodotto: creare accounts.json dal template, mettere private.pem, far combaciare tre URL (indirizzo del browser, redirect_url nel file, callback registrata nel dashboard Enable Banking), aprire a mano /connect?bank=FinecoBank&country=IT scrivendo il nome ASPSP esatto a memoria (EnableBankingClient.list_banks esiste e non e chiamato da nessuno), poi editare accounts.json a mano per tenere solo i conti voluti fra quelli che la banca risponde (Fineco ne da quattro) e decidere notes (che per il ledger e l identificativo del conto) e start_sync_date, poi sync, e infine dichiarare un saldo o il conto resta non verificato per la 5.4. Attriti misurati: accounts.json assente fa 500 su /connect e /callback (load_config fuori dal try), redirect_url mancante cade in silenzio sulla porta morta di Flask :3000, /callback risponde JSON grezzo nel browser, e il primo avvio su NAS non puo nemmeno partire perche compose monta i due file singoli e pretende che esistano prima di up. Serve che il primo setup sia una schermata guidata dell app, con il gate al primo avvio e la stessa schermata raggiungibile dopo per aggiungere o rinnovare una banca, e che l app scriva la propria configurazione invece di chiedere di editarla.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Con accounts.json assente GET /api/setup risponde 200 elencando cosa manca, e l app apre il wizard al posto delle sezioni invece di mostrare una shell vuota
- [x] #2 Il passo credenziali scrive application_id, redirect_url e account_holder_name in accounts.json, e la chiave privata incollata su pem_path; la chiave non caricabile e redirect_url non valido sono 422 con il motivo, e subito dopo load_config legge il file
- [x] #3 La chiave privata non torna mai dal server: GET /api/setup dice al massimo che la chiave c e, e nessun log la contiene
- [x] #4 Il passo banca elenca gli ASPSP del paese scelto via list_banks, avvia l autorizzazione, e dopo il login il browser torna nell app invece che su JSON grezzo; l esito added/refreshed per conto si legge nell app
- [x] #5 Il passo conti rinomina un conto, ne fissa la data d inizio, rifiuta un nome gia usato da un altro conto configurato e rimuove una voce indesiderata senza toccare il ledger
- [x] #6 Il passo sync chiama POST /api/sync e mostra l esito per conto
- [x] #7 Il passo saldo dichiara un saldo letto dalla banca, allinea l apertura, e la verifica 5.4 di quel conto passa a verificato
- [x] #8 A sistema configurato il wizard resta raggiungibile per aggiungere o rinnovare una banca
- [x] #9 docker compose monta la cartella di configurazione, cosi un container appena avviato puo far nascere accounts.json; README e CLAUDE.md aggiornati con il nuovo primo avvio e la migrazione della cartella
- [x] #10 La spec e aggiornata nello stesso cambiamento: nuova sezione sul primo setup guidato, fase 7 in roadmap, versione che sale
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. config.py: un solo punto di scrittura del documento — _read_document/_write_document sul JSON grezzo (chiavi sconosciute preservate, come save_account), piu setup_state(path), save_credentials(...) (application_id, pem_path, redirect_url, account_holder_name e la chiave incollata), rename_account(uid, name, start_sync_date), remove_account(uid), write_private_key(path, pem) che valida con load_pem_private_key e scrive 0600. load_config resta strict: il sync continua a fallire forte. 2. api.py (API_VERSION 17 -> 18): GET /api/setup (cosa manca, chiave presente si/no, conti configurati con esito dell'ultima autorizzazione), PUT /api/setup/credentials (422 con motivo: chiave non caricabile, redirect_url senza /callback, application_id vuoto), GET /api/setup/banks?country= (ASPSP via list_banks, oggi mai chiamato), POST /api/setup/connect -> {url} con la stessa start_auth di /connect (estrarre l'avvio in un helper, non duplicarlo), PATCH/DELETE /api/setup/accounts/{uid} (rinomina e data d'inizio, rifiuta un nome gia usato; rimozione che non tocca il ledger). /callback scrive l'esito in settings (last_connect) e risponde 303 su /?setup=1 invece del JSON grezzo; /connect e /callback con config incompleta rispondono 409 con cosa manca invece di 500. 3. docker-compose.yaml: montare la cartella di configurazione (./config:/config) cosi un container appena avviato puo far nascere accounts.json; README con la migrazione. 4. web/: screens/Setup.tsx (cinque passi + riepilogo) sul pattern di Accounts.tsx, useSetup.ts, voci in api.ts e types.ts, gate in App.tsx prima della shell come lo schermo stale-server, ?setup=1 per riaprirlo, voce nel drawer, REQUIRED_API_VERSION 18, stili coi token di :root. 5. Test: estendere test_oauth.py (callback 303 + last_connect, connect senza config 409) e nuovo tests/test_setup_api.py (stato con file assente, credenziali rileggibili da load_config, PEM non valido 422, redirect_url non valido 422, rinomina duplicata 422, rimozione voce, elenco ASPSP). 6. Documentazione: spec con la sezione sul primo setup guidato e la fase 7, versione che sale; README (primo avvio, configurazione, NAS); CLAUDE.md (file map, module map, cose non ovvie); web/README.md. 7. Verifica: uv run pytest, npm --prefix web run build, e un giro reale nel browser sui cinque passi con una copia del ledger.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verifica: uv run pytest = 377 passed; npm --prefix web run build = tsc strict + vite ok; docker compose config risolve il bind su <repo>/config. Giro reale nel browser (390x844) contro uno stub Enable Banking usa-e-getta (dumps/, poi rimosso) e una copia del ledger: accounts.json assente -> il wizard e l'app (nessuna tabbar) -> credenziali con chiave incollata (key_loads true, il file creato accanto) -> lista ASPSP -> autorizzazione -> /callback 303 su /?setup=1 -> tre conti, rinomina e data, Togli -> primo sync con esito per conto -> saldo dichiarato e apertura allineata -> 'verificato' su entrambi i conti; cancellato un movimento e risincronizzato, il passo 5 dice 'd accordo salvo 1 movimento cancellato a mano (109,90 EUR)' come la sezione Conti; drawer -> Configurazione apre al passo Conti; 'Vai alla dashboard' toglie ?setup=1. Stati e testi letti dal DOM, due screenshot passati a un modello di visione. Difetti trovati e chiusi durante la verifica: la guardia sulle credenziali non verificava la chiave (500 su /api/setup/banks invece di 502 con il motivo della banca), due scritture concorrenti sulla config perdevano un aggiornamento (ora serializzate, con test di regressione), ConsentExpiredError non catturato sulle rotte Enable Banking (500 invece di 502). Revisione indipendente (due reviewer) e rilievi applicati: pem_path scelto dal chiamante rimosso dal corpo della richiesta, load_config allineato a setup_state sul default di pem_path, scrittura atomica del documento (temp + os.replace), 404 invece di 422 per un uid sconosciuto, OSError tradotto in 503 invece di 500 sulle scritture, account_holder_name cancellabile (None distinto da vuoto), campo last_connect.accounts non letto rimosso, _upstream_detail (un solo chiamante) inlinato, catch morto di ConsentExpiredError tolto dai POST di autorizzazione, /config/ ancorato in .gitignore (ombrava tests/fixtures/config/), commenti e docstring corretti (sei/sette etichette, nuova scheda, data di inizio vuota, redirect proposto dall'origine). Fuori perimetro per scelta dell'utente: import degli export storici, configurazione dell'assistente, dichiarazioni passthrough.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il primo setup e ora una schermata guidata dell'app (desiderata 5.10, fase 7): gate al primo avvio e sezione Configurazione raggiungibile dopo, cinque passi — credenziali Enable Banking con la chiave privata incollata, istituto scelto fra gli ASPSP che il provider accetta, conti da tenere con nome e data d'inizio, primo sync con l'esito per conto, saldo dichiarato e apertura allineata fino a 'verificato' per la 5.4. L'app scrive la propria configurazione (config.py: save_credentials/rename_account/remove_account, scritture serializzate e atomiche, chiave mai restituita ne registrata), /callback torna nell'app con un 303 invece del JSON, compose monta la cartella ./config perche un container appena avviato possa far nascere accounts.json, e serve parte anche senza configurazione. Verificato con 377 test (test_setup_api.py nuovo, test_oauth.py e test_config.py estesi), build del bundle, docker compose config e un giro reale nel browser contro uno stub Enable Banking e una copia del ledger, dal file assente al conto 'verificato'. La spec sale a 1.4 con la sezione 5.10, la fase 7 e due righe di rischio; README, CLAUDE.md e web/README.md seguono. Restano fuori, concordato: import degli export storici, configurazione dell'assistente, dichiarazioni passthrough.
<!-- SECTION:FINAL_SUMMARY:END -->
