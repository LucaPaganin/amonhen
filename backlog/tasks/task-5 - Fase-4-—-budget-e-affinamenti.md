---
id: TASK-5
title: Fase 4 — budget e affinamenti
status: Done
assignee:
  - '@luca'
created_date: '2026-09-12 12:07'
updated_date: '2026-09-12 14:16'
labels:
  - phase-4
dependencies:
  - TASK-4
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Budget mensili per categoria, anomaly detection deterministica e spiegabile (z-score robusto su MAD o soglia sul p95 storico di categoria, mai LLM), classificatore statistico leggero (logistica su char n-gram) sulla coda non coperta dalle regole, LLM solo per la normalizzazione dei merchant mai visti, in batch asincrono, output marcato 'da confermare'. Vedi §5.5, §5.7, §8, §9 Fase 4.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Budget mensili per categoria modificabili dalla UI
- [x] #2 Anomalie rilevate con z-score robusto su MAD (o p95 storico di categoria) e spiegabili con una frase, senza LLM
- [x] #3 Classificatore statistico char n-gram attivo sulla coda non coperta dalle regole, con copertura misurata
- [x] #4 LLM usato solo per merchant mai visti, in batch asincrono, fuori dal percorso sincrono del sync, con output 'da confermare'
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Schema: tabella budgets (budget mensile per categoria) e merchant_suggestions (proposte per merchant con origine e decisione), più API ledger.
2. Anomalie deterministiche: z-score robusto su MAD per categoria, fallback su soglia p95 quando la MAD è zero, ognuna spiegabile con una frase; mai LLM.
3. Classificatore statistico char n-gram (logistica multinomiale deterministica) sulla coda non coperta dalle regole, che propone merchant→categoria.
4. Suggeritore LLM per i merchant mai visti: batch asincrono su API esterna, fuori dal sync, output sempre marcato "da confermare" e mai applicato da solo.
5. API: budget con speso/residuo, anomalie, proposte con accetta/rifiuta (accettare crea la regola esatta), trigger del classificatore e dell'LLM.
6. UI: budget e anomalie nella Sintesi, blocco "proposte da confermare" nella coda.
7. Verifica: test + browser sul ledger reale.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementazione (commit cc8df11):
- Budget: tabella `budgets` (un importo mensile per categoria) con speso/residuo del mese; CLI `budget`/`budgets`, `GET/PUT /api/budgets`, sezione Budget nella Sintesi con stato "sforato".
- Anomalie (§5.7): `finance_monitor/anomalies.py`, z-score robusto su MAD per categoria con fallback sulla soglia p95 quando la MAD è zero, deterministico e spiegato con una frase che nomina importo, merchant, categoria, mediana e soglia. La finestra di revisione di 31 giorni è esclusa dalla storia su cui viene calcolata, altrimenti il ramo p95 non potrebbe mai scattare sul caso per cui esiste.
- Classificatore (§5.5 passo 3): `finance_monitor/classifier.py`, logistica multinomiale su char 3-gram hashati, nessuna dipendenza e nessun random. Sul ledger reale mappa tutti i merchant Aspit* su Trasporti e il fruttivendolo su Spesa: generalizzazione che le regole esatte non possono esprimere.
- LLM (§5.5 passo 4, §8): `finance_monitor/suggestions.py`, endpoint compatibile OpenAI, spento se `MONITOR_LLM_URL`/`MONITOR_LLM_MODEL` non sono configurati, usato solo per etichette discrete su merchant mai visti, mai nel percorso di sync. Le sue risposte finiscono come proposte.
- Nulla di ciò che producono classificatore e modello viene applicato da solo: una proposta diventa regola esatta solo quando un umano la accetta dalla coda (l'accettazione crea la regola e categorizza i movimenti corrispondenti).
- Verifica live sul ledger reale: budget salvato/rimosso/sforato, 19 anomalie spiegate, proposta accettata dal browser (regole 8→9, coda 333→330, proposte 20→19), proposta rifiutata, classificatore lanciato dalla UI, e il pulsante del modello che mostra il messaggio 503 testuale quando nessun LLM è configurato.
- `uv run pytest`: 168 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fase 4 completata: budget mensili per categoria (CLI e UI, con stato sforato), anomaly detection deterministica e spiegabile (z-score robusto su MAD per categoria, fallback p95), classificatore statistico char n-gram che propone merchant→categoria, e suggeritore LLM opzionale per i merchant mai visti. Classificatore e LLM scrivono solo proposte: diventano regole solo con un'accettazione umana dalla UI, e l'LLM resta spento senza configurazione (la UI mostra il motivo). Verifica: 168 test e prova in browser sul ledger reale (budget, anomalie, proposta accettata e rifiutata, classificatore dalla UI, messaggio 503 del modello).
<!-- SECTION:FINAL_SUMMARY:END -->
