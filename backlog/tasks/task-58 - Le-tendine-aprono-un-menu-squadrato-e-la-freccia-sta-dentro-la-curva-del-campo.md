---
id: TASK-58
title: Le tendine aprono un menu squadrato e la freccia sta dentro la curva del campo
status: Done
assignee: []
created_date: '2026-09-26 10:53'
updated_date: '2026-09-26 11:09'
labels: []
dependencies: []
type: bug
ordinal: 57500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Difetto riportato dall uso vero, su Chrome a 390x844: aprendo una tendina il menu che compare ha gli angoli vivi mentre il campo che lo apre e una pillola, e la freccia del campo sta a 3.5px dal bordo destro, cioe dentro la curva di 22px, dove legge come appoggiata al muro e fa sembrare la curvatura eccessiva. Sono due facce dello stesso fatto: la tendina e l unico controllo che il browser disegna per intero. Il foglio dipinge la pillola, il motore dipinge freccia e menu, e nessuna regola CSS aveva mai toccato nessuno dei due. La specifica di design dice che nulla ha un angolo vivo (web/README.md, "One family of shapes"), quindi il menu nativo quadrato e una violazione della regola, non un dettaglio di gusto. Il menu e anche l unica superficie dell app la cui leggibilita dipende dal motore: la voce scelta la colora il sistema in azzurro, fuori dalla tavolozza.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La freccia che si vede e disegnata dal foglio e sta a 16 px dal bordo destro (misurato sul render a 4x) con il testo che non ci finisce sotto
- [x] #2 Dove il motore lo consente (appearance: base-select) il menu aperto e una lastra d angoli tondi larga quanto il campo con voci alte almeno 44 px e la voce in vigore segnata dall ambra
- [x] #3 Su un motore che non conosce ::picker(select) la tendina resta quella nativa opaca e leggibile come prima
- [x] #4 La voce attiva da tastiera si vede e la scelta resta annunciabile da uno screen reader
- [x] #5 Nessun valore scelto e troncato dalle tendine dell app ne finisce sotto la freccia (misurato sul render in ogni schermata); l unica etichetta piu lunga del campo e l opzione lunga della card che era gia troncata prima di questa modifica
- [x] #6 web/README.md e CLAUDE.md dicono cosa dipinge il foglio e cosa il motore; npm --prefix web run build e uv run pytest -q passano
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Sulla tendina: appearance none e una freccia disegnata dal foglio a 16 px dal bordo (12x8 px di disegno), col padding-right che le riserva il posto.

2. Dentro @supports (appearance: base-select): appearance base-select, ::picker-icon nascosto, e ::picker(select) come lastra d angoli tondi (raggio 18, --menu opaco, ombra di sistema), voci alte 44 px, voce in vigore con la tinta ambra e il colore d accento.

3. Misura sul render a 4x con il fondo reso magenta: posizione e dimensione della freccia, geometria del menu, altezza righe, troncamento del testo su ogni tendina dell app.

4. Prova da tastiera: la voce attiva si deve vedere.

5. Aggiornare web/README.md (sezione Design) e CLAUDE.md; build e test.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Freccia: appearance none piu chevron in data URI 12x8 a 'right 16px center', padding-right 40px. Misurato sul render a 4x (Chrome 153, viewport 390x844): 12.0 x 7.0 px, 16.0 px dal bordo destro, centrata a 0.125 px dal centro; prima era a 3.5 px dal bordo dentro la curva di 22.

Menu: nel blocco @supports (appearance: base-select) il picker e il controllo si dichiarano entrambi base-select, ::picker-icon si nasconde e la superficie la dipinge il foglio. Misure a 4x: pannello 362 x 188 px (6 di padding + 4 righe da 44), larghezza uguale al campo, angoli tondi (inset 13 px a dy=0 che scende a 0 entro 16 px, cioe il raggio --radius di 18), riga in vigore a (88,82,75) con testo (242,207,134) d accento, gap di 8.25 px sotto il campo.

Trappola trovata verificando: appearance base-select sul solo controllo non basta, il picker resta appearance none e Chrome disegna il menu nativo (150 px, evidenziazione azzurra, righe ~35 px). Dichiararlo anche su ::picker(select) e cio che accende le regole del foglio.

Seconda trappola, un difetto introdotto e poi corretto: le tendine con class input (categoria di una proposta, categoria di una regola) perdono contro la coda di .input (0,1,0) della lastra dei campi, quindi restavano senza freccia (appearance none toglie quella del motore) e con il fondo translucido. Aggiunto select.input alle liste: ora quei campi hanno freccia, fondo opaco e padding 40, e la classe .input smette di reintrodurre il menu bianco che il commit 25b2365 aveva tolto.

Tastiera: con il picker aperto ArrowDown sposta l evidenza; la riga attiva passa da (43,45,56) a (60,61,72), cioe --fill-2 sul fondo del menu, la stessa tinta che l app usa sull hover di una voce nel foglio.

Ripiego: forzando appearance none su controllo e picker il menu torna quello nativo, righe a --menu (43,45,56) con testo chiaro, evidenziazione azzurra del sistema sulla voce corrente, come nella schermata segnalata: nessuna regressione sul percorso senza ::picker(select).

Testo: misurato su ogni schermata (Coda, Movimenti, Categorie e regole, Conti, editor dello split). Nessun valore selezionato eccede lo spazio disponibile (peggiore: 132 px su 306 nei filtri; 75 su 172 nelle card; 66 su 140 nello split). L unica etichetta che non entra e l opzione lunga 'Nessuna categoria: rifiuta la proposta' (281 px) nella card, che era gia troncata prima (196 px disponibili) e resta visibile per intero nel menu: difetto preesistente, non toccato qui.

Revisione di gusto indipendente (agente reviewer, read-only, istruzioni di .pi/agents/taste-reviewer.md): nessun must-fix sul blocco CSS; due rilievi di prosa, entrambi accolti. Il titolo del bullet del README affermava ancora che le due superfici le dipinge il browser, mentre il corpo dice il contrario: il bullet e stato spezzato in due (la tendina, e l alone che non porta offset). La distanza della freccia del motore era scritta 4 px dove la misura e 3.5 px: corretta nel README e nel commento di styles.css.

Verifica finale sul bundle costruito, senza stili iniettati e con service worker e cache cancellati: appearance base-select su controllo e picker, padding-right 40px, chevron presente, fondo rgb(43,45,56), riga del menu min-height 44px, pannello raggio 18px e padding 6px, sia per una tendina nuda sia per una con class input. Albero di accessibilita: le tendine restano combobox con nome ed expanded, le voci option con selected, e ArrowDown sposta focused sulla voce successiva.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Le due facce dello stesso fatto: la tendina era l unico controllo disegnato dal motore, quindi pillola con la freccia a 3.5 px dal bordo (dentro la curva di 22) e menu squadrato con evidenziazione di sistema. Ora il foglio dipinge la freccia — appearance none piu chevron 12x8 a 16 px dal bordo, con padding-right 40 che le riserva il posto — e, dove il motore lo consente (::picker(select), Chrome 135 e oltre), anche il menu: lastra d angoli tondi raggio 18 larga quanto il campo, righe alte 44 px, la voce in vigore in ambra. Il percorso di ripiego resta quello nativo, opaco e leggibile. Nel farlo sono emersi due difetti: appearance base-select va dichiarato anche sul picker o il menu resta del sistema, e le tendine con class input perdevano contro la coda di .input, restando senza freccia e con il fondo translucido che il commit 25b2365 aveva tolto. Verificato a 4x sul render di Chrome 153 a 390x844 con un fondo magenta per isolare le forme (freccia 12x7 a 16 px, pannello 362x188 con angoli tondi, righe 44, riga scelta (88,82,75) con testo d accento), piu tastiera, albero di accessibilita, percorso di ripiego e misura del troncamento su ogni schermata; revisione di gusto indipendente senza must-fix; build e 314 test verdi.
<!-- SECTION:FINAL_SUMMARY:END -->
