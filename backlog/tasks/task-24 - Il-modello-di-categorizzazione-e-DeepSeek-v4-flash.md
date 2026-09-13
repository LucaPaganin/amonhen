---
id: TASK-24
title: Il modello di categorizzazione e' DeepSeek v4 flash
status: Done
assignee: []
created_date: '2026-09-13 12:59'
updated_date: '2026-09-13 16:39'
labels: []
dependencies: []
ordinal: 23500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il percorso LLM esisteva (proposte discrete per i merchant che nessuna regola copre) ma non era configurato, e la sua richiesta non soddisfaceva il requisito di DeepSeek per la modalita' JSON: la parola json deve comparire nel prompt.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 MONITOR_LLM_URL (endpoint completo), MONITOR_LLM_MODEL=deepseek-v4-flash e MONITOR_LLM_API_KEY documentati in .env.example e presenti in .env
- [x] #2 Il percorso locale ha le variabili senza mettere segreti nel repo (.vscode/launch.json prende la chiave dall'ambiente)
- [x] #3 Il prompt contiene la parola json, richiesta da DeepSeek per response_format json_object
- [x] #4 Verificato contro un endpoint compatibile: percorso, bearer, model, temperature 0, response_format, ruoli e contenuto utente; una categoria inventata viene scartata e il movimento resta Uncategorized
- [x] #5 Dalla richiesta non escono date, importi, IBAN ne' payload grezzo
- [x] #6 Con la chiave reale manca solo la prova dal vivo, e il comando e' documentato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fatti veri su DeepSeek: il modello si chiama deepseek-v4-flash, l'endpoint e' https://api.deepseek.com/chat/completions, e la modalita' JSON richiede che la parola json compaia nel prompt e che il formato desiderato sia esemplificato. Il prompt non lo faceva, quindi e' stato riscritto.

MONITOR_LLM_URL e' l'endpoint intero: il client fa requests.post sulla URL data senza aggiungere percorsi, quindi la base URL del fornitore non basta. Verificato con uno stub locale compatibile: percorso, bearer, model, temperature 0, response_format json_object, ruoli system e user; dalla richiesta non escono date, importi, IBAN ne' payload grezzo. Una categoria inventata viene scartata e il movimento resta Uncategorized.

Resta solo la chiave, da creare su platform.deepseek.com/api_keys e incollare in .env (gitignorato). Poi il comando e' uv run amonhen llm-suggest, oppure il pulsante Chiedi al modello nella coda. Nell'ambiente non c'era nessuna chiave API, quindi la chiamata vera non e' stata provata.

Il difetto vero era a monte della chiave: .env lo leggeva solo docker compose, quindi un uv run partiva senza e la sezione restava spenta senza dire perché. Ora settings carica il file prima di leggere qualunque variabile, con quella già nell'ambiente che vince, e il server avviato senza nessuna variabile a mano risulta configurato.

La prima chiamata vera ha anche trovato un falso positivo della regola sulle cifre: il modello scrive due cifre del pacchetto come confronto (entrate/uscite separate da una barra) e la regola leggeva tutto il token come una cifra sola, rifiutando una lettura che non violava niente. Ora un token si legge come tutte le cifre che contiene, e un separatore al bordo è punteggiatura della frase. Due test tengono le due metà: il confronto passa, la cifra inventata no.

Verificato dal vivo il 13 settembre 2026, su una copia della contabilità vera: il modello configurato risponde con una lettura in italiano che cita le cifre del pacchetto, le proposte di categoria nominano merchant che erano nella richiesta e categorie che esistono, la seconda domanda identica arriva dalla cache senza raggiungere il modello, e la chiamata è contata sul tetto giornaliero. Le prime letture ripetevano i nomi dei campi (burn_atteso, runway_mesi): il pacchetto ora usa parole, e la lettura dice il burn atteso e il runway.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il modello di categorizzazione e DeepSeek sono configurati e ora funzionano davvero: .env viene letto all'avvio sia da uv run sia da docker compose, con la variabile dell'ambiente che vince, quindi la chiave scritta nel file basta. La prima chiamata vera ha fatto il suo lavoro di verifica: ha confermato che il percorso regge end to end e ha trovato due difetti, la regola sulle cifre troppo stretta sui confronti e i nomi dei campi che finivano nella prosa. Restano il tetto di venti chiamate al giorno, il conteggio visibile nella sezione, le proposte che aspettano un gesto e la registrazione di domanda, risposta e impronta dei dati.
<!-- SECTION:FINAL_SUMMARY:END -->
