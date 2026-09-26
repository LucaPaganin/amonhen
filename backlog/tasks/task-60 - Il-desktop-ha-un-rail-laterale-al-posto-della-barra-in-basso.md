---
id: TASK-60
title: Il desktop ha un rail laterale al posto della barra in basso
status: Done
assignee: []
created_date: '2026-09-26 11:32'
updated_date: '2026-09-26 13:17'
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
- [x] #1 Sopra i 1024px il rail e fisso a sinistra, largo 248px (il gettone --rail, non i 232 del piano: a 232 la voce piu lunga con il badge misurava 115px in 109 e andava a capo), con icona, nome per esteso e badge della coda, e la sezione corrente marcata con aria-current=page
- [x] #2 Sopra i 1024px tabbar, pulsante Sezioni e cassetto sono spenti - display:none, cioe nessun layout, nessun tab stop, nessun nodo di accessibilita - e .app__main non riserva piu spazio in fondo per la tabbar
- [x] #3 Il contenuto non finisce sotto il rail a nessuna larghezza sopra i 1024 (misurato: nessun elemento di .app__main lo attraversa) e l ordine di tabulazione segue il rail poi la schermata
- [x] #4 A 390px e a 768px tabbar e drawer sono quelli di prima, identici (confronto di scatole e di pixel con il build precedente, sullo stesso ledger)
- [x] #5 La lista delle sezioni resta una sola: rail, tabbar e drawer la leggono da Navigation.tsx
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
web/README.md e CLAUDE.md, npm --prefix web run build, uv run pytest -q, revisioni AGENTS.md, commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Misure a 1484/1280/1024/768/390: rail 248x925 a x=0 (display:none sotto i 1024), .app__main x=248 w=1236 a 1484, x=232 w=1048 a 1280, w=776 a 1024, e nessuno scorrimento orizzontale a nessuna delle cinque larghezze. .appbar__inner x=258 w=1216, cioe la stessa cornice del contenuto. Sopra i 1024 tabbar, pulsante Sezioni e cassetto sono display:none. Sette voci raggiunte cliccando una per una, ognuna con aria-current=page e il titolo della schermata corrispondente; l ordine di tabulazione e sette voci del rail, poi Sincronizza, poi la schermata. Voci alte 44px, nessuna etichetta a capo o troncata (la piu lunga, Categorie e regole, 137px di 168 disponibili); il fuoco si vede (contorno 2px accento).

Il primo tentativo era largo 232 come il piano, e la misura l ha smentito: la voce Da confermare con il badge della coda chiedeva 115px in 109 e mandava l etichetta a capo (voce alta 66px invece di 44, con Da da solo su una riga). Il gettone e a 248, l etichetta sta su una riga sola e resta margine anche per un contatore a tre cifre (31px sul piu lungo). La ragione e scritta nel commento del gettone e nel README.

Sotto i 1024 non si muove niente, e la prova e un confronto: stesso ledger, build precedente contro questa, ogni scatola di ogni elemento visibile a 390 e a 768 identica (530, 796 e 278 per schermata) e sei screenshot byte per byte identici. Il primo confronto aveva dato differenze su tutte le schermate: erano un sync cliccato fra le due catture (aveva cambiato un saldo) e un anello di fuoco rimasto addosso al pulsante del menu dalla sessione prima. Due lezioni finite in CLAUDE.md: si confronta sullo stesso ledger, e prima di confrontare pixel si toglie il fuoco.

Revisione di gusto, di specifica e di documentazione (tre revisori indipendenti, read-only, ognuno col suo modello). Il difetto vero l hanno trovato in due su tre: .app { padding-left: var(--rail) } spostava anche le tre schermate che disegnano .app senza navigazione - primo avvio, caricamento, server non aggiornato - lasciando il wizard di un desktop fuori asse con 248px vuoti a sinistra. Corretto con .app:has(.apprail) e verificato sul ramo vero, non simulato: server avviato con AMONHEN_CONFIG_FILE su un file inesistente, a 1484 la colonna del setup misura x=122 (centrata nella finestra, 0 di padding) e la stessa colonna dentro la shell si centra sull asse del contenuto (centro 866 = centro del contenuto). La specifica ha confermato che 248 e una correzione giustificata dalla misura e non uno scostamento non approvato.

Altri rilievi accolti: AppRail non e piu esportato (un solo chiamante, nello stesso modulo); il commento dell hover diceva il falso (anche barra e cassetto si guardano con lo stesso puntatore) ed e riscritto; tre commenti nuovi dicevano ancora 232px, ora dicono 248 o rimandano al gettone; e le prose di navigazione di web/README.md, README.md e CLAUDE.md presentavano barra e menu come le uniche vie - sei punti aggiornati, perche sopra i 1024 quei due pezzi sono spenti.

Difetto trovato misurando il wizard a 1484, introdotto dalla fetta 1 e quindi in ambito: la colonna a 1240 stendeva l Application ID del setup a 1214px - centocinquanta caratteri su una riga per un identificativo - dentro una scheda vuota per meta. Corretto nella stessa sezione del desktop: la schermata del setup si tiene a 720px e si centra, i campi a 640 e i suggerimenti a 72 battute. Le due regole mordono davvero (campo misurato 640, suggerimento 632) invece di essere decorazione.

Specifica di prodotto portata a 1.6 con la voce del desktop: la colonna che si prende la finestra, le griglie, il rail che sostituisce barra e menu (le due vie di §0.4 restano quelle del telefono), e la regola che cio che e stretto per natura resta stretto. Il revisore di documentazione aveva detto che la specifica non serviva; l ho aggiornata lo stesso perche AGENTS.md la vuole aggiornata nello stesso cambiamento in cui la decisione cambia, e la frase di §0.4 si legge al presente.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Sopra i 1024px le sezioni smettono di essere una pillola in fondo a una finestra larga: la stessa lista di SECTIONS sale in un rail fisso da 248px a sinistra, a tutta altezza, con la vetrata della barra in basso e gli angoli tondi a destra, ogni sezione col nome per esteso e il badge della coda; tabbar, pulsante Sezioni e cassetto sono spenti, e il contenuto si sposta accanto invece di finirci sotto (.app sposta solo dove il rail c e, quindi il primo avvio resta centrato). Il rail e la terza forma della stessa voce: .navitem e condiviso con il cassetto e la barra tiene la sua variante compatta. 248px e non i 232 del piano, perche a 232 la voce piu lunga col badge andava a capo. Verificato: sette destinazioni raggiungibili con aria-current, fuoco visibile, nessuna sovrapposizione, ordine di tabulazione rail-schermata, nessuno scorrimento orizzontale a cinque larghezze; a 390 e 768 scatole identiche e sei screenshot byte per byte identici al build precedente sullo stesso ledger. Nella stessa fetta: il wizard a 1484 non e piu un modulo da 1214px ma una colonna da 720 centrata, i campi si fermano a 640 e i suggerimenti a 72 battute; specifica a 1.6, README, CLAUDE.md e web/README.md aggiornati; build e 314 test verdi.
<!-- SECTION:FINAL_SUMMARY:END -->
