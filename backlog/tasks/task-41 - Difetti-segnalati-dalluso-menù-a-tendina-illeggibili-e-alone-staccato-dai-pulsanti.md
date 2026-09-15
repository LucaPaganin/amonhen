---
id: TASK-41
title: >-
  Difetti segnalati dall'uso: menù a tendina illeggibili e alone staccato dai
  pulsanti
status: Done
assignee: []
created_date: '2026-09-15 22:01'
updated_date: '2026-09-15 22:01'
labels: []
dependencies: []
type: bug
ordinal: 40500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Segnalazione diretta mentre l'app era in uso: i menù a tendina escono chiarissimi con le scritte bianche e non si legge nulla, e le ombre colorate dei pulsanti sono disallineate rispetto ai pulsanti. Nessuna delle due cause era nel foglio precedente: la prima non era mai stata gestita in nessuna versione, la seconda era un valore sbagliato dalla riscrittura.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La tendina e le sue voci usano un fondo opaco rgb(43,45,56) e testo rgb(245,246,250), 12.67:1 misurato sul render
- [x] #2 Il fondo opaco vale per tutti e nove i select dell'app: verificato nudo, con la classe dello split e dentro un campo
- [x] #3 L'alone dei pulsanti non ha scostamento: profilo dei pixel simmetrico sopra e sotto (25 contro 22 a 1 px, 13 contro 11 a 12 px)
- [x] #4 Il valore vecchio riprodotto per confronto: 0 di alone sopra la pillola e da 30 a 21 per 12 px sotto, cioe la striscia staccata segnalata
- [x] #5 Le due trappole sono scritte in web/README.md e CLAUDE.md, con i numeri che le reggono
- [x] #6 Nessuna dipendenza nuova, nessun cambio di contratto, i 314 test e la build passano
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Diagnosi. La tendina: nessuna versione stila le option e il controllo sta su un riempimento traslucido; la superficie del menu la dipinge il browser a partire da quel colore, e con alpha sopra il chiaro di sistema esce un menu bianco con il testo quasi bianco che l'app eredita. L'alone: --shadow-glow era 0 16px 30px -14px, cioe scostato di 16 px verso il basso, quindi non un alone intorno alla pillola ma una striscia colorata sotto.
Verifica. Il primo tentativo di misura era falsato: lo screenshot e a 488x1055 mentre il riquadro dell'elemento e in pixel CSS 390x844 (scala 1.25), quindi la finestra di analisi finiva altrove. Corretta la scala, il confronto ha rivelato un secondo problema: due fogli di stile erano vivi insieme, perche il service worker serviva il CSS vecchio dalla cache e il suo :root vinceva ancora su --shadow-glow. La prova e venuta dal registrare, a ogni scatto, l'ombra calcolata: dopo aver tolto lo stile inline il valore era ancora il vecchio. Azzerati service worker e cache, la misura e netta.
Nota per l'uso: un client che ha gia installato il service worker puo continuare a servire il foglio vecchio finche non ricarica (e a volte serve svuotare la cache del sito). E il motivo per cui, subito dopo un aggiornamento, si puo vedere ancora il difetto corretto.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Le due cause erano entrambe reali e nessuna delle due era nel foglio scritto a mano: una superficie dipinta dal browser che non puo prendere un colore con alpha, e un alone con scostamento verticale. Corrette e misurate sul render: tendina opaca a 12.67:1 su tutti e nove i select, alone centrato con profilo simmetrico, contro il valore vecchio che dava 0 sopra e 30-21 sotto. Documentate in web/README.md e CLAUDE.md. Build, tsc e 314 test ok, nessuna dipendenza nuova e nessun cambio di contratto.
<!-- SECTION:FINAL_SUMMARY:END -->
