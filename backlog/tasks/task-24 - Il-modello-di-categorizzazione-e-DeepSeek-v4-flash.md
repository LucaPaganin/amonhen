---
id: TASK-24
title: Il modello di categorizzazione e' DeepSeek v4 flash
status: In Progress
assignee: []
created_date: '2026-09-13 12:59'
updated_date: '2026-09-13 13:00'
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
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Il modello di categorizzazione e' configurato per DeepSeek v4 flash: la URL all'endpoint intero, il modello, la chiave in .env (gitignorato, da riempire) e la stessa coppia URL piu' modello nel profilo di debug locale, senza segreti nel repo. Il prompt ora contiene la parola json e l'esempio del formato, che DeepSeek pretende per la modalita' JSON. Il percorso e' provato contro uno stub compatibile: forma della richiesta corretta, categoria inventata scartata, movimento non toccato, nessun dato identificativo nella richiesta. Manca la chiamata vera, che ha bisogno della chiave.
<!-- SECTION:FINAL_SUMMARY:END -->
