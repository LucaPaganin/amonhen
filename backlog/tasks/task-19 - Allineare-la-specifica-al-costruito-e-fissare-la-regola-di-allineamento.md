---
id: TASK-19
title: Allineare la specifica al costruito e fissare la regola di allineamento
status: Done
assignee: []
created_date: '2026-09-13 10:31'
updated_date: '2026-09-13 10:33'
labels: []
dependencies: []
ordinal: 18500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La specifica e' ferma alla 0.1 mentre il sistema ha consegnato le fasi 0-4 piu' il cruscotto, le regole sul testo della descrizione e la gestione dei giroconti. Contraddizioni da correggere: §5.4 dice che l'invariante non va mostrata in dashboard (ora e' visibile per figura), §5.6 include la rata del mutuo nel runway (rimossa di proposito) e dichiara decorative le torte per categoria (il cruscotto le mostra), §6 elenca net_worth_snapshots che non esiste. Da aggiungere: i giroconti verso conti propri non collegati, l'abbinamento manuale, il nome del prodotto e i confini rimasti. E la regola di processo: leggere la specifica prima di implementare ed editarla nello stesso cambiamento in cui una decisione la cambia.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La specifica e' alla 0.2, con il changelog di cosa e' cambiato e la regola di manutenzione
- [x] #2 Nessuna affermazione contraddice il codice: §5.4 visibile per figura, §5.6 senza rata del mutuo e con le serie che il cruscotto mostra, §6 con lo schema reale, §5.8 patrimonio osservato
- [x] #3 I giroconti verso conti propri non collegati, l'abbinamento manuale e il rifiuto del link sono nella specifica (§3, §5.2, §5.3)
- [x] #4 §9 dichiara cosa e' fatto e cosa resta aperto, coerente con il backlog
- [x] #5 CLAUDE.md e AGENTS.md impongono di leggere la specifica prima di implementare e di aggiornarla nello stesso cambiamento
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Applicate 19 sostituzioni, ognuna verificata con un assert di occorrenza singola, cosi' nessuna e' passata in silenzio. Il diff e' di 48 inserimenti e 21 rimozioni e ogni riga rimossa e' una che il cambiamento voleva cambiare; i fini di riga CRLF del file sono stati preservati. Controllo dei residui: net_worth_snapshots non compare piu' nella specifica, 'torte per categoria' nemmeno, la rata del mutuo solo nella riga di changelog e nella nuova negazione. Il commento di db.py che cita la tabella morta resta, ed e' corretto: _drop_obsolete la cancella ancora.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La specifica e' alla 0.2 e descrive il sistema che esiste. Corrette le tre contraddizioni: §5.4 non dice piu' che l'invariante va nascosta (e' visibile per conto e per figura), §5.6 non ha piu' la rata del mutuo nel denominatore del runway ne' dichiara decorative le torte che il cruscotto mostra, §6 elenca le nove tabelle reali al posto di net_worth_snapshots. Aggiunto quello che il codice ha imparato: la seconda gamba di un giroconto va su un conto virtuale, una gamba verso un conto proprio non collegato si dichiara (per etichetta o per singolo movimento), due gambe si abbinano a mano con gli stessi guardiani del matcher, e annullare una coppia rifiuta il link invece di cancellarlo. §9 segna le fasi 0-4 come fatte e indica il lavoro aperto, che sta nel backlog. La regola di processo e' scritta dove gli agenti la leggono: specifica, CLAUDE.md e AGENTS.md dicono di leggere le sezioni toccate prima di implementare e di aggiornare la specifica nello stesso cambiamento, alzando la versione.
<!-- SECTION:FINAL_SUMMARY:END -->
