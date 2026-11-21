---
id: TASK-99
title: payslip-parser legge il contratto e l'estratto titoli di Scalable
status: To Do
assignee: []
created_date: '2026-11-18T07:05:00Z'
labels: []
dependencies: []
type: feature
ordinal: 98000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Lavoro da fare nel repository privato payslip-parser (con la sua specifica, SPEC.md, e il suo backlog): questo task sta qui finché non viene spostato là. Dalla specifica 1.51 di AmonHen l'ETF del PAC si ricostruisce dai documenti del broker invece che dalla sua CLI. Serve un layout per il contratto di esecuzione di Scalable Capital (data, ISIN, quote, prezzo, controvalore, commissioni) e uno per l'estratto titoli periodico (data, ISIN, quote in deposito), con i loro invarianti (quote × prezzo + commissioni = addebito). Prima di tutto va verificato su un PDF vero che il documento abbia uno strato di testo: il package non fa OCR. Nessun PDF né cifra reale entra nel repository pubblico di AmonHen.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un PDF vero del contratto e uno dell'estratto hanno uno strato di testo, verificato con payslip-parser words; se no, il task lo dice e si ferma
- [ ] #2 Il contratto si legge in un modello nuovo del package (data, ISIN, quote, prezzo, controvalore, commissioni) con l'invariante che le cifre tornano
- [ ] #3 L'estratto titoli si legge in un modello (data, ISIN, quote in deposito)
- [ ] #4 La specifica del package dice i nuovi modelli e i layout, e il package ha un tag che AmonHen fissa nella dipendenza
<!-- AC:END -->
