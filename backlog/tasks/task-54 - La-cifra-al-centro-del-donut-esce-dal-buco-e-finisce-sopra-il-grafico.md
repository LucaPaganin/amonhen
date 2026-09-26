---
id: TASK-54
title: La cifra al centro del donut esce dal buco e finisce sopra il grafico
status: Done
assignee: []
created_date: '2026-09-26 07:40'
updated_date: '2026-09-26 07:46'
labels:
  - bug
dependencies: []
ordinal: 53500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Segnalato dall'uso: nel cruscotto la cifra al centro della torta (16.784,39 EUR su 12 mesi) e troppo grande e si sovrappone in parte agli archi. Causa: la dimensione del testo segue la larghezza della finestra (clamp(1.2rem, 5.2vw, 1.55rem)) mentre il raggio della torta lo decide il lato minore del contenitore (recharts dimensiona sul min(width, height), e il contenitore e alto 200px): su schermo largo il testo cresce fino al tetto mentre il buco resta quello, e una cifra lunga lo attraversa. Il numero e l euro devono stare dentro il buco a qualunque larghezza e per una cifra lunga.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A 390px e a 720px di larghezza il riquadro della cifra al centro sta dentro il cerchio interno della torta con margine visibile, verificato misurando i bounding box nel browser
- [x] #2 Con una cifra piu lunga di quella attuale (periodo a 24 mesi o conto singolo con milioni) il testo resta dentro il buco, o rimpicciolisce, invece di attraversare gli archi
- [x] #3 Il simbolo dell euro resta leggibile sullo sfondo del buco
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Causa misurata: la cifra era dimensionata in vw (clamp(1.2rem, 5.2vw, 1.55rem)) mentre il raggio della torta segue il lato minore del riquadro (200px, non la larghezza): a 846px la finestra dell utente il font arrivava al tetto di 24.8px con il buco fermo a 63px di raggio, e la cifra lo attraversava. Fix: .chart--pie e un contenitore (container-type: size) e la cifra e in cqmin (8cqmin), quindi font e buco seguono lo stesso lato; buco portato al 68% del raggio (anello 20px) e simbolo dell euro al 72% della cifra. Misure nel browser sul ledger reale a 390px e 846px: 16.784,39 EUR -> raggio interno 67px, margine 20px; 1.234.567,89 EUR (sette cifre, il massimo che il ledger puo produrre) -> margine 7px. Le due larghezze danno lo stesso margine, come previsto: entrambi i termini seguono il lato minore. Nota: il modello di visione aveva segnalato anche clipping del sottotitolo del cruscotto, del pulsante Sincronizza e della fonte della citazione; misurato nel DOM, nessuno dei tre e vero (scrollWidth = clientWidth, il sottotitolo e integro, il pulsante finisce a 368px su 390, nessun overflow orizzontale del documento).

L'AC nomina 390px e 720px: 720 sta fra le due larghezze misurate (390 e 846) e il margine e lo stesso per costruzione, non per fortuna — sotto i 200px di larghezza il lato minore e la larghezza e font e buco calano insieme, sopra e l altezza (200px) per entrambi, quindi la cifra non puo attraversare gli archi a nessuna larghezza.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La cifra al centro della torta e ora dimensionata sul contenitore (8cqmin) invece che sulla finestra, con il buco al 68% del raggio e il simbolo dell euro al 72% della cifra. Verificato misurando i bounding box nel browser sul ledger reale: margine 20px dentro il cerchio per il totale attuale e 7px per una cifra da milioni, identico a 390px e a 846px, la larghezza della finestra da cui era arrivata la segnalazione. web/README.md documenta la regola e le misure.
<!-- SECTION:FINAL_SUMMARY:END -->
