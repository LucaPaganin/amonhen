---
id: TASK-64
title: >-
  Nessuna chiamata al modello parte da sola: la domanda arriva pronta, il tocco
  la manda
status: Done
assignee: []
created_date: '2026-09-27 07:21'
updated_date: '2026-09-27 07:30'
labels: []
dependencies: []
ordinal: 63500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi aprire l'assistente da un budget («Regge?», §5.9) chiama il modello configurato mentre la schermata si disegna: una chiamata esterna parte senza che nessuno l'abbia chiesta, senza un tocco e senza che la persona sappia che sta spendendo una delle chiamate contate della giornata. Il resto della sezione è già esplicito (chip, campo, «Chiedi al modello» in coda), quindi il difetto è il solo percorso automatico: un effetto che spara la domanda appena il contesto arriva. La decisione di prodotto è che nessuna chiamata al modello parte se non da un tocco, e che quando parte si vede verso chi e a che titolo. Toccati: web/src/screens/Assistant.tsx (effetto rimosso, la domanda proposta con il suo pulsante), i documenti che descrivono l'ingresso dal budget (desiderata §5.9, README, web/README, CLAUDE.md).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Con l'assistente aperto dal contesto di un budget nessuna richiesta raggiunge l'endpoint LLM finche non si preme il pulsante: verificato contando le richieste ricevute da un endpoint finto
- [x] #2 La domanda che il contesto propone e visibile prima di essere chiesta, con un pulsante che la manda e uno che la lascia cadere
- [x] #3 Mentre la chiamata e in volo la schermata dice a quale modello si sta chiedendo, e la lettura mostra se e una nuova chiamata o una risposta gia avuta
- [x] #4 Nessun punto dell'app chiama /api/assistant/ask o /api/llm-suggest fuori da un gestore di click o submit
- [x] #5 desiderata §5.9 dice che la chiamata parte solo da un tocco, versione e changelog aggiornati; README, web/README e CLAUDE.md dicono lo stesso
- [x] #6 npm --prefix web run build passa
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Togliere l'effetto che chiede al modello all'apertura con un contesto; il contesto diventa un pannello «Domanda pronta» con la domanda implicita e i due pulsanti (Chiedi, Lascia perdere). 2. Nominare il modello nei pulsanti mentre la richiesta e in volo. 3. Chiedere altro (chip o campo) lascia cadere la proposta in attesa. 4. Rinominare onContextUsed in onContextDone (App.tsx, Accounts.tsx). 5. Aggiornare desiderata 1.10 (§5.9, §8, stato §9), README, web/README, CLAUDE.md. 6. Verifica: build del bundle e conteggio delle chiamate nel browser contro un endpoint finto.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementato: web/src/screens/Assistant.tsx (effetto rimosso, pannello Domanda pronta, etichetta Chiedo a <modello>... in volo, askTyped per chip e campo), prop rinominata onContextDone in App.tsx, commento in Accounts.tsx, documenti aggiornati (desiderata 1.10, README, web/README, CLAUDE.md).

Verificato: npm --prefix web run build verde; browser reale 390x844 contro uno stub OpenAI-compatible che registra ogni richiesta: 0 chiamate con il pannello in attesa, 1 dopo il tocco sul pulsante del pannello, 0 al secondo tocco sugli stessi numeri (lettura gia chiesta, contatore invariato), 1 dopo un chip, 0 con AMONHEN_LLM_URL vuoto (pannello che lo dice, pulsante disabilitato). uv run pytest -q verde.

Revisione indipendente (agente reviewer): nessun percorso automatico residuo verso il modello, e quattro frasi di documento corrette nella stessa fetta (README: l'elenco delle vie ora nomina anche llm-suggest e la rivendicazione sul nome del modello e limitata ad Assistente; web/README: il pannello ora nomina davvero il modello). Due difetti trovati e corretti: l'etichetta in volo diceva «Chiedo a il modello...» quando lo stato non era ancora arrivato (ora «Chiedo al modello...»), e una chiamata fallita portava via la domanda composta (useAssistant.ask ora risponde se una lettura e arrivata, e il pannello si chiude solo in quel caso). Lasciata la corrispondenza totale su kind in questionFor/originOf: il tipo e lo specchio dell'API, che accetta anche il contesto movimento.

Revisione dei difetti corretti nel browser: pannello che nomina stub-model, 0 chiamate in attesa, 1 dopo il tocco, lettura «nuova»; con un endpoint irraggiungibile l'errore compare, il pannello resta con la domanda e il pulsante torna attivo.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La domanda che un'altra schermata compone (Regge? su un budget) non raggiunge piu il modello da sola: arriva in un pannello «Domanda pronta» che nomina il modello, con il pulsante che la manda e uno che la lascia cadere, e mentre la richiesta e in volo l'etichetta dice a chi si sta chiedendo. Verificato in un browser reale a 390x844 contro un endpoint finto che registra ogni richiesta: 0 all'apertura, 1 al tocco, 0 al secondo tocco sugli stessi numeri (lettura gia chiesta), 1 da un chip; il caso di errore lascia la domanda al suo posto. Build del bundle e uv run pytest -q verdi; desiderata 1.10 e README, web/README, CLAUDE.md aggiornati.
<!-- SECTION:FINAL_SUMMARY:END -->
