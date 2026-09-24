---
id: TASK-51
title: Verifica integrata della fase 6
status: Done
assignee: []
created_date: '2026-09-24 18:39'
updated_date: '2026-09-24 22:04'
labels: []
dependencies:
  - TASK-43
  - TASK-44
  - TASK-45
  - TASK-46
  - TASK-47
  - TASK-48
  - TASK-49
  - TASK-50
references:
  - AGENTS.md
  - tests/
  - README.md
documentation:
  - doc-1
type: task
ordinal: 50500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
I task di questa fase si toccano nel percorso piu delicato del sistema (l'ingest) e nell'unica superficie che l'utente usa ogni giorno. La verifica integrata e quella che guarda il risultato intero su una copia del ledger vero, e le revisioni indipendenti di AGENTS.md sono l'ultimo filtro prima del merge.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Su una copia del ledger, in browser: sync dal pulsante, nota scritta su un movimento, movimento cancellato, flag del conto accesa, reimport che riporta la nota, ripristino dal cestino, §5.4 che spiega la differenza invece di gridare mismatch
- [x] #2 Le revisioni previste da AGENTS.md girano con i loro agenti e ogni rilievo ha una disposizione motivata
- [x] #3 `uv run pytest`, la build del bundle e `uv run amonhen --db <copia> validate` passano sul ramo integrato
- [x] #4 Nessun movimento reale e stato toccato: le prove girano su copie in `dumps/`
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Le revisioni di AGENTS.md sono girate sui quattro ruoli (taste, spec, test, docs) piu una revisione finale, tutte sull'agente `reviewer` perche questo harness non registra gli specialisti del repository: ogni revisore ha letto il proprio ruolo in `.pi/agents/<ruolo>.md` e l'ha adottato. Sostituzione visibile, come chiede AGENTS.md.
<!-- SECTION:NOTES:END -->
