---
id: TASK-6
title: Dashboard con i grafici e rimozione della rata del mutuo
status: Done
assignee: []
created_date: '2026-09-12 15:55'
updated_date: '2026-09-12 15:56'
labels: []
dependencies: []
type: feature
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sostituisce la scheda Sintesi con un dashboard come schermata iniziale: card delle metriche in testa, poi tre grafici (spese per categoria del mese, entrate/uscite per mese, patrimonio osservato), quindi budget, anomalie, flag e conti. Rimuove del tutto la rata del mutuo (riga, calcolo, valore in settings).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 recharts fra le dipendenze di web, `npm --prefix web run build` esce 0
- [x] #2 la app si apre sul Dashboard; la coda resta una scheda a sé; nessuna scheda "Sintesi"
- [x] #3 tre grafici alimentati dall'API, con stato vuoto quando non ci sono dati
- [x] #4 saldi per conto `(account, as_of, amount, source)` scritti dal sync da Enable Banking e da `anchor`; serie del patrimonio dalle sole osservazioni
- [x] #5 card della vecchia Sintesi conservate in testa, tranne il mutuo, che esce anche da calcolo e settings
- [x] #6 somme degli endpoint di aggregazione asserite su un ledger seminato, nessuna somma nel frontend
- [x] #7 `uv run pytest -q` verde
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Backend:
- `metrics.py`: `spend_by_category`, `monthly_flows`, `net_worth_series`, `latest_balances` (più dataclass). La finestra di `monthly_flows` è ritagliata ai mesi coperti dal ledger, come le finestre delle metriche, e il mese in corso è marcato `partial`.
- `metrics.py`: `compute_metrics` perde il parametro e il campo `mortgage_monthly`; il denominatore del runway è il solo burn atteso.
- `api.py`: `GET /api/spending`, `GET /api/flows`, `GET /api/networth`; rimossi `GET/POST /api/settings` e il modello `SettingRequest`.
- `sync.py`: `_record_balances` scrive a ogni sync il saldo riportato dalla banca (`eb:<tipo>`, best-effort: un errore sui saldi non perde i movimenti). Lo stesso saldo è ciò contro cui la asserzione §5.4 confronta il ledger.
- `db.py`: rimossa la tabella morta `net_worth_snapshots`; `_drop_obsolete` cancella la chiave `mortgage_monthly` lasciata dai database esistenti.
- `cli.py`: via `metrics --mortgage` e la riga in output; `sync` riporta `balances=N`.

Frontend:
- `web/src/components/Charts.tsx`: donut delle categorie con totale al centro e legenda (nome, quota, importo), barre raggruppate entrate/uscite, area del patrimonio.
- `web/src/screens/Sintesi.tsx` → `screens/Dashboard.tsx`: card, i tre pannelli, budget, anomalie, categorie, conti; rimossi il campo e il salvataggio della rata.
- Tab bar: Dashboard (nuova scheda iniziale, prima posizione), Da confermare, Movimenti.

Verifica: 201 test; sync reale che ha scritto 3 righe `eb:ITAV`; endpoint interrogati dal vivo (spending 1836,72 € su 4 categorie; flows da aprile a settembre; due punti reali di patrimonio); ispezione in browser a 390 px dei tre pannelli (render corretto, nessun overflow, nessuno scroll orizzontale) e di un ledger vuoto (zero grafici, tre stati vuoti).

Nota: questa fase supera la parte di TASK-4 che prevedeva la rata del mutuo nel runway; il criterio #4 di TASK-4 resta come traccia storica.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La home è un dashboard: card delle metriche §5.6, poi tre grafici recharts (spese per categoria del mese con totale al centro e legenda, entrate/uscite per mese con il mese in corso attenuato, patrimonio sui saldi osservati), quindi budget, anomalie, flag e conti. La coda resta una scheda a sé e la scheda Sintesi non esiste più. La rata del mutuo è uscita da riga, calcolo, settings e CLI: il denominatore del runway è il solo burn atteso. Il sync ora scrive a ogni giro il saldo che la banca riporta (origine eb:tipo), quindi la serie del patrimonio parte da osservazioni reali e la stessa riga alimenta l'asserzione §5.4; la tabella morta net_worth_snapshots è stata rimossa e la chiave mortgage_monthly residua cancellata all'apertura. Verifica: 201 test; sync reale con 3 righe eb:ITAV; endpoint dal vivo (spese 1836,72 € su 4 categorie, flussi da aprile a settembre, due punti reali di patrimonio); ispezione in browser a 390 px dei tre pannelli e di un ledger vuoto (zero grafici, tre stati vuoti corretti).
<!-- SECTION:FINAL_SUMMARY:END -->
