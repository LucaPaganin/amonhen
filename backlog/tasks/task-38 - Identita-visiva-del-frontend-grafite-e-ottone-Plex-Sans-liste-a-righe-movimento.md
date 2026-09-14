---
id: TASK-38
title: >-
  Identita visiva del frontend: grafite e ottone, Plex Sans, liste a righe,
  movimento
status: Done
assignee: []
created_date: '2026-09-14 17:44'
updated_date: '2026-09-14 17:49'
labels: []
dependencies: []
type: feature
ordinal: 37500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il frontend aveva la palette di default di ogni dashboard (navy e smeraldo, card arrotondate, system-ui) e nessuna identita: lo smeraldo era insieme il colore del marchio e quello delle entrate. Questa fetta rifa l'aspetto come un sistema unico - token, tipografia, righe al posto delle card, movimento - senza toccare il contratto dell'API ne la logica del client. Verificata con misure sul DOM e sul contrasto, non a occhio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 I colori dell'interfaccia vengono dai token in web/src/styles.css; la sola lista di colori fuori dai token e la palette categorica dei grafici
- [x] #2 Contrasto misurato: ogni coppia testo/superficie almeno 4.5:1 e ogni bordo di controllo almeno 3:1 (minimi: testo 4.81, bordo 3.01)
- [x] #3 A 390 px il documento e largo quanto il viewport e nessun controllo sta sotto i 44 px
- [x] #4 Una schermata entra a cascata e con prefers-reduced-motion: reduce nessun blocco resta invisibile (opacita 1 entro 120 ms)
- [x] #5 Il font e self-hosted, servito da /assets/ con hash, con la licenza OFL accanto
- [x] #6 Nessun cambiamento di contratto: API_VERSION resta 11 e il client non somma ne filtra
- [x] #7 Le icone PWA sono nella palette nuova: fondo rgb(14,16,19), barre rgb(210,161,63)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Token: fondo grafite #0e1013, inchiostro #ecebe6, ottone #d2a13f per tutto cio che dice l'app (azione piena, attenzione, patrimonio, marcatore della sezione aperta), piu entrate #5ec98d, uscite #e0705c, giroconto #a99bf0, split #74b6d4. Due pesi di linea: --border separa, --border-strong disegna il bordo di cio che si tocca (e infatti solo lui e tenuto al 3:1).
Liste: .txn-list, .card-list, .flag-list, .budget-list, .anomaly-list sono una superficie con separatori sottili; le metriche del cruscotto sono una griglia i cui gap di 1 px sono i separatori. Movimento: .screen > * a cascata di 40 ms; il blocco reduce azzera anche i ritardi, perche una animazione di durata zero che aspetta 200 ms tiene il blocco invisibile per 200 ms.
Difetti trovati misurando e corretti: la maniglietta del foglio aveva altezza 0 (elemento flessibile compresso, ora flex: none); i chip dei filtri erano a 36 px e la promessa del README dice 44, ora sono a 44 con spaziatura 6/10 e la barra filtri resta su una riga.
Il font e IBM Plex Sans variabile 100-700, sottoinsieme latino, 45712 byte, in web/src/assets/ cosi Vite lo emette in /assets/ con hash e il service worker lo mette in cache.

Review indipendente (agente reviewer, modello diverso da chi ha scritto): copertura delle classi completa, invarianti rispettate, nessuna aritmetica aggiunta nel client. Tre rilievi, tutti verificati con misure prima di correggere: la griglia delle metriche faceva righe [3,3,2] a 560 px e la riga incompleta dipingeva il fondo --border come un blocco (ora 2 colonne sotto 640 px e 4 sopra, ogni riga piena a 390/560/700/900); il summary di Come si calcolano era alto 39 px a 390 e 20 px da 700 in su (ora 63 e 44, con il padding e senza perdere il marcatore nativo); --danger e --warning erano rimasti senza lettori e sono stati rimossi.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
L'interfaccia ha ora un'identita sola: grafite freddo, inchiostro caldo e un ottone che porta tutto cio che dice l'app, con i colori del denaro come uniche tinte dei dati. Verificato a 390x844 su una copia del ledger: nessun overflow orizzontale, nessun controllo sotto 44 px, griglia metriche a 2 colonne con gap di 1 px, contrasto misurato (testo 4.81-15.96, bordi 3.01), cascata presente e azzerata sotto prefers-reduced-motion, font e licenza serviti da /assets/, icone ricampionate al pixel. tsc e build puliti; nessuna modifica a route, payload o API_VERSION.
<!-- SECTION:FINAL_SUMMARY:END -->
