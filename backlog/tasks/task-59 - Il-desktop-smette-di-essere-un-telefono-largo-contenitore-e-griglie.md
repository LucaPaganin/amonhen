---
id: TASK-59
title: 'Il desktop smette di essere un telefono largo: contenitore e griglie'
status: To Do
assignee: []
created_date: '2026-09-26 11:32'
labels: []
dependencies: []
references:
  - >-
    C:\Users\lucap\.omp\agent\sessions\-git_repos-amonhen\2026-09-24T18-25-56-868Z_01a0d4aa-c684-7715-8842-e15e80e3b466\local\desktop-shell-plan.md
type: feature
ordinal: 58500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A 1484x925 la colonna di contenuto e 720px su 1484: 382px vuoti per lato, e nessun elemento attraversa la finestra. Pannelli e carte misurano 692px e stanno uno per riga, la lista dei movimenti e alta 7862px per circa 130 movimenti. La causa e una riga sola di styles.css (.app__main max-width 720px) piu un unico breakpoint sopra i 640px per .metrics. Questa fetta e il pavimento delle altre due: senza un contenitore largo il rail e il pannello laterale non hanno dove stare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Sopra i 1024px la colonna di contenuto misura almeno 1100px, e a 1440 o piu 1240px, con lo stesso tetto per la fascia alta e la barra bassa
- [ ] #2 Sopra i 1024px le metriche sono a 6 colonne, i due grafici del cruscotto affiancati e la coda a 2 colonne (3 a 1440)
- [ ] #3 Sotto i 1024px il render e identico a prima: confronto di screenshot a 390 e a 768 senza differenze
- [ ] #4 Nessun blocco supera il tetto della colonna e nessun paragrafo supera i 75 caratteri per riga (misurato)
- [ ] #5 I grafici recharts hanno altezza non nulla dentro le griglie nuove (misurata, non dedotta)
- [ ] #6 web/README.md e CLAUDE.md dicono la soglia e il tetto; npm --prefix web run build e uv run pytest -q passano
<!-- AC:END -->
