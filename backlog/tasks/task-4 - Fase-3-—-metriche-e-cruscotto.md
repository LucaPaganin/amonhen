---
id: TASK-4
title: Fase 3 — metriche e cruscotto
status: Done
assignee: []
created_date: '2026-09-12 12:07'
updated_date: '2026-09-12 14:04'
labels:
  - phase-3
dependencies:
  - TASK-3
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Calcolo delle sole metriche elencate in §5.6: burn ricorrente (mediana mobile 6 mesi delle spese non episodiche), accantonamento episodico (one-off 24 mesi / 24), burn atteso, runway stressato (liquidità / (burn atteso + rata mutuo)), quota incomprimibile vs discrezionale, flusso di risparmio (verso conti di investimento; PAC/contributi/TFR non sono spese). Schermata di sintesi mensile ed editing degli split. Le metriche su storico troppo corto vanno riportate come parziali, non calcolate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Burn ricorrente = mediana mobile a 6 mesi delle spese non episodiche
- [x] #2 Accantonamento episodico = somma one-off ultimi 24 mesi / 24
- [x] #3 Burn atteso = burn ricorrente + accantonamento episodico
- [x] #4 Runway stressato = liquidità / (burn atteso + rata mutuo)
- [x] #5 Quota incomprimibile vs discrezionale
- [x] #6 Flusso di risparmio verso conti di investimento, con PAC/contributi/TFR esclusi dalle spese
- [x] #7 Schermata di sintesi mensile e editing degli split nella UI
- [x] #8 Metriche con storico insufficiente riportate come parziali
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementazione (commit 6ab633a):
- `finance_monitor/metrics.py`: burn ricorrente (mediana dei mesi completi nella finestra, default 6), accantonamento episodico (somma episodica su 24 mesi / 24), burn atteso, runway stressato (liquidità / (burn atteso + rata mutuo)), incomprimibile/discrezionale, flusso di risparmio. Finestre ritagliate sui mesi realmente coperti e segnalate come parziali (`partial`, `episodic_partial`) invece di riempire mesi inesistenti con zeri.
- Difetto trovato eseguendo le metriche sul ledger reale: sommando i postings di categoria senza filtrare il segno del movimento, lo stipendio in entrata (posting di categoria negativo) si compensava con la spesa e il burn risultava −35,41. Corretto con il filtro sui movimenti in uscita, come `spend_between`; ora il burn reale è 4764,50. Regressione coperta da test.
- Flag per categoria (`episodic`, `essential`), flag per conto reale (`investment`), rata mutuo in `settings`; migrazione delle colonne sui database esistenti. Split: `Ledger.set_splits` con postings a somma zero e `PUT /api/transactions/{id}/splits`.
- UI: terza scheda Sintesi (una card per metrica, avviso di storico parziale, campo rata mutuo), toggle per categorie e conti, editor degli split nella scheda categoria, chip "N categorie".
- Correzioni dalla review di fase 2: il badge della coda ora si ricarica dal server dopo un rifiuto o una categorizzazione da Movimenti (prima si disallineava); `Ledger.category` rifiuta un nome già usato da un conto reale/virtuale o vuoto (prima 201 fasullo e poi 500, con `/api/categorize` che si interrompeva a metà); link e clearing di un giroconto in un'unica transazione (prima un fallimento intermedio lasciava un link con le gambe che contavano come spesa, e la coppia non veniva più riproposta); le regole vengono applicate anche dal sync schedulato dentro il server; l'API ascolta su localhost per default.
- Verifica in browser (360 px) sul ledger reale: metriche con banner parziale, salvataggio rata mutuo con runway ricalcolato, toggle categoria/conto, split sbilanciato rifiutato con il messaggio del backend e split bilanciato salvato, badge della coda coerente su conferma, rifiuto e categorizzazione da Movimenti.
- `uv run pytest`: 149 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fase 3 completata: le metriche di §5.6 (burn ricorrente a mediana mobile, accantonamento episodico su 24 mesi, burn atteso, runway stressato con rata mutuo, quota incomprimibile vs discrezionale, flusso di risparmio) calcolate dal ledger e mostrate in una nuova schermata Sintesi, con storico insufficiente segnalato come parziale. Aggiunti flag episodic/essential per categoria e investment per conto, rata mutuo configurabile, ed editing degli split. Verifica: 149 test, più prova in browser sul ledger reale (metriche, toggle, rata, split rifiutato e salvato). Corretti anche cinque difetti trovati dalla review indipendente di fase 2.
<!-- SECTION:FINAL_SUMMARY:END -->
