---
id: TASK-96
title: Le fonti vere del portafoglio
status: To Do
assignee: []
created_date: '2026-11-16T20:18:00Z'
labels: []
dependencies:
  - TASK-95
references:
  - desiderata-monitoring-finanziario.md
  - docs/investments.md
  - https://github.com/LucaPaganin/payslip-parser
type: feature
ordinal: 96000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Quarta fetta della fase 12 (sezione 5.16): sostituisce le sorgenti finte di TASK-95 con quelle vere. I documenti li legge il package payslip-parser (repository privato, seconda fetta, con la sua specifica e il suo backlog): qui si integra come dipendenza, e nessuna fixture derivata da un documento reale entra in questo repository, che è pubblico. Prima di cominciare vanno verificate due cose sulla CLI di Scalable: se restituisce lo storico delle transazioni o solo le posizioni, e se il login regge su un NAS senza interazione.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AmonHen legge da Paperless i documenti di un tipo modificati dopo l'ultima lettura, scarica l'originale e non la copia d'archivio, e non rilegge un documento già letto
- [ ] #2 L'esito torna su Paperless come tag amonhen:importato o amonhen:errore, con le cifre chiave come custom field
- [ ] #3 La CLI di Scalable gira in un container a parte dietro un wrapper che espone solo comandi di lettura; dal processo di AmonHen non si raggiunge nulla che prepari un ordine
- [ ] #4 Il valore quota del fondo si legge una volta al mese dalla pagina pubblica della sua classe (Azionario Globale C); se la pagina non si legge l'app chiede il valore a mano invece di saltare il mese
- [ ] #5 Il calendario delle cedole nette del BTP Valore si genera da ISIN, nominale e data d'acquisto e si riconcilia con gli accrediti Fineco
- [ ] #6 Lo storico dei prezzi di fine mese dell'ETF prima del primo sync si carica una volta sola
<!-- AC:END -->
