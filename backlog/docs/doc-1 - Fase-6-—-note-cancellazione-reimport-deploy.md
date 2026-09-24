---
id: doc-1
title: 'Fase 6 — note, cancellazione, reimport, deploy'
type: specification
created_date: '2026-09-24 18:40'
updated_date: '2026-09-24 20:32'
---
# Fase 6 — nota locale, cancellazione, reimport, deploy

Stato: costruita (TASK-43…TASK-51). La fonte del prodotto resta
`desiderata-monitoring-finanziario.md` v1.3, che in §5.1, §5.4, §6 e §9 dice cosa
questa fase aggiunge; questo documento tiene le decisioni prese con l'utente e le
alternative scartate, che nella specifica non hanno posto.

## Decisioni prese con l'utente (2026-09-24)

| Domanda | Scelta |
|---|---|
| La nota segue la riga o l'identità? | Colonna sulla riga, più una copia nel tombstone: il reimport e il ripristino la restituiscono, una riga ricreata con un identificativo nuovo no |
| Dove vive la flag di reimport? | Colonna `accounts.reimport_deleted`, default 0, comandata dal pannello Conti |
| Cancellare una gamba di giroconto? | Sgancio automatico: il link si rifiuta, l'altra gamba torna in coda, poi la riga si cancella |
| §5.4 dopo una cancellazione? | Differenza spiegata: un quarto esito, mai sottratto in silenzio |
| Sync dietro l'API? | Richiesta sincrona con un guardiano di processo, risposta con l'esito per conto |
| Tombstone visibili? | Sì: cestino sotto il conto, con ripristino di una riga |
| Build e consegna? | CI → GHCR su un tag, NAS in pull, senza il repository |

## Perché l'identità del tombstone è quella che è

La chiave è l'identificativo della banca, o l'impronta di contenuto **nella forma
esatta in cui la riga è stata scritta** (`d`, `d:r2`, `d:<external_id>`). La
soppressione riconosce il movimento in tre modi (§5.1), e ognuno è una relazione
che il ledger aveva già: lo stesso identificativo; lo stesso contenuto che arriva
dall'altro percorso di ingest; la gamba contabilizzata di un movimento in attesa
cancellato qui (`PENDING_WINDOW_DAYS`). Un movimento dello stesso stato non si
riconosce mai dal solo contenuto, perché quattro accrediti identici nello stesso
giorno sono quattro movimenti e cancellarne uno non deve sopprimere il gemello.

Scartate: la tolleranza su data e importo per tutti (sopprimerebbe i gemelli) e
l'identificazione per sola impronta (stessa ragione).

## Perché il ripristino passa da `record`

`restore_deleted` non scrive da fuori: chiama `record(..., restoring=True)`, che
solleva il veto del tombstone — la cosa che si sta disfacendo — e lascia in piedi
il dedup. Un movimento che il ledger tiene già sotto una delle identità che il
dedup conosce torna come `duplicate`, non come una seconda riga. Quello che il
ripristino non può sapere è un movimento tornato sotto un'identità che il
tombstone non porta: è il limite dell'impronta nella zona di sovrapposizione, e il
posto dove accorgersene è la lista del cestino.

## Cosa questa fase non fa

- Non ripristina la categoria di un movimento cancellato: il ripristino rimette
  il movimento e la sua nota, e la categoria la decide di nuovo l'ingest o una
  persona. Una categoria è una decisione sul denaro, non un campo del payload.
- Non rende editabile nient'altro: importo, data e descrizione restano ciò che la
  banca ha dichiarato, perché la verifica di §5.4 confronta quella dichiarazione
  con il ledger.
- Non sincronizza tra processi: il guardiano è di processo, quindi un `amonhen
  sync` da riga di comando mentre il server sincronizza resta un secondo
  scrittore sullo stesso file SQLite. Conviverci è una decisione, non una svista.
- Non prova il deploy: l'immagine non è mai stata costruita su questa macchina, e
  la prima costruzione vera è il primo tag.
