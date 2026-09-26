---
id: TASK-60
title: Il desktop ha un rail laterale al posto della barra in basso
status: To Do
assignee: []
created_date: '2026-09-26 11:32'
updated_date: '2026-09-26 11:32'
labels: []
dependencies:
  - TASK-59
references:
  - >-
    C:\Users\lucap\.omp\agent\sessions\-git_repos-amonhen\2026-09-24T18-25-56-868Z_01a0d4aa-c684-7715-8842-e15e80e3b466\local\desktop-shell-plan.md
type: feature
ordinal: 59500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sopra i 1024px la navigazione resta una pillola flottante in fondo alla finestra e due destinazioni (Assistente e Configurazione) vivono solo nel drawer. Il rail e il terzo consumatore della stessa lista di sezioni (oggi SectionNav serve tabbar e drawer) e nomina tutte le destinazioni per esteso, con il badge di quello che aspetta in coda. Dipende dalla fetta del contenitore: il rail cambia l asse su cui il contenuto si allinea.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Sopra i 1024px il rail e fisso a sinistra, largo 232px, con icona, nome per esteso e badge della coda, e la sezione corrente marcata con aria-current=page
- [ ] #2 Sopra i 1024px la barra in basso e il pulsante Sezioni non sono renderizzati, e .app__main non riserva piu spazio in fondo per la tabbar
- [ ] #3 Il contenuto non finisce sotto il rail a nessuna larghezza sopra i 1024 (misurato) e l ordine di tabulazione segue il rail poi la schermata
- [ ] #4 A 390px tabbar e drawer sono quelli di prima, identici (confronto di screenshot)
- [ ] #5 La lista delle sezioni resta una sola: rail, tabbar e drawer la leggono da Navigation.tsx
<!-- AC:END -->
