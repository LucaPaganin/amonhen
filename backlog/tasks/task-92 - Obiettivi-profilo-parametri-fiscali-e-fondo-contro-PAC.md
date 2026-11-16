---
id: TASK-92
title: Obiettivi, profilo, parametri fiscali e fondo contro PAC
status: Done
assignee:
  - '@claude'
created_date: 2026-11-03 12:00
updated_date: '2026-11-16T21:21:00Z'
labels: []
dependencies: []
type: feature
ordinal: 92000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La prima fetta della fase 12 (sezione 5.16): gli obiettivi, i fatti del profilo che il ledger non vede, i parametri fiscali per anno con la fonte, e il confronto fra un euro in più nel fondo pensione e lo stesso euro in un PAC.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un obiettivo ha nome, cifra in euro di oggi, data, liquidità richiesta e la data da cui vale
- [x] #2 Il profilo tiene la base del versamento separata dal lordo, ogni fatto con la data da cui vale
- [x] #3 I parametri fiscali sono righe per anno con la fonte; un anno mancante si dice, e ogni cifra scrive l'anno usato
- [x] #4 Il confronto mette in fila deduzione, contributo del datore, spazio sotto il tetto, tassazione all'uscita e vincolo di liquidità, per due ripartizioni una accanto all'altra
- [x] #5 Il margine si legge dal ledger sui 12 mesi completi, con quello dei mesi ordinari accanto
- [x] #6 Le schede della Guida per obiettivo, base del versamento e tetto di deducibilità
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Forma (docs/architettura.md): core puro, persistenza come sotto-dominio del ledger senza repository, un caso d'uso in services/, nessuna porta nuova (nessun sistema esterno).

1. Schema — tre tabelle nuove in db.SCHEMA (CREATE IF NOT EXISTS, nessuna migrazione):
   - goals(id, series, name, amount, target_date, liquidity CHECK IN ('liquida','alla_data','vincolabile'), valid_from, valid_to?) — una riga per versione; `series` lega le versioni; cambiare a una data chiude la riga (valid_to) e ne apre una nuova, come un default di budget; si legge "com'era al giorno D".
   - profile_facts(key, value, valid_from) PK(key, valid_from), chiavi chiuse: gross_monthly, months_paid, contribution_base (annua, separata dal lordo), own_rate, employer_rate, tfr_destination (fondo|azienda), birth_date, fund_joined (adesione, per l'aliquota d'uscita).
   - tax_parameters(year, key, value, source NOT NULL) PK(year, key), chiavi chiuse: irpef_brackets (JSON), regional_surtax, municipal_surtax, employee_social_rate, deduction_cap (5.300 dal 2026, datore dentro, TFR fuori), exit_rate_base (15), exit_rate_step (0,30), exit_rate_floor (9), exit_rate_free_years (15), fund_return_tax, etf_gain_tax (26), stamp_duty. Nessun valore scritto nel codice.
2. Persistenza: amonhen/ledger/planning.py, PlanningMixin composto in Ledger (goals_at, save_goal, end_goal, profile_at, set_profile_fact, tax_years, tax_year, set_tax_parameter, delete_tax_parameter).
3. Core puro: amonhen/core/ (nuovo) planning.py — IRPEF + addizionali su scaglioni, aliquota d'uscita per anni di adesione, una ripartizione (F al fondo, P al PAC, all'anno) → contributo del datore (solo se F ≥ own_rate·base), deduzione = min(F, tetto − datore), spazio sotto il tetto (negativo = oltre), risparmio d'imposta = imposta(R) − imposta(R − deduzione) con R = lordo·mensilità·(1 − contributi), crescita anno per anno al rendimento scritto, rendimenti del fondo tassati ogni anno, uscita solo sulla parte dedotta + datore, ETF con bollo annuo e 26% sul guadagno; vincolo di liquidità dall'obiettivo. Margine: funzione pura da 12 margini mensili → somma annua e mediana (mesi ordinari).
4. Caso d'uso: amonhen/services/planning.py — plan_overview(ledger, today) (obiettivi, profilo, parametri con anno usato e anno mancante, margine via metrics.period_summary sui 12 mesi completi) e compare(ledger, today, goal_id, allocations[2], return_rate). Anno fiscale usato = ultimo anno completo ≤ anno in corso; l'anno in corso mancante o incompleto si dice con le chiavi che mancano; nessun anno completo → il confronto non si calcola e lo dice.
5. API: amonhen/api/routes/plan.py — GET /api/plan, PUT|DELETE goals, PUT profile, PUT|DELETE tax-parameters, POST /api/plan/compare. API_VERSION 43 e REQUIRED_API_VERSION insieme.
6. PWA: sezione **Piano** sotto Gestione (web/src/screens/Plan.tsx): Obiettivi, Profilo, Parametri fiscali per anno con la fonte, Margine, Confronto con due ripartizioni una accanto all'altra; nessuna aritmetica nel client. Schede della Guida: obiettivo, base del versamento, tetto di deducibilità, fondo contro PAC.
7. Test: core (scaglioni, tetto, datore condizionato, aliquota d'uscita, anno mancante), ledger (versioni a una data), servizio (margine su 12 mesi), API. Suite da un checkout pulito (git archive).
8. Verifica UI in Chromium su una copia di un ledger sintetico (nel container non c'è il ledger vero), con AMONHEN_CONFIG_FILE su una copia; screenshot letti.
9. Spec 1.47 (sezioni 5.16, 6, 9), docs/investments.md, CLAUDE.md (file map, schema: 18 tabelle), docs/frontend.md se serve.

Tagli (ponytail, approvati): profilo senza data di nascita e destinazione del TFR (nessuna cifra di questa fetta le usa: arrivano con le proiezioni); tre schede della Guida, quelle del criterio 6; nessun comando CLI. Decisioni approvate: rendimento unico scritto nel confronto, mesi ordinari = mediana dei 12 margini, datore solo se il proprio raggiunge la percentuale, risparmio d'imposta nel PAC dello stesso anno, liquidità a tre valori, base annua, ripartizioni non salvate, nessuna copia dall'anno prima.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verifica: 652 test passati da un checkout pulito (git archive, senza accounts.json e .env), 15 nuovi in tests/test_planning.py. UI percorsa in Chromium a 1280 e 390 su un ledger sintetico (nel container non c'è il ledger vero) servito con --db e AMONHEN_CONFIG_FILE su copie: due obiettivi, sei fatti del profilo, dodici parametri 2025 scritti a mano con la fonte; il 2026 mancante è detto sia nei parametri sia nel confronto; margine 13.800 € con mese ordinario 750 € (12×750 + due mensilità); risparmio d'imposta 1.690,26 € = 4.564,57 × 37,03%; aliquota d'uscita al minimo 9% con 36 anni di adesione; per l'obiettivo Casa (alla data) il fondo resta vincolato; nessun errore in console, nessuno scorrimento orizzontale a 390. Corretti durante la verifica: date e percentuali all'italiana nel profilo, bordo del fieldset.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La prima fetta della fase 12 (sezione 5.16). Tre tabelle nuove (goals versionati per serie, profile_facts con la base del versamento separata dal lordo, tax_parameters per anno con fonte obbligatoria); il core puro amonhen/core/planning.py (IRPEF sugli scaglioni, tetto con il datore dentro e il TFR fuori, datore solo sopra la percentuale propria, aliquota d'uscita 15→9%, ETF con bollo e 26% sul guadagno); il caso d'uso services/planning.py (margine dei 12 mesi completi e mediana del mese ordinario, confronto di due ripartizioni con l'anno fiscale usato e quello mancante); /api/plan; la sezione Piano sotto Gestione; tre schede della Guida. API_VERSION e REQUIRED_API_VERSION a 43. Specifica 1.47, docs/investments.md e CLAUDE.md allineati. Rischi e seguiti: il rendimento è uno solo finché TASK-94 non porta gli scenari; le detrazioni IRPEF non entrano nel risparmio d'imposta; la UI è verificata su un ledger sintetico, non su una copia di quello vero.
<!-- SECTION:FINAL_SUMMARY:END -->
