# Desiderata — AmonHen, sistema di monitoring finanziario personale

Versione 1.42 — novembre 2026

*1.28 · la coda chiede anche gli accrediti: dall'agosto 2026 un accredito senza categoria sta in
*Accrediti da chiarire*, e si dichiara entrata, rimborso o contributo.
1.29 · i saldi della banca che contano sono un elenco chiuso (sezione 5.4): un tipo che non vi
compare non si verifica, non entra nei saldi e **Conti** lo segnala, invece di valere come
disponibile.
1.30 · una categoria si rinomina, e le sue regole la seguono.
1.31 · il contributo copre anche le spese rare: si divide su tutto ciò che il conto paga nel
mese, quindi la riserva ne è al netto e lo stesso denaro non conta due volte.
1.32 · la storia delle versioni e il dettaglio delle fasi concluse stanno in `docs/storia-desiderata.md`; i motivi che vivevano solo lì sono passati nel corpo.
1.33 · il numero su **Da confermare** conta anche gli accrediti da chiarire.
1.34 · il limite di richieste di una banca ferma quel conto invece di trattenere il sync (sezione 5.1), un riavvio
non consuma il limite, e una regola di giroconto si applica subito e prima dell'abbinamento (sezione 5.3).
1.35 · gli accrediti da chiarire partono da una data che si imposta: sul NAS è tutta la storia.
1.36 · la ciambella delle spese per categoria torna sul cruscotto, anche sul telefono; il periodo ha *Questo mese* e due date a scelta, anche in **Movimenti**.
1.37 · un conto chiuso non si ricostruisce: la storia parte dall'apertura di Fineco e il denaro arrivato da lì sta su un conto virtuale (sezione 5.3).
1.38 · l'assistente è tolto (sezione 5.9); **Statistiche** legge ogni categoria sui mesi completi, e il **Budget** dice quanto prende di solito (sezione 5.15).
1.39 · **Movimenti** si stringe anche per importo.
1.40 · il sistema pianifica anche verso dove si vuole andare (sezione 5.16): obiettivi, i fatti
che il ledger non vede, i parametri fiscali come dati con la loro fonte, il confronto fra fondo
pensione e PAC, il portafoglio dichiarato a mano e le proiezioni per scenari. Le proiezioni non
sono previsioni (sezione 3), e l'analisi periodica con un modello si fa fuori dall'app (sezione 8).
1.41 · la distanza in giorni fra le due gambe di un giroconto si configura: due giorni per
l'abbinamento automatico, sette per quello a mano, che arriva al prelievo da PayPal accreditato giorni dopo.
1.42 · **Statistiche** ha i suoi grafici: il totale per mese, la composizione, mediana contro media e la mappa di calore (sezione 5.15).*

La storia completa è in `docs/storia-desiderata.md`.

Questo file è la definizione di prodotto: cosa il sistema deve fare, i vincoli,
i non-obiettivi, l'ordine dei lavori e lo stato di ciascuna fase (sezione 9). `CLAUDE.md`
dice come è fatto: architettura, invarianti, comandi. Quando una decisione cambia
il prodotto, questo file si aggiorna **nello stesso cambiamento** del codice — una
specifica che insegue il codice smette di essere la fonte, e la fetta successiva
implementa il prodotto vecchio.

---

## 1. Problema

Il flusso di cassa reale è distribuito su più conti (stipendio su banca principale, spese su Revolut, ~840 €/mese verso un conto congiunto). I conti sono già tutti collegati in console Enable Banking, ed è disponibile l'export manuale dei movimenti da ciascun istituto: la connettività non è il collo di bottiglia.

Il collo di bottiglia è che i dati non vengono mai uniti. Le analisi fatte finora sono istantanee su un singolo export, elaborate a mano: i giroconti tra conti risultano contati due volte, una per gamba; i movimenti interni vengono scambiati per spese; e nulla di tutto questo è ripetibile il mese successivo senza rifare il lavoro da capo.

Il sintomo è "non so quanto spendo davvero". La causa è assenza di riconciliazione e di automazione, non mancanza di accesso ai dati.

## 2. Obiettivi

1. **Vista unificata del flusso.** Tutti i conti collegati confluiscono in un unico ledger riconciliato, con storico profondo abbastanza da rendere calcolabili le metriche della sezione 5.6.
2. **Una spesa mensile che un mese strano non sposta**, con le spese ricorrenti separate da quelle rare.
3. **Riconciliazione automatica dei trasferimenti** tra conti: un movimento interno appare una volta sola e non conta come spesa.
4. **Ripetibilità**: il dato si aggiorna da solo, senza download manuali. Il sync Enable Banking è **parte del sistema**, non un servizio esterno a cui il sistema si appoggia.
5. **Interfaccia propria.** Il sistema ha una UI mobile-first da cui rivedere le categorie, correggere gli split e leggere le metriche. Non è un requisito opzionale: è il modo in cui il sistema viene effettivamente usato.
6. **Sapere dove si va, non solo dove si è stati.** Quanto versare nel fondo pensione e quanto nel PAC dipende da cosa si vuole raggiungere e quando: il sistema tiene gli obiettivi e mostra le conseguenze di una ripartizione, con i parametri fiscali dell'anno e ipotesi scritte (sezione 5.16). Il monitoraggio dice quanto si può mettere da parte; la pianificazione dice dove.

## 3. Non-obiettivi

Esplicitamente fuori scope, per evitare scope creep:

- Integrazione API con il broker, e lettura dei suoi estratti. Le posizioni e il loro valore si dichiarano a mano (sezione 5.16), la liquidità del broker pure (sezione 5.8).
- Calcolo di rendimenti di portafoglio (TWR, IRR). Il broker è già un cruscotto: il portafoglio si legge come valore contro versato netto.
- Previsioni di spesa, forecasting, ottimizzazione automatica del budget. Le proiezioni verso un obiettivo (sezione 5.16) non lo sono: sono aritmetica su ipotesi che una persona scrive e che stanno accanto a ogni cifra, e la spesa che usano è quella osservata (sezione 5.6), non stimata.
- Consulenza. Il sistema calcola le conseguenze di una scelta — quanto versare, dove, per quale obiettivo — e non dice quale fare: non sceglie strumenti, comparti né percentuali.
- Il calcolo delle imposte dovute o della dichiarazione. I parametri fiscali servono a confrontare scelte; per una cifra da dichiarare fanno fede la busta paga, il CU e i documenti del fondo e del broker.
- Categorizzazione completamente automatica senza revisione umana.
- Multi-utente, multi-valuta, condivisione.
- Gestione dei crediti verso terzi. Le spese anticipate per altri non vengono modellate come crediti: nessun elenco dice chi deve ancora cosa, e finché non paga la spesa resta alta. **Un rimborso o una quota non sono entrate**, e quello che non si modella è la *coppia* con la singola spesa: un rimborso copre spesso molte spese insieme. La spesa però è al netto: un accredito messo in una categoria abbassa quella categoria, e un contributo alle spese abbassa il totale (sezione 5.6).
- App nativa. La UI è una PWA.

## 4. Vincoli

| Vincolo | Implicazione |
|---|---|
| Side project da weekend | Ogni fase deve essere deployabile e usabile da sola |
| NAS UGREEN, 8 GB RAM | Niente LLM locali; eventuali chiamate LLM vanno a API esterne |
| Accesso via Tailscale | Nessuna esposizione pubblica, nessun dominio, nessun auth complesso |
| Dati bancari personali | Storage locale; nessun invio di importi o saldi a terze parti |
| Enable Banking come provider PSD2 | Il modello dati deve reggere pending → booked e id instabili |

## 5. Requisiti funzionali

### 5.1 Ingest

Due percorsi distinti che **devono convergere nella stessa tabella e condividere la stessa logica di deduplica**.

**Percorso A — sync PSD2 (continuo).** Sync automatico schedulato da Enable Banking su tutti i conti già collegati in console. Copre il presente e il futuro.

**Il limite della banca.** Una banca conta le letture fatte senza la persona e, oltre il limite, le rifiuta con un 429: Fineco lo ha fatto tre volte in un giorno di riavvii. Insistere non serve e può consumarne altre, quindi l'app riprova per pochi secondi, poi lascia quel conto per questo giro e passa agli altri; un `Retry-After` breve si rispetta, uno lungo chiude subito. Il corpo del rifiuto finisce nei log, e **Conti** dice sul conto che è fermo e quando è stato letto l'ultima volta, finché una lettura non riesce. Un riavvio non è un sync: il server conta l'intervallo dall'ultimo sync finito, e all'avvio applica soltanto, senza chiedere nulla alle banche, ciò che un processo fermato a metà ha lasciato indietro. L'IBAN già noto di un conto non si richiede.

**Un periodo scelto, per un conto.** Il sync incrementale decide da sé da dove partire — l'ultimo movimento del conto meno una settimana — e un buco in mezzo allo storico non lo richiede mai. Per questo un conto collegato si sincronizza anche su un periodo `dal`/`al` scelto da chi lo lancia, passato compreso: dal pannello del conto in **Conti**, da `POST /api/sync/period` e da `amonhen sync --account <nome> --from AAAA-MM-GG --to AAAA-MM-GG`, con un'anteprima che non scrive niente. Il periodo si controlla prima di chiamare la banca (`dal` non dopo `al`, `al` non dopo oggi, conto collegato) e condivide il lucchetto del sync normale.

- *Finestre.* Il periodo si chiede a finestre di giorni interi, larghe `max_window_days` del conto in `accounts.json` (30 di default): alcune banche rifiutano trenta giorni. Una finestra che la banca rifiuta come intervallo si dimezza, fino a un giorno, e la larghezza ridotta vale per il resto del periodo; un giorno rifiutato fa fallire quella finestra e basta. I giorni restano interi perché il ledger numera i movimenti identici di uno stesso giorno dentro un lotto, e un giorno spezzato fra due lotti li numererebbe in un altro modo.
- *Esito per finestra.* Ogni finestra dice quanti movimenti la banca ha restituito o con che errore l'ha rifiutata, e le finestre riuscite si scrivono anche quando un'altra fallisce: quella fallita si riprova con un periodo più stretto. Il limite PSD2 resta (circa novanta giorni, qualunque periodo si chieda): una finestra vuota è una risposta della banca, non un periodo coperto, e l'esito lo mostra come tale.
- *Stesse regole di scrittura.* Tutto passa da `Ledger.record`: rilanciare lo stesso periodo non scrive niente, una cancellazione resta tale salvo la flag del conto, un `PDNG` si promuove a `BOOK` come nel sync normale. Dopo la scrittura girano gli stessi passi — abbinamento dei giroconti dall'inizio del periodo, non dal più vecchio `start_sync_date`, poi le destinazioni dichiarate, la validazione e le regole — e l'esito porta lo stato della sezione 5.4 del conto: un mismatch che compare dopo un periodo passato è il segno di un doppione. I movimenti prima di `opening_date` non spostano il saldo calcolato, perché l'apertura li contiene già.
- *Il cursore non si sposta.* La sync incrementale successiva riparte da dove sarebbe ripartita, e `start_sync_date` non si modifica né limita il periodo chiesto a mano.
- *Probabili doppioni dell'import.* I periodi passati sono quelli che di solito arrivano da file, e lì l'impronta è il solo discriminante e contiene la descrizione: se la banca scrive un movimento in PSD2 diversamente che nell'export, lo stesso movimento entrerebbe due volte. Un movimento che il ledger scriverebbe ma che ha lo stesso conto, giorno e importo di una riga arrivata dall'altro percorso **non si scrive**: resta in `held_transactions` con la riga a cui somiglia, il pannello del conto lo elenca e una persona lo scrive o lo scarta, uno per uno. Lo scarto si ricorda, così rilanciare il periodo non chiede due volte la stessa cosa.

**Percorso B — import file (bootstrap e recupero).** Import di export CSV/OFX scaricati manualmente da ciascun istituto. Serve a due cose:

1. **Seed dello storico.** Le API PSD2 restituiscono tipicamente una finestra limitata (ordine dei 90 giorni; verificato: chiedendo il 2026-01-01 sono tornati movimenti dal 2026-06-14). Le metriche della sezione 5.6 richiedono 6 mesi per la spesa mensile tipica e 24 mesi per la riserva per spese rare: senza backfill da export non sono calcolabili prima di due anni di esercizio. L'import storico è quindi un prerequisito, non un extra.
2. **Recupero.** Consenso PSD2 scaduto, istituto temporaneamente indisponibile, buchi nel sync.

Requisiti comuni a entrambi i percorsi:

- Idempotenza: `external_id` del provider quando presente, con fallback `hash(data, importo, descrizione, conto)`. L'export CSV di solito non contiene l'`external_id`, e allora il fallback è il solo discriminante nella zona di sovrapposizione tra i due percorsi — per questo l'import ripara le lettere accentate che un export ha codificato due volte, altrimenti la stessa descrizione non coincide con quella PSD2: va testato esplicitamente reimportando un periodo già sincronizzato e verificando che il conteggio non cambi. Quando invece l'estratto una colonna di identificativo ce l'ha, la sezione **Importa** la mappa e quell'identificativo prende il posto dell'impronta come identità.
- Un adattatore per formato di export, che normalizza verso lo schema comune. I formati differiscono per istituto (colonne, segno dell'importo, formato data, separatore decimale).
- L'adattatore si può scegliere invece di scriverlo: dalla sezione **Importa** dell'app si dice quali colonne sono la data, l'importo (o Dare e Avere), la descrizione, il formato della data e dei decimali, e l'identificativo della banca quando c'è, e l'anteprima mostra le prime righe mappate prima che qualcosa venga scritto. Le righe che non si leggono si contano con la loro riga invece di fermare il file; i profili scritti per banca restano per la riga di comando.
- Gestione della transizione pending → booked senza duplicare la transazione.
- Payload grezzo conservato integralmente, con indicazione del percorso di provenienza, per poter riprocessare senza ri-fetchare né ri-scaricare.
- **Una cancellazione è una decisione che il sync rispetta.** Un movimento si cancella dal ledger e resta in `deleted_transactions` con l'identità con cui il ledger deduplica (l'identificativo della banca, altrimenti l'impronta di contenuto così com'era), il payload, la nota, com'era la riga e quando è stata tolta: senza quella copia il sync successivo riscriverebbe il movimento, e a mano non resta niente da rileggere. Un `PDNG` cancellato sopprime anche il `BOOK` che la banca manda dopo, anche quando lo contabilizza con un altro riferimento e un'altra data. La soppressione riconosce il movimento in tre modi, e sono le relazioni che il ledger conosce già: l'identificativo con cui è stato cancellato, lo stesso contenuto che arriva dall'*altro* percorso di ingest — è la zona di sovrapposizione della sezione 5.1, dove l'impronta è il solo discriminante — e la gamba contabilizzata di un movimento in attesa cancellato qui, che la banca manda giorni dopo con un altro riferimento e un'altra data. Esatta ovunque altro: quattro accrediti identici nello stesso giorno sono quattro movimenti, e cancellarne uno non deve sopprimere il suo gemello, quindi un movimento dello stesso stato non si riconosce mai dal solo contenuto. Una leg di un giroconto non si cancella lasciando l'altra appesa al conto di clearing: il link si rifiuta, l'altra gamba torna in coda, e la cancellazione lo dice. Il cestino di un conto elenca ciò che è stato tolto — data, importo, descrizione, nota e quando è sparito — e il ripristino di una riga la rimette nel ledger dal payload conservato, con la sua nota: una seconda volta è rifiutata, e il ripristino passa dalle stesse regole dell'ingest, quindi un movimento che il ledger già tiene non viene scritto due volte. Quello che il ripristino non può sapere è un movimento tornato sotto un'identità che il tombstone non porta — il limite dell'impronta nella zona di sovrapposizione — e il posto dove accorgersene è la lista del cestino.
- **Si cancella anche in blocco.** Nei movimenti si sceglie una pagina intera, o le righe che servono, e si cancellano insieme — ognuna come se fosse cancellata da sola, tombstone compreso, in una transazione sola — o si dà a tutte la stessa categoria come decisione della persona. Un giroconto e un movimento diviso restano com'erano: una categoria sola nasconderebbe il giroconto o butterebbe le parti, e si decidono aprendoli. Una riga che nel frattempo non c'è più ferma tutto il blocco prima che si scriva qualcosa: una pagina vecchia non cancella metà di quello che mostrava.
- **Il ritorno di una cancellazione è una decisione del conto.** Una flag per conto — spenta, perché cancellare deve significare cancellare — dice se il sync successivo riporta i movimenti cancellati: accesa, li riscrive dal tombstone con la loro nota e segna che sono tornati; spenta, li lascia fuori e l'esito del sync li conta fra i soppressi. Si accende per un conto solo, perché la ragione è la storia di quel conto — un consenso rinnovato, un periodo cancellato per sbaglio — non una proprietà del ledger, e spegnerla di nuovo non ricancella ciò che è tornato.
- **La ri-autorizzazione rinfresca, non accoda.** Un consenso può morire mentre la sessione che lo contiene è ancora valida, e rinnovarlo produce una sessione nuova mentre l'uid del conto resta lo stesso: la voce di `accounts.json` che ha quell'uid si aggiorna sul posto — nome e data d'inizio restano, perché il primo è il nome con cui il ledger conosce il conto e la seconda è la storia che ha già importato — e solo un conto mai visto viene aggiunto. Accodare una seconda voce significava, per un ledger che riconosce i conti per nome, un secondo conto con la stessa storia dentro.

L'import CSV ripara le lettere accentate che un export ha scritto due volte codificate, come fa l'estratto italiano di Revolut: la stessa spesa via PSD2 ha le lettere giuste, e l'impronta che le confronta altrimenti non coincide.

### 5.2 Modello a partita doppia

Ogni movimento è composto da N *postings* la cui somma è zero.

- **Spesa**: conto reale −X, categoria di spesa +X.
- **Giroconto**: conto A −X, conto B +X quando entrambe le gambe sono collegate; altrimenti la seconda gamba va su un conto virtuale — il conto di clearing per una coppia, un conto intitolato all'etichetta per una gamba sola verso un conto proprio non collegato. Nessuna categoria: non è spesa per costruzione, non per regola. I conti virtuali, tranne quello di clearing, si vedono in **Conti** con il loro saldo e i loro movimenti: denaro uscito dalla spesa deve potersi ritrovare.
- **Split**: più postings di categoria sullo stesso movimento.

### 5.3 Riconciliazione trasferimenti

- Match su: importo opposto, conti diversi, |Δt| ≤ 2 giorni (`AMONHEN_TRANSFER_MAX_GAP_DAYS`), nessuna delle due gambe già appaiata.
- **La prova è l'IBAN che ciascuna banca stampa sulla propria gamba.** Una gamba che nomina il conto dell'altra è evidenza; una che ne nomina un altro è una contraddizione, e la coppia si rifiuta: è la coincidenza d'importo che il matcher esiste per non accettare. Due accrediti dello stesso importo nello stesso giorno si distinguono così, e non tirando a indovinare.
- L'IBAN del conto si legge da `GET /accounts/{uid}/details` — la sessione elenca gli uid e nient'altro — e il sync lo registra sul conto quando manca. Senza quell'IBAN la prova non è disponibile, e i candidati si ordinano solo per chi nomina una controparte: entrambe le gambe (più forte), una sola, nessuna. Il metodo del link dice quale dei tre casi è stato (`…-unverified` quando il confronto non era possibile).
- Mai match sulle descrizioni (incoerenti tra istituti).
- In caso di ambiguità (più candidati compatibili), risoluzione via matching bipartito di peso massimo, non greedy.
- Ogni link ha un livello di confidenza e resta rivedibile a mano: si conferma, si annulla, si registra una gamba sola verso una destinazione dichiarata (sezione 5.3) e si abbinano due gambe a mano. L'abbinamento manuale accetta solo le coppie che il matcher stesso accetterebbe: conti reali diversi, importi uguali e opposti, nessuna split da perdere. La distanza è l'eccezione: a mano arriva a 7 giorni (`AMONHEN_MANUAL_PAIR_MAX_GAP_DAYS`), perché un prelievo da un borsellino come PayPal può arrivare in banca giorni dopo, e chi sceglie è la prova.
- Annullare una coppia **rifiuta** il link invece di cancellarlo, così il matcher non la ripropone al sync successivo; annullare una gamba sola la riporta in coda, senza categoria.
- **Il denaro che non è né spesa né entrata si dichiara.** Una voce di `passthrough` in `accounts.json` nomina una destinazione — il conto virtuale in cui finisce il lato non reale — e i testi che la banca stampa su quei movimenti, con `incoming_only` per le etichette che nominano una persona o una ditta: lo stesso nome vale nelle due direzioni, e il nome di una ditta porterebbe fuori dalla spesa il premio oltre al rimborso. Serve perché i due casi non si riconoscono altrimenti: un conto proprio non collegato non ha una contro-gamba da appaiare, e un accredito da fuori non ha un addebito che lo compensi. Sulla contabilità viva nessuno degli accrediti di un mese di prova ha un addebito di pari importo: quello che hanno in comune è chi li manda, non cosa pagano. Restano quindi fuori dalle entrate e fuori dalle spese, la loro categoria non viene toccata, e restano sul libro col nome della destinazione.
- **Un conto chiuso non si ricostruisce.** La storia parte dal 26 agosto 2025, quando Fineco è stato aperto: il periodo prima resta fuori, e con lui il conto ING chiuso. I bonifici arrivati da ING dopo quella data stanno sul conto virtuale *ING*, quelli di origine non ritrovata da un conto proprio su *Altri conti miei*: non sono né entrate né spese.

### 5.4 Invariante di correttezza

Per ogni conto e ogni periodo:

```
saldo_iniziale + Σ movimenti == saldo dichiarato dalla banca
```

Quali saldi contano è un elenco chiuso, per tipo dichiarato dalla banca:

| Tipi | Che cosa sono | Che cosa fa il sistema |
|---|---|---|
| `ITAV`, `CLAV`, `OPAV` | disponibile, movimenti in attesa compresi | si verifica contro il saldo calcolato con tutti i movimenti, ed entra nei saldi |
| `ITBD`, `CLBD`, `OPBD`, `PRCD` | contabilizzato | si verifica contro il saldo dei soli movimenti contabilizzati, ed entra nei saldi |
| `FWAV`, `XPCD` | previsione | si conserva, non si verifica e non entra nei saldi; serve solo all'avviso qui sotto |
| ogni altro tipo | sconosciuto | si conserva, non si verifica, non entra nei saldi e **Conti** lo segnala sul conto |

Un tipo sconosciuto non vale mai come disponibile: potrebbe essere una previsione, un fido o una nota, e il valore «disponibile» dato a tutto ciò che non si riconosceva è il modo in cui `FWAV` ha falsato verifica e curva della liquidità senza che nulla lo dicesse. Il segnale resta finché il tipo non entra in questo elenco, che è una decisione presa leggendone il significato. I saldi scritti da una persona (`manual:`, `anchor:`) non sono tipi della banca e contano sempre. Un conto la cui banca dichiara solo tipi sconosciuti resta `non verificato`.

Un saldo previsto dalla banca per una data futura resta fuori: descrive qualcosa che non è successo, quindi non si verifica e non entra nella liquidità. Se è negativo, il conto dice in **Conti** che la banca lo vede andare in rosso se si continua così: è un avviso, e non cambia né il saldo né l'esito della verifica.

Questa è la quantità conservata del sistema. Va verificata a ogni sync e l'esito è **visibile per conto** (pannello Conti), non sepolto in un log: non è una metrica di spesa, è lo stato di affidabilità di quel conto. La banca dichiara due figure per la stessa data — disponibile e contabilizzata — e ognuna si confronta con il saldo calcolato che significa la stessa cosa, così un controllo che fallisce dice quale delle due non torna, ed è ciò che distingue un movimento in attesa da un duplicato. Lo dice solo quando l'altra figura è stata dichiarata e torna: una banca che dichiara una figura sola — Revolut, il disponibile — non dice dove sta la differenza, e la verifica ne mostra l'importo. Un conto per cui nessuno ha dichiarato un saldo resta `non verificato`: il silenzio non è un assenso. Se non torna, ogni numero a valle è inaffidabile.

**Una differenza spiegata non è un guasto.** Gli esiti visibili per conto sono quattro, non tre: oltre a *verificato*, *mismatch* e *non verificato*, un conto la cui differenza è esattamente ciò che una persona ha cancellato a mano si legge **d'accordo salvo N movimenti cancellati a mano**, con l'importo, perché il ledger e la banca discordano davvero, ma per una decisione presa qui, e un rosso che nessuno può far sparire insegna a ignorare l'unica riga che conta. Ogni figura si confronta con i movimenti che conterrebbe: quella disponibile conta anche i sospesi cancellati, quella contabilizzata no. Una differenza che i tombstone non spiegano resta un mismatch, e il sync non chiama guasto ciò che è spiegato: lo annota.

**Il saldo iniziale è il punto fisso, non la correzione.** L'invariante misura da lì, quindi ricavarlo da un saldo dichiarato — saldo dichiarato meno i movimenti noti — serve una volta, per stabilire il punto di partenza: dopo, una differenza vuol dire un movimento che manca o uno di troppo, e ricavarlo di nuovo la sposterebbe dentro il saldo iniziale, dove la verifica non la vede più. Un conto collegato lo prende dal sync alla prima figura che la banca dichiara, e dalla contabilizzata quando c'è: un'autorizzazione carta che la banca toglie dal disponibile senza esporla come sospeso starebbe nel saldo iniziale e, il giorno in cui arriva, sarebbe contata due volte. Un conto aggiunto a mano lo ricava dal saldo che una persona dichiara. Ricalcolarlo resta possibile, perché un punto di partenza può essere sbagliato, ma è un'azione chiusa in fondo al pannello del conto, non un pulsante accanto al rosso: prima di scrivere dice di quanto cambia il saldo iniziale e che quella differenza non verrà più segnalata. Accanto a una verifica che non torna il pannello mostra invece quanto manca o avanza e gli ultimi movimenti del conto, che è dove di solito sta la risposta.

### 5.5 Categorizzazione

Pipeline a cascata, dal deterministico al probabilistico:

1. Normalizzazione del merchant (stringa grezza → nome pulito), usata dalle proposte e dal classificatore; le regole lavorano sulla descrizione.
2. Regole su un testo contenuto nella descrizione del movimento, o su un'espressione regolare scritta fra barre — una regola copre una famiglia di movimenti, non un solo nome; l'espressione copre le famiglie che la banca scrive in troppi modi per elencarli. Copertura attesa 80-90%.
3. Classificatore statistico leggero (logistica su char n-gram) sulla parte restante.
4. LLM solo sulla coda: transazioni mai viste, in batch asincrono, output sempre marcato "da confermare".

Nessuno stadio scrive una categoria definitiva senza che sia rivedibile. Nessuno stadio è bloccante per il sync.

**La coda dice cosa una proposta decide.** Le proposte — del classificatore e del modello — sono per *merchant*, non per movimento: un sì copre tutti i movimenti di quel merchant. Accanto alla categoria proposta, quindi, la coda porta quanto denaro aspetta, su quanti movimenti e quando sono passati — e i movimenti stessi, con giorno, conto, importo e descrizione, perché è da quelli che si riconosce una spesa — letto con lo stesso predicato della coda stessa: la cifra di una proposta non può contraddire la lista che le sta sotto. Fuori da quel conto resta ciò che un solo sì non può decidere — una split porta le sue parti, e si decide aprendola — quindi la cifra non promette un movimento che l'accettazione lascerebbe dov'è. Una proposta i cui movimenti sono già stati decisi — da una regola, da una split o da una persona — resta senza niente da pesare, e lo dice invece di mostrare uno zero.

**La proposta si corregge.** La categoria proposta è un punto di partenza, non un verdetto: si cambia prima di accettare, e accettare assegna la categoria *scelta* ai movimenti che la coda teneva per quel merchant. Non sceglierne nessuna è il rifiuto, perché è lo stesso gesto con l'esito opposto: una proposta che non merita una categoria non deve restare in coda per sempre. Il modello e il classificatore sbagliano su merchant che non hanno mai visto — misurato: il classificatore indovina l'86% dei merchant tenuti fuori dall'addestramento contro il 47% della categoria più frequente, e il 92% di ciò che propone sopra la soglia di confidenza — quindi la correzione è il modo in cui la coda resta utile mentre i due proponenti migliorano con quello che la persona decide.

**La regola è una cosa che si chiede.** Una regola è un'affermazione sui movimenti che la banca non ha ancora stampato, e una regola per ogni proposta accettata è una regola per ogni modo in cui un istituto scrive lo stesso esercente: il loro numero crescerebbe con la coda invece che con le decisioni prese. La casella che la chiede è quindi **spenta** quando la coda si apre: accettare assegna la categoria ai movimenti in attesa e non tocca `rules`. Accesa, accettare apre un dialogo con il testo della regola — precompilato con il nome del merchant, **modificabile**, ed è quel testo a essere scritto — e la regola assegna la categoria scelta nella riga. Annullare non lascia niente a metà: la proposta resta in coda e i movimenti restano dov'erano. Quello che un'accettazione senza regola scrive è una decisione della persona, e le regole non la sovrascrivono: riempiono il vuoto, seguono i propri cambiamenti, e un movimento già deciso a mano non cambia categoria per una regola che ne assegna un'altra. Una regola che assegna la *stessa* categoria invece lo adotta — è quella che lo tiene, ed è quello che la sua riga conta — e togliere quella regola lo rimanda in coda: è ciò che rende la casella spenta una scelta, non un rinvio. Dal movimento aperto vale lo stesso: con la casella accesa, scegliere la categoria apre il dialogo della regola — testo precompilato dal merchant, condizioni e azione modificabili, e l'elenco dei movimenti che prenderebbe — e il movimento prende la categoria solo quando la regola si salva; chiudere il dialogo non scrive niente.

**Categorie e regole sono una sezione sola.** Ciò che una categoria è e ciò che ci finisce sono la stessa decisione vista dai due capi, e stanno in un elenco solo: una riga per categoria con nome, quanti movimenti tiene e i due flag che le metriche leggono — spesa rara, irrinunciabile — scritti in chiaro quando sono accesi. Una categoria si apre e dentro ci sono i flag da cambiare, i testi che le assegnano e la riga che ne scrive uno: una regola assegna la categoria sotto cui sta, quindi non c'è niente da scegliere. In cima stanno solo la ricerca e i pulsanti per creare; cercare apre i gruppi che hanno trovato qualcosa, e una categoria la cui regola si corregge si sposta da sola. Una categoria si crea qui e dalla tendina con cui una proposta si corregge: non categorizza niente da sola, è il posto dove i movimenti possono finire. Si rinomina dalla sua riga: movimenti, regole e proposte la seguono, perché un nome che inganna vale quanto una categoria sbagliata — *Rimborsi* teneva quasi solo pagamenti in uscita verso altre persone. Non si rinomina con il nome di un altro conto o di un'altra categoria, e la categoria della coda tiene il suo. Il significato dei flag e delle regole sta nella **Guida**, non nella pagina.

**Una regola è un testo, o un'espressione.** Scritta fra barre — `/amazon (eu|payments)/` — la regola è un'espressione regolare: una sola regola per la famiglia che la banca scrive in troppi modi per elencarli. L'espressione vede lo stesso testo che vedono le regole — spazi collassati, maiuscole ignorate — perché una parola e un'espressione devono descrivere gli stessi movimenti. Il tipo di una regola sta nel suo pattern, non in una colonna: quel che si è scritto è quel che si rilegge, nell'elenco come nella rimozione. Un'espressione che non compila si rifiuta quando la si scrive — l'API risponde 422 con il motivo, e la riga in fondo al gruppo lo mostra — perché una regola che non potrà mai combaciare non deve arrivare al ledger. Dove due pattern combaciano vince il più lungo — la più stretta — che sia un testo o un'espressione: un'espressione scritta per nominare una famiglia è più lunga delle parole che sostituisce e ne prende i movimenti, una più larga non ruba niente a un testo più stretto che combacia ancora. Una barra sola e `//` restano testo, così un pattern che contiene una barra non diventa un'espressione per sbaglio.

**Una regola fa una cosa, a certe condizioni.** Oltre al testo, una regola si restringe a un conto e a un intervallo di importi — letti senza segno, perché una persona dice «fra 5 e 10 euro» — e a parità di testo vince quella con più condizioni, che è l'affermazione più stretta. Lo stesso testo con le stesse condizioni è una regola sola. Quello che segue è una di quattro azioni: assegnare una categoria, **cancellare** il movimento, **registrarlo come giroconto** verso una destinazione, **mettere un tag**. Dove più regole combaciano, cancellare vince su giroconto e giroconto su categoria: un movimento che non c'è non ha categoria, e un giroconto non è spesa da categorizzare.

- *Cancellare.* Prima di salvarla, la regola mostra quanti e quali movimenti prenderebbe — l'elenco lo calcola il backend, come ogni confronto fra regole e movimenti — e il pulsante che la salva dice quanti ne cancella. Salvata, li porta nel cestino del loro conto, come una cancellazione a mano; a ogni sync quelli nuovi che combaciano ci finiscono da soli, e il tombstone tiene fuori quelli già tolti. Finché la regola c'è un movimento che prende non si ripristina — tornerebbe nel cestino al sync dopo, e un ripristino che si annulla da solo non è un ripristino — e la risposta nomina la regola; togliere la regola lascia nel cestino quello che ha preso, ora ripristinabile. La verifica della sezione 5.4 conta queste cancellazioni come le altre: una differenza che spiegano è spiegata. Un conto con la flag di reimport accesa riporterebbe i movimenti a ogni sync e la regola li ritoglierebbe: vince la regola.
- *Giroconto.* La destinazione è un conto virtuale, come per le dichiarazioni `passthrough` di `accounts.json`, che restano dove sono: il movimento esce dalle spese, dalle entrate e dalla coda, e resta registrato. Una regola tolta rimanda in coda i movimenti che aveva registrato, dove le regole di categoria li ritrovano. Una destinazione non può essere una categoria, né un conto collegato a una banca: quello riporta da sé l'altra gamba, e l'abbinamento della sezione 5.3 la trova.
- *Giroconto verso un conto creato a mano.* Un conto che nessuna banca espone — il conto deposito di Revolut, che Enable Banking non mostra — non ha movimenti da abbinare, ma è un conto vero con un saldo vero. La regola allora scrive su quel conto il movimento opposto (stesso giorno, stessa descrizione, importo di segno contrario) e collega i due come giroconto confermato: escono da spese, entrate e coda come ogni coppia, e il conto ha i suoi movimenti. Il movimento opposto si scrive quando la banca contabilizza quello vero — un `PDNG` si riscrive al `BOOK` — e appartiene alla regola: non si cancella né si scollega da solo (si cambia la regola), sparisce con il movimento che rispecchia, e togliere o cambiare la regola lo toglie e rimanda in coda il movimento. Eliminare il conto toglie anche le regole che vi puntano. Su un conto così non si importa un estratto: i suoi movimenti sono quelli della regola, e l'estratto li conterebbe due volte.
- *Categoria.* Come sempre: riempie il vuoto, segue i propri cambiamenti, non sovrascrive una decisione presa a mano.
- *Tag.* Mette un tag (sezione 5.13) a ogni movimento che combacia, compresi split e giroconti. Non compete con le altre azioni: si somma, quindi una regola di categoria e una di tag sullo stesso testo valgono insieme, e tutte le regole di tag che combaciano mettono il loro. Togliere la regola toglie il tag dai movimenti dove l'aveva messo lei; un tag messo a mano resta.

**Anche un accredito va chiarito.** Finché nessuno decide, un accredito senza categoria non abbassa nessuna spesa e nei grafici conta come entrata. Il blocco *Accrediti da chiarire* di **Da confermare**, separato dalla lista delle uscite e fuori dai suoi filtri, mostra quelli contabilizzati dalla data di `AMONHEN_CREDITS_REVIEW_FROM` in poi, esclusi giroconti e split. Sul NAS è il 1° agosto 2025, cioè tutta la storia: un accredito vecchio lasciato senza categoria falsa i grafici quanto uno nuovo. Il blocco mostra i più recenti, e gli altri arrivano man mano che si decidono. Da ogni accredito si sceglie il tipo — entrata, rimborso o contributo alle spese (sezione 5.6) — e poi la categoria fra quelle di quel tipo; un tipo con una categoria sola non chiede altro. Per un rimborso la categoria è quella della spesa. La riga aperta porta allo stesso foglio di ogni movimento, per ciò che i tre tipi non dicono: un giroconto, una nota, una cancellazione. Un accredito che si ripete si risolve con una regola, non a uno a uno, ed è così che restano fuori gli interessi giornalieri del conto deposito: una regola di categoria verso una categoria *Entrata*, che non cambia nessuna cifra perché lì erano già entrate. Una categoria decisa fa uscire l'accredito dal blocco, anche quando è sbagliata; si ritrova in **Movimenti** filtrando per categoria, senza una vista apposta. Il numero sulla voce **Da confermare** conta anche questi accrediti: tolti gli interessi sono pochi, e uno che non si vede dalla barra non riceve risposta.

Ogni categoria può avere una descrizione, scritta nella sua riga: dice di cosa si tratta, a chi legge fra un anno, e non cambia nessun calcolo.

Le regole che non assegnano una categoria — cancellano, registrano un giroconto o mettono un tag — non stanno sotto una categoria: la sezione le elenca a parte, in due blocchi chiusi di base sotto le categorie (*Tag* e *Altre regole*); un pulsante *Nuova regola* apre lo stesso dialogo da zero, e ogni regola si apre per cambiarla.

### 5.6 Metriche esposte

**La spesa è al netto dei rimborsi.** Un accredito in una categoria non marcata *Entrata* è un rimborso: abbassa quella categoria nel mese in cui arriva, e con i suoi tag vale anche per spesa rara e irrinunciabile. Non entra nelle entrate. Un accredito in una categoria *Entrata* è un'entrata, e uno senza categoria non conta come rimborso finché nessuno lo decide: è il blocco *Accrediti da chiarire* a chiederlo (sezione 5.5). Un mese o una categoria possono risultare negativi. Le anomalie guardano solo le uscite.

**Il contributo alle spese abbassa il totale, non una categoria.** Il denaro che entra per coprire le spese in generale — i versamenti sul conto cointestato, che riguardano tutto ciò che quel conto paga — si mette in una categoria marcata *Contributo alle spese*. Non è un'entrata e non è il rimborso di niente: un rimborso abbassa la sua categoria, un contributo copre tutte le spese del conto su cui arriva. Spesa tipica, spesa attesa, mesi di autonomia, irrinunciabile, tagliabile e riserva per spese rare ne sono al netto: in ogni mese tutto ciò che quel conto ha pagato, spese rare comprese, scende della stessa percentuale, quanto ha ricevuto sul quanto ha speso, al massimo tutto, e gli altri conti restano interi. Una percentuale sola è ciò che fa contare il denaro una volta: ridurre le spese rare con la quota calcolata sulle sole spese normali toglierebbe due volte gli stessi euro. Nel mese, *Questo mese* e il suo solito restano lordi, così il confronto non dipende dal giorno in cui il denaro arriva, e una riga sotto dice i contributi e quanto resta a carico. Il segno sta da solo: accenderlo spegne *Spesa rara*, *Irrinunciabile* ed *Entrata*. Nei grafici il contributo non è un'entrata e le uscite ne sono al netto, come per un rimborso. I budget di categoria non lo contano. L'autonomia presume che i contributi continuino anche se si fermano le entrate di chi usa l'app.

Solo queste, in ordine di priorità; la lettura di ogni categoria sta nella sezione 5.15. Ognuna si chiama con parole che dicono cosa misura, nell'app come qui; fra parentesi il nome con cui la conosce il codice.

- **Spesa mensile tipica** (*burn ricorrente*): quanto si spende di solito in un mese, senza le spese rare — la mediana mobile a 6 mesi delle spese non rare. Una spesa è **rara** se la sua categoria è segnata come rara o se il movimento ha un tag segnato come raro: la definizione è una sola, nel codice come qui, e ogni metrica la legge da lì.
- **Riserva per spese rare** (*accantonamento episodico*): le spese rare degli ultimi 24 mesi divise per 24, cioè quanto mettere da parte ogni mese per quando tornano. Gli eventi rari non vanno rimossi, vanno modellati come processo separato con frequenza propria. Si divide sempre per 24 anche con meno storia, così una storia corta non la gonfia: finché la storia è più corta, la riserva è sottostimata e la **Guida** lo dice.
- **Spesa mensile attesa** (*burn atteso*) = spesa mensile tipica + riserva per spese rare: quanto costa davvero un mese.
- **Mesi di autonomia** (*runway*) = liquidità / spesa mensile attesa: per quanti mesi si va avanti se le entrate si fermano. La rata del mutuo non è più una voce fissa del denominatore: un pagamento del mutuo è un movimento come gli altri, e se deve contare sta in una categoria.
- **Spesa irrinunciabile e spesa tagliabile** (*quota incomprimibile e discrezionale*): la spesa tipica divisa fra quella irrinunciabile — per categoria o per tag, con la stessa regola di rara — e il resto, cioè quanto sarebbe tagliabile se servisse. Un movimento raro e irrinunciabile conta come raro, una volta sola.

Il cruscotto risponde a due domande, in quest'ordine e senza scorrere: **Questo mese** (quanto è uscito finora contro quanto esce di solito a questo punto del mese: la mediana dei 6 mesi completi precedenti alla stessa data, senza spese rare, che hanno una riga a parte) e **Dove sono finiti** (le categorie con una spesa nel mese, dalla più alta, ognuna con la distanza dal suo solito scritta in parole, e ognuna apre i suoi movimenti). Sotto stanno liquidità e mesi di autonomia, le anomalie, il periodo, la ciambella delle spese per categoria e, su PC, altri due grafici: entrate e uscite, e la curva della liquidità. Le altre cifre della sezione 5.6 sono sotto *Dettagli*. I grafici non fanno aritmetica: ogni serie si calcola nel backend. I filtri (conti, categoria, tag) e il periodo pesano diversamente: il **periodo** decide cosa mostrano i grafici, si sceglie fra *Questo mese*, 3, 6, 12 e 24 mesi o due date a scelta, e conta i giorni scelti anche quando taglia un mese; i **conti** restringono tutto ciò che è di conto; **categoria e tag** restringono solo le spese. Un filtro si applica nel backend, mai nel browser.

Le metriche non seguono il periodo: le loro finestre di 6 e 24 mesi sono la definizione della metrica, non una vista.

**Movimenti** si legge per mese e, con *Periodo*, fra due date a scelta, e si stringe per importo: un minimo e un massimo senza segno, estremi compresi, come le condizioni di una regola (sezione 5.5). L'importo è quello del movimento intero, anche quando è diviso fra più categorie. Il budget resta per mese: il tetto è di un mese, e un periodo qualunque non avrebbe un tetto con cui confrontarsi (sezione 5.12).

Conti e budget si gestiscono da una sezione dell'app, non dal cruscotto: l'elenco dei conti con nome, saldo in evidenza ed esito della verifica; dietro *Dettagli* sta tutto il resto: la dichiarazione di un saldo letto dalla banca, l'allineamento del saldo iniziale perché l'invariante della sezione 5.4 torni a valere, la sincronizzazione di un periodo, i flag e l'eliminazione. Un conto reale si crea anche a mano (il broker, o una banca non collegata). Eliminare un conto toglie i suoi movimenti, il suo cestino, i saldi dichiarati e le regole ristrette a lui, e se è collegato a una banca lo toglie anche da `accounts.json`, altrimenti il sync successivo lo ricreerebbe con tutta la sua storia; l'altra gamba di un giroconto non si cancella — quel denaro è davvero entrato o uscito da un altro conto — e torna in coda. Non c'è cestino per un conto: si conferma scrivendone il nome, e per tornare indietro serve uno snapshot (sezione 5.11). Il budget di ogni categoria ha una sezione sua (sezione 5.12). I flag delle categorie e la loro creazione stanno invece nella sezione che le categorie le definisce insieme alle regole che le riempiono (sezione 5.5).

Il PC non è un telefono largo. Sopra i 1024 px la colonna si prende lo spazio della finestra, le sezioni salgono in un rail laterale, i movimenti sono una tabella con l'intestazione fissa, la coda mostra l'elenco delle proposte accanto al dettaglio di quella scelta, così si decide senza aprire niente, e le schede si aprono da destra, così quello che si stava guardando resta visibile. Ciò che è stretto per natura resta stretto: i paragrafi tengono le 72 battute e il setup, che è un modulo, resta una colonna. Sotto i 1024 px l'app è quella del telefono.

Esplicitamente escluse perché decorative: patrimonio a frequenza giornaliera, medie su singolo mese, rendimenti calcolati internamente.

### 5.7 Anomalie

Detection statistica deterministica, non LLM: z-score robusto su MAD per categoria, oppure soglia sul p95 storico della categoria. Deve essere spiegabile con una frase. Una spesa sotto i 100 €, un cambio valuta o una spesa rara non è un'anomalia: la prima è rumore, il secondo non è una spesa, la terza è già nota. La frase parla italiano — quanto, di solito quanto, quante volte tanto — e la statistica resta nel calcolo. Il cruscotto mostra le tre più grandi, le altre a richiesta.

### 5.8 Patrimonio

Patrimonio **osservato**, non ricostruito: `account_balances` tiene ciò che la banca dichiara per un conto in una data, e lo scrivono il sync (per ogni conto raggiungibile), `balances` su richiesta e `anchor` per una dichiarazione a mano. La serie somma l'ultimo saldo noto di ogni conto reale tracciato, e un conto conta dalla sua prima osservazione: la curva comincia dove cominciano i dati, senza back-fill né interpolazioni. Liquidità, mesi di autonomia e curva contano solo i conti reali tracciati, e tutti i conti reali sono denaro disponibile: il portafoglio non è in nessuno di essi, quindi patrimonio e liquidità sono la stessa cifra e sullo schermo si chiama *Liquidità*.

**Un conto può valere quello che dicono i suoi movimenti.** Un conto creato a mano con la flag *saldo dai movimenti* — il conto deposito alimentato dai giroconti che una regola gli scrive (sezione 5.5) — non ha una banca che ne dichiari il saldo: il patrimonio lo conta, a ogni data della serie, per il saldo calcolato a quella data (saldo iniziale più i movimenti), dalla sua data iniziale in poi, e i saldi per conto lo mostrano a oggi. Le date della serie restano quelle osservate. Un saldo dichiarato su quel conto non è un punto della serie ma la verifica della sezione 5.4: la differenza che si accumula è quello che i movimenti non vedono, come gli interessi maturati dentro il deposito, e si corregge con un movimento a mano, così l'interesse resta un'entrata invece di sparire nel saldo iniziale. Il saldo iniziale si ricava dal saldo di oggi togliendo i giroconti già nel ledger, quindi la storia del conto parte dal primo giroconto. La liquidità usava già il saldo calcolato per ogni conto.

**Del broker si tiene la liquidità, non il portafoglio.** Il conto del broker è un conto reale creato a mano, segnato come tale, e tiene solo il denaro non investito: i bonifici lo aggiornano da soli come altra metà dei giroconti. Il portafoglio non entra nel ledger né nella liquidità: non è liquido e varia. Le sue posizioni e il loro valore si dichiarano a mano nella pianificazione (sezione 5.16), con la frequenza propria. Quello che i movimenti non vedono — acquisti, vendite, rendimenti — si riallinea dichiarando la liquidità letta dal broker (*Aggiorna la liquidità* in **Conti**): la differenza dal saldo calcolato a quella data è scritta come un movimento verso il conto virtuale *Investimenti*, e la cifra diventa il saldo dichiarato, così la verifica della sezione 5.4 torna. Non è un'entrata né una spesa (ha un posting virtuale), non è candidata a un giroconto e le regole non la toccano; una seconda dichiarazione sulla stessa data sostituisce la prima. I versamenti che comprano subito — il PAC — vanno direttamente su *Investimenti* con una regola di giroconto. Il saldo di *Investimenti* è quindi il netto versato e nient'altro, non un valore di mercato, e si legge fra i conti virtuali. Nessuna cifra fiscale esce dall'app: per il valore di fine anno e la giacenza fanno fede i documenti del broker.

Motivazione della separazione: spese e patrimonio sono processi con frequenza di campionamento e struttura del rumore diverse di ordini di grandezza. Unirli fa entrare la volatilità di mercato nelle metriche di spesa.

Gli estratti PDF del broker non si leggono: leggerli ogni trimestre era più lavoro di quanto valga una curva del patrimonio.

### 5.9 Assistente *(rimossa, novembre 2026)*

C'è stata una sezione che leggeva in prosa i numeri già calcolati: non è stata usata, nessuna lettura è mai stata registrata sul NAS, e per le domande che prometteva mancavano i dati. La sua aritmetica era vietata, quindi poteva dire al massimo ciò che le schermate dicono già. Quello che serviva davvero — quanto prende di solito una categoria — sta nella sezione 5.15. Il numero resta, perché altre sezioni e la storia lo citano; il testo com'era è in `docs/storia-desiderata.md`. Il modello resta per una cosa sola: proporre la categoria dei merchant mai visti (sezione 5.5).

### 5.10 Primo setup guidato *(costruita)*

Il primo avvio era una decina di passi a mano e nessuno di essi stava nel prodotto: creare `accounts.json` da un template, mettere la chiave privata accanto, far combaciare tre indirizzi (quello che il browser raggiunge, `redirect_url` nel file, la callback registrata nel dashboard), aprire a mano `/connect` scrivendo il nome dell'ASPSP a memoria, poi editare lo stesso file per tenere solo i conti voluti fra i quattro che una banca risponde, poi sincronizzare, e infine dichiarare un saldo o il conto restava `non verificato` per la sezione 5.4. L'app conosce già il proprio indirizzo, la lista degli istituti che Enable Banking accetta e i conti che un'autorizzazione ha appena scritto: quasi tutti quei passi chiedevano a una persona qualcosa che il sistema sa.

**Il gate è la prima schermata, non un manuale.** Quando la configurazione manca, l'app apre il setup al posto delle sezioni, al primo passo che ha qualcosa da chiedere; a sistema configurato la stessa schermata resta raggiungibile dal menu, perché un consenso PSD2 scade e una banca si aggiunge, e il passo utile in quel momento è quello dei conti. Il wizard non è una modalità che si chiude per sempre: è dove la configurazione si guarda e si cambia.

**Cinque passi.**

1. *Credenziali.* Application ID, chiave privata incollata, indirizzo di ritorno, nome dell'intestatario. L'indirizzo lo propone l'app dalla propria origine — è quello che il browser raggiunge, quindi è quello giusto per costruzione — e la chiave si carica subito: una che non è una chiave privata si rifiuta lì, dove è stata incollata, invece di diventare un sync che fallisce domani. Resta a mano **una** cosa, ed è l'unica che il sistema non può scrivere al posto tuo: registrare quell'indirizzo nel dashboard Enable Banking, carattere per carattere. La schermata mostra la stringa esatta, e il rifiuto della banca (`Redirect URI not allowed`) torna verbatim.
2. *Banca.* Il nome dell'ASPSP deve combaciare con quello che Enable Banking conosce, e chiederlo a memoria era un modo per sbagliarlo: la lista arriva dall'API, filtrata per paese, e si sceglie da lì. L'autorizzazione si apre nella stessa scheda, perché è lì che il ritorno deve arrivare.
3. *Conti.* Una banca risponde con tutti i conti che l'autorizzazione copre — Fineco ne dà quattro — e prima si potavano editando il file a mano. Qui si tiene quello che serve, si dà a ciascuno il nome con cui il ledger lo conoscerà e la data da cui importarne la storia. Il nome è la chiave del ledger: un nome che un'altra voce già usa si rifiuta, invece di scoprire nel ledger che due conti erano uno.
4. *Primo sync.* Il pulsante chiede i movimenti adesso e risponde per conto con quello che ha scritto, come quello della barra in alto (sezione 5.4 compresa): il primo sync non è un passaggio a vuoto, è la prima volta che si vede cosa è arrivato.
5. *Saldi e verifica.* Un conto senza saldo dichiarato è `non verificato` (sezione 5.4), e un ledger che nessuno ha confrontato con la banca non è ancora affidabile: qui si dichiara il saldo letto dall'istituto, si allinea l'apertura e si legge l'esito per conto. Il setup si può chiudere con un conto ancora non verificato, ma lo dice.

**Chi scrive la configurazione.** `accounts.json` ha due scrittori, e la scrittura è la stessa: il callback OAuth aggiunge o rinfresca le voci delle autorizzazioni, il setup scrive le credenziali e cura le voci; le chiavi che il sistema non conosce sopravvivono a entrambi. La chiave privata si scrive accanto al file, dove `pem_path` la indica, e **non torna mai indietro**: l'API dice se c'è e se si carica, non la restituisce, non la registra. `load_config` resta severo — chi legge la configurazione per lavorare continua a fallire forte — mentre lo stato del setup si legge anche da un documento assente, perché "non c'è ancora niente" e "questo server è rotto" sono due cose diverse.

**Un avvio a freddo deve poter partire.** Un container appena creato non ha né `accounts.json` né `private.pem`, quindi compose monta la cartella di configurazione e non i due file: è la differenza tra un primo avvio possibile e un `up` che pretende che il setup sia già stato fatto da riga di comando. Per la stessa ragione `/connect` e `/callback` con la configurazione incompleta dicono cosa manca invece di rispondere 500, e il ritorno dal login è un 303 dentro l'app invece del JSON grezzo che nessuno leggeva: la schermata che ha iniziato l'autorizzazione è quella che deve dire cosa è arrivato.

Restano fuori, ciascuna per una ragione diversa: la configurazione del modello (è configurazione d'ambiente, sezione 5.5, e l'app in container non scrive l'`.env` dell'host) e le dichiarazioni `passthrough` (sezione 5.3: si capiscono dai testi che la banca stampa, che al primo avvio non ci sono ancora).

*Fatto quando*: davanti a un'installazione nuova, dall'app e senza terminale, si arriva a un conto collegato, sincronizzato e verificato dalla sezione 5.4, e l'unico passo che resta a una persona è registrare l'indirizzo di ritorno nel dashboard della banca.

### 5.11 Backup e ripristino *(costruita)*

Il ledger vive in un volume del container e la configurazione in una cartella montata, e nessuno dei due era copiato da niente. Il rischio che conta non è il disco rotto: è il sync che riscrive un periodo, un conto tolto per sbaglio, un `DELETE` digitato male. Senza una copia l'unica risposta è rifare il backfill e rimettere a mano le decisioni prese in mesi di coda.

**Cosa si copia.** Il database del ledger e la configurazione che lo rende ripristinabile — `accounts.json` e la chiave privata che `pem_path` nomina — perché un ledger senza le sessioni che lo alimentano non si rilegge da nessuna banca da solo. Non l'`.env`: quella è configurazione della macchina, non del ledger, e una copia in più di un file con la chiave del modello è un rischio senza contropartita.

**Come.** Una cartella per snapshot, nominata con il momento in cui è stato preso (`2026-09-26T101500Z`), che contiene il database, i file di configurazione e un `manifest.json` con l'ora, la provenienza, lo sha256 di quello che ha scritto, i conteggi delle righe e l'elenco di cosa ha copiato. Il database si copia con l'API di backup di SQLite e non leggendo il file: il server può stare scrivendo, e una copia presa in quel momento può risultare strappata — una copia che sembra un backup e contiene mezzo movimento è peggio di nessun backup. La scrittura passa da una cartella temporanea e prende il nome definitivo solo alla fine, quindi un giro interrotto non lascia qualcosa che sembra uno snapshot buono, e una cartella senza nome non conta nemmeno per la ritenzione. La ritenzione tiene gli N più recenti (quattordici per impostazione predefinita) e non tocca niente quando è a zero: senza, la cartella cresce di un database alla volta per sempre.

**Dove, e cosa non è ancora.** Sul NAS la copia la fa il cron, dentro il container, scrivendo nella cartella `backups/` che l'host monta. Uno snapshot sul disco del NAS **non è ancora un backup**: sta sugli stessi dischi del ledger. Portarlo fuori è compito dello strumento di backup del NAS puntato su quella cartella, o di un `docker compose cp` a mano. Il prodotto scrive la copia e la rende leggibile; la ridondanza è dell'ambiente, e non si finge.

**Come si torna indietro.** Si ferma l'app — fermarla è ciò che chiude il database, quindi mentre la copia atterra non sta scrivendo nessuno — si copia `amonhen.db` dallo snapshot al posto di quello vivo, si rimette la proprietà dell'utente del container e si riaccende. Un ripristino mai provato non è un ripristino: per questo la prova locale qui sotto include il giro intero, snapshot, guasto e ritorno, invece di fermarsi al comando che scrive la cartella.

*Fatto quando*: dopo un errore che ha rovinato il ledger si torna allo stato di ieri sera con la procedura di ripristino, senza risincronizzare e senza rimettere a mano le decisioni; e la prova locale dimostra quel giro — snapshots, guasto e ritorno — prima che serva davvero, non solo che i comandi esistano.

### 5.12 Pianificazione del budget *(costruita)*

Un budget per categoria dice quanto si vuole spendere in un mese, non in cosa. La pianificazione è lo stesso budget visto più da vicino: dentro il tetto di una categoria si scrivono le spese che si sa già di dover fare, e la sezione dice quanta parte del tetto hanno già preso e se ci stanno. Non è una previsione (sezione 3): il sistema non stima entrate né spese, mostra ciò che una persona ha scritto accanto a ciò che è già uscito.

**Il tetto è per mese, con un default.** Ogni categoria ha un importo di default che vale da un mese in avanti: cambiarlo guardando novembre lo cambia da novembre in poi e lascia ottobre con quello che aveva, perché un budget riscritto all'indietro cancella la storia che si voleva tenere. Togliere il default è la stessa scrittura, con importo vuoto. Un mese può sovrascrivere il default per sé solo — dicembre con più regali — e togliere la sovrascrittura lo riporta al default. I budget scritti prima di questa versione diventano default validi da sempre.

**Le voci stanno dentro il tetto.** Una voce appartiene a una categoria e a un mese, e porta descrizione, importo, una data facoltativa dentro quel mese, una priorità e una nota. Una categoria senza voci è il budget di prima, senza niente in più; con le voci il tetto si legge in tre parti: quanto è pianificato, quanto resta libero, quanto è già stato speso. Se le voci superano il tetto la categoria lo segnala, e il tetto non si alza da solo: è una decisione, e la prende la persona.

**La priorità ordina, non taglia.** Tre livelli — essenziale, importante, rimandabile. Dentro una categoria le voci si leggono in quell'ordine, a parità per data (le voci senza data in fondo) e poi per ordine di inserimento; scorrendole così, una voce *ci sta* finché la somma di quelle prima più lei non supera il tetto. Il calcolo è del backend, come ogni somma (sezione 5.6). Il sistema non propone cosa togliere né cosa spostare: è l'ottimizzazione che la sezione 3 esclude.

**Una voce nasce in tre modi, e resta modificabile.** Scritta da zero; copiata da un movimento passato — descrizione, importo senza segno, categoria, e il giorno riportato nel mese che si sta pianificando —, con il modulo aperto sui campi copiati prima che qualcosa venga salvato; oppure copiando le voci di una categoria dal mese precedente, con le date spostate nello stesso modo. La copia è una copia: modificare la voce non tocca il movimento né il mese da cui viene, e copiare due volte non duplica una voce con la stessa descrizione e lo stesso importo. Una voce si sposta di mese o di categoria dal suo modulo.

**Lo speso resta per categoria.** Una voce non sa se è stata spesa: lo speso è quello di sempre, la spesa contabilizzata della categoria nel mese, al netto dei rimborsi, ed è il confronto con il tetto che conta. Collegare una voce al movimento che la realizza è un lavoro che si fa solo se lo storico lo chiede.

**Lo storico è il mese.** Ogni mese si riapre con il suo tetto, le sue voci e il suo speso; niente si blocca, perché un mese passato si corregge come uno presente.

*Fatto quando*: si pianifica il mese prossimo da una sezione dell'app — tetto, voci e priorità — e il mese prima resta leggibile com'era, anche dopo aver cambiato il default.

### 5.13 Tag *(costruita)*

Un tag è un'etichetta libera su un movimento, che tiene la sua categoria: Euronics resta in *Casa* e porta *Elettrodomestici*. Un movimento può averne più d'uno, e si mettono a mano — sul movimento o su una selezione — o con una regola (sezione 5.5). Un tag può portare gli stessi due flag di una categoria, *Spesa rara* e *Irrinunciabile*: non sono un secondo concetto, è la stessa domanda posta al movimento invece che alla categoria, e ogni calcolo legge un predicato solo. Se esiste un tag raro, il movimento è una spesa rara. Un tag vale per tutto il movimento, split compresi. Un tag filtra **Movimenti** e i grafici del cruscotto, e come una nota sopravvive alla cancellazione e al ripristino. Non scrive nessuna categoria e non cambia cosa ha detto la banca.

### 5.14 Guida *(costruita)*

Una sezione sotto *Gestione* spiega i concetti, una scheda per concetto — il mese e il solito, mediana e media, liquidità, spesa tipica, spesa rara, rimborso, contributo alle spese, riserva, spesa attesa, autonomia, irrinunciabile e tagliabile, giroconto, conto virtuale, regola, tag, anomalia, verifica del saldo — con cosa significa, come si calcola e cosa succede cambiandolo, e dove serve le cifre attuali come esempio. Un *?* dalle altre pagine porta alla scheda giusta. È il solo posto dove le pagine spiegano: un paragrafo che spiega un concetto in una pagina si sposta qui, e una modifica a un calcolo aggiorna la scheda nello stesso cambiamento, come questa specifica.

### 5.15 Statistiche *(costruita)*

Una sezione sotto *Gestione* legge ogni categoria sugli ultimi 6, 12 o 24 mesi completi: mediana, media, minimo e massimo, in quanti mesi ha speso, e aprendola i suoi mesi uno per uno. Una riga in cima dice lo stesso del totale, che ha i suoi mesi: le mediane delle categorie non sommano alla sua. Il mese in corso non c'è, e un mese senza spese vale zero: è ciò che separa la mediana dalla media in una categoria che spende ogni tanto, e quella distanza è la cosa da leggere. La mediana dice il mese normale, la media quanto costa la categoria nel lungo periodo. Quattro grafici disegnano le stesse cifre: il totale mese per mese contro la sua mediana e la sua media, di cosa è fatto ogni mese (le cinque categorie più care a colori, le altre insieme), mediana e media categoria per categoria, e una mappa di calore che dice in quali mesi spende ciascuna rispetto al suo mese più caro. Il client li disegna e basta: nessuna somma nuova.

Il conto è quello del budget: al netto dei rimborsi, non dei contributi, con le spese rare dentro, perché la decisione che queste cifre servono è quale tetto mettere. Per la stessa ragione ogni riga del **Budget** dice *di solito*: la mediana dei 6 mesi completi prima del mese che si guarda, così un mese riaperto mostra il solito che aveva allora. Non è una previsione (sezione 3): sono cifre del passato, e il tetto lo decide la persona. Ogni cifra si calcola nel backend (sezione 5.6).

*Fatto quando*: davanti a un tetto da scegliere la cifra è già sulla riga, e la distanza fra mediana e media dice se una categoria va a strappi.

### 5.16 Pianificazione a lungo termine *(da costruire)*

Il resto del sistema dice com'è andata. Questa sezione serve a una decisione che si prende più volte l'anno e cambia quando cambia un obiettivo: quanto mettere da parte, e dove — liquidità, fondo pensione, PAC. Senza un punto d'arrivo la ripartizione non ha un criterio, e la risposta giusta per un acquisto fra tre anni è sbagliata per la pensione fra trenta.

**Gli obiettivi dicono dove si va.** Un obiettivo ha un nome, una cifra in euro di oggi, una data e quanto deve restare raggiungibile: il cuscinetto si misura in mesi di spesa attesa (sezione 5.6) e deve essere liquido; un acquisto ha una data e non può stare in uno strumento bloccato fino a quella data; la pensione, o l'età da cui si vuole poter scegliere se lavorare, è un reddito annuo da un'età. Gli obiettivi si scrivono a mano e si cambiano: ognuno porta la data da cui vale, come un default di budget (sezione 5.12), così un piano riaperto mostra gli obiettivi che aveva allora.

**Il profilo tiene i fatti che il ledger non vede.** Il ledger vede lo stipendio netto, non quello che lo produce: lordo e numero di mensilità, la base su cui si calcola il versamento al fondo, la percentuale propria e quella del datore, dove va il TFR, l'età. Ogni fatto vale da una data in poi. La base del versamento si scrive a parte perché non è il lordo: nelle buste paga del 2025–2026 la percentuale si calcola su una base contrattuale che non è salita quando a luglio 2026 è salito il lordo, quindi un versamento dedotto dal lordo sarebbe stato sbagliato. Quanto si può mettere da parte lo dice invece il ledger: entrate meno spese sui 12 mesi completi, così le mensilità aggiuntive e le rendite trimestrali pesano una volta, con il margine dei mesi ordinari scritto accanto, perché il denaro che arriva tre volte l'anno non si versa ogni mese.

**I parametri fiscali sono dati, non codice.** Una tabella per anno — scaglioni IRPEF, addizionali, tetto di deducibilità della previdenza complementare (5.300 € dal 2026, che comprende il contributo del datore e non il TFR), aliquota sulle prestazioni del fondo (15%, che scende di 0,30 punti per ogni anno oltre il quindicesimo fino al 9%), tassazione dei rendimenti del fondo, 26% sui guadagni degli ETF, bollo — e ogni valore porta la sua fonte. La legge di bilancio li cambia ogni anno, e una regola rimasta indietro dà una cifra sbagliata con l'aria di una giusta: per questo si aggiornano a mano, a gennaio, e un anno senza parametri non si copre in silenzio con quelli dell'anno prima. Il calcolo usa l'ultimo anno disponibile, lo scrive accanto a ogni cifra, e la sezione dice che l'anno in corso manca. I parametri non li scrive un modello (sezione 8).

**Fondo pensione contro PAC.** È la domanda per cui la sezione esiste. Per un euro in più versato nel fondo il calcolo mette in fila: la deduzione all'aliquota marginale dell'anno, il contributo del datore se dipende da quanto si versa, lo spazio che resta sotto il tetto (oltre il tetto la deduzione non c'è più e il confronto cambia), la tassazione all'uscita, e il fatto che quel denaro resta bloccato salvo le anticipazioni. Lo stesso euro in un ETF paga il 26% sul guadagno quando si vende e il bollo ogni anno, ma resta disponibile. Il risultato è per obiettivo e orizzonte: quanto vale a scadenza, netto, in ciascuno scenario, e quanto resta raggiungibile prima. Il sistema mostra due ripartizioni una accanto all'altra; quale scegliere lo decide la persona (sezione 3).

**Il portafoglio si dichiara.** Le posizioni — strumento, ISIN, quote — e il loro valore a una data si scrivono a mano, come la liquidità del broker (sezione 5.8); il valore del fondo pensione si prende dal suo estratto. Il versato netto c'è già: è il saldo del conto virtuale *Investimenti*. Il portafoglio si legge come valore contro versato e come ripartizione fra strumenti e orizzonti, non come rendimento (sezione 3), e non entra in liquidità né in mesi di autonomia. Nessun prezzo si chiede a un servizio esterno.

**Le proiezioni sono per scenari.** Ogni obiettivo si proietta in tre scenari — prudente, centrale, favorevole — con il rendimento reale e l'inflazione di ciascuno scritti accanto al risultato, in euro di oggi. La proiezione dice se l'obiettivo, al ritmo di versamento attuale, si raggiunge e quanto servirebbe al mese per raggiungerlo; quando i tre scenari divergono molto, è quella distanza la cosa da leggere. Le ipotesi le scrive la persona, e il sistema non le stima dal passato.

**La revisione periodica sta fuori dall'app.** Ogni trimestre uno snapshot (sezione 5.11) e una lettura del piano e del portafoglio con un assistente, su cifre che l'app ha già calcolato. L'app non chiama un modello per questo, e piano e portafoglio non lasciano il NAS dall'app (sezioni 4 e 8). Ogni cifra si calcola nel backend (sezione 5.6), e i concetti nuovi — obiettivo, base del versamento, tetto di deducibilità, scenario — hanno la loro scheda nella **Guida** (sezione 5.14).

*Fatto quando*: davanti alla domanda "quanto verso nel fondo e quanto nel PAC l'anno prossimo" l'app mostra, per ogni obiettivo, le conseguenze di due ripartizioni con i parametri fiscali dell'anno e le ipotesi scritte, e dice se i parametri dell'anno mancano.

## 6. Modello dati minimo

```
accounts             (id, nome, tipo: reale|virtuale|categoria, istituto, iban, uid_esterno, valuta,
                      saldo_iniziale, data_iniziale, flag: spesa rara | irrinunciabile | investimento,
                      ripristina_cancellati, saldo_dai_movimenti)
transactions         (id, conto, data, importo, descrizione, stato BOOK|PDNG, external_id, content_hash,
                      origine psd2|import, payload_grezzo, controparte, conto_controparte, nota,
                      rispecchia — il movimento di cui è l'altra gamba scritta da una regola)
postings             (id, transaction_id, account_id, importo, note)
deleted_transactions (id, conto, chiave, data, importo, descrizione, stato, external_id, content_hash,
                      origine, payload_grezzo, controparte, conto_controparte, nota, cancellato_il,
                      ripristinato_il)
held_transactions    (id, conto, chiave, occorrenza, data, importo, descrizione, movimento,
                      riga_a_cui_somiglia, creato_il, decisione: pending | written | discarded)
transfer_links       (leg_a, leg_b, confidenza, metodo, confermato_da_umano: 1 confermato, 0 da rivedere, -1 rifiutato)
rules                (id, chiave, testo, azione: categoria | cancella | giroconto,
                      destinazione o categoria, conto?, importo minimo?, importo massimo?)
account_balances     (conto, data, saldo, origine)
budgets              (categoria, dal_mese, importo — vuoto toglie il default da quel mese, aggiornato_il)
budget_months        (categoria, mese, importo, aggiornato_il)
budget_items         (id, categoria, mese, descrizione, importo, data, priorità, nota, creato_il)
merchant_suggestions (merchant, categoria, origine, decisione: pending | accepted | dismissed)
settings             (chiave, valore)
```

Per la sezione 5.16, da costruire:

```
goals                (id, nome, importo in euro di oggi, data, liquidità richiesta, dal, al?)
profile_facts        (chiave, valore, dal — lordo, mensilità, base del versamento, percentuali, TFR, età)
tax_parameters       (anno, chiave, valore, fonte)
holdings             (id, strumento, isin?, orizzonte)
holding_values       (holding, data, quote, valore)
scenarios            (nome, rendimento reale, inflazione)
```

Vincolo di integrità: per ogni `transaction_id`, `SUM(postings.importo) = 0`.

**La nota di un movimento è locale, e nient'altro si scrive a mano.** Un movimento porta una
`notes` che la banca non manda e che nessun percorso di ingest tocca su una riga che esiste:
sopravvive alla promozione `PDNG`→`BOOK`, che riscrive data, descrizione e identificativo della
stessa riga, e alla riimportazione del periodo. L'unica scrittura che non viene da una persona è
il tombstone che restituisce a un movimento appena ricreato la nota che quello cancellato aveva,
nel reimport e nel ripristino. È l'unico campo del
movimento che una persona può modificare: importo, data e descrizione sono ciò che la banca ha
dichiarato, e la verifica della sezione 5.4 confronta proprio quella dichiarazione con il ledger.

Vincolo deliberato: `content_hash` **non** è unico. La stessa spesa può ripetersi identica nello stesso giorno, e il percorso di import ha bisogno che l'hash di base resti riutilizzabile.

## 7. Perimetro del sistema e riuso di bank-connector

Il sistema è **custom e autonomo**: possiede il proprio ledger, la propria pipeline di ingest e la propria interfaccia. Actual Budget non è una dipendenza.

Questo non significa riscrivere da zero l'integrazione PSD2. Il repo `bank-connector` contiene una implementazione dell'integrazione con Enable Banking che copre flusso OAuth, JWT RS256, paginazione e gestione dei rate limit, parsing del segno dell'importo da `credit_debit_indicator`, filtro dei self-transfer sul nome dell'intestatario, e riconciliazione pending → booked.

**Va però trattata come implementazione di riferimento, non come codice funzionante.** Non è in uso (la sincronizzazione verso Actual avviene oggi tramite il plugin nativo di Actual Budget) e il suo percorso di fetch non è verificato contro l'API attuale. Il valore riusabile sta nelle specificità del provider già comprese una volta, non nelle righe in sé.

**Conseguenza sull'ordine di lavoro**: la prima attività è uno script usa e getta che autentica, scarica e scrive su disco il JSON grezzo di lista conti e transazioni, senza parsing. Serve a due scopi: verificare che il percorso di fetch sia ancora valido, e produrre le fixture su cui poggeranno i test di parsing. Solo dopo quel dump si decide cosa del codice esistente sopravvive.

**Modalità di riuso: modulo interno, non servizio.** Il lavoro avviene su un branch dello stesso repo. Il confine tra il livello che parla con Enable Banking e il resto dell'applicazione è un confine tra moduli, non tra repository: il livello di fetch restituisce transazioni normalizzate e non sa nulla di dove finiscono.

Conseguenze da accettare consapevolmente:

- Il codice verso Actual (client actualpy, patch delle regole, `state.json` con `pending_map` riferita agli UUID di Actual, thread dello scheduler) esce dal branch subito. Non essendo in uso, non c'è nulla da preservare né da far coesistere. Lo stato di dedup si sposta nel database del sistema.
- Flask esce dal livello di integrazione: le route `/connect` e `/callback` diventano endpoint dell'applicazione, e il modulo espone solo le funzioni che costruiscono l'URL di autorizzazione e finalizzano la sessione.
- Le funzioni che Actual dava gratis vanno costruite: budget per categoria, editing degli split, viste mobile. Sono l'oggetto delle fasi successive.
- L'eventuale vincolo di licenza sulla logica di sync derivata da terzi segue il codice riusato, indipendentemente dal branch o dal repo in cui finisce.

**Repo**: branch sul repo esistente. La strumentazione di sviluppo (regole per gli agenti, backlog) va installata su `main` in un commit dedicato, prima di aprire il branch, così è disponibile anche ai branch successivi.

**Esito (settembre 2026).** La strumentazione è su `main` in un commit dedicato e il lavoro sta su un branch; il percorso Actual è uscito dal branch; il livello che parla con Enable Banking è un modulo interno (`providers/`), scritto contro le fixture anonimizzate della fase 0. Il prodotto si chiama AmonHen, e dal 2026 anche i confini lo dicono: il pacchetto è `amonhen`, le variabili sono `AMONHEN_*`, il database è `amonhen.db`, e da settembre hanno lo stesso nome il repository su GitHub e la cartella locale. `bank-connector` resta il nome con cui quel repo ha ospitato il connettore prima che il prodotto avesse il suo: è storia della sezione, non lo stato di oggi.

## 8. Dove non va l'AI

- Mai nel percorso sincrono del sync: non deterministico, non testabile, e se l'API esterna è giù il sync si blocca.
- Mai per produrre numeri. Solo per produrre etichette discrete, sempre confermabili.
- Niente query in linguaggio naturale: SQL scritto a mano su uno schema pulito è più veloce e più affidabile.
- Niente anomaly detection generativa quando esiste una statistica robusta.
- Mai da sola. Nessun timer, nessun effetto e nessun giro automatico chiede al modello al posto della persona: una chiamata parte da un tocco, e parte solo da lì (sezione 5.5).
- Mai dentro la pianificazione. L'analisi periodica del piano e del portafoglio si fa fuori dall'app, su uno snapshot, con un assistente che legge cifre già calcolate dal sistema (sezione 5.16). L'app non chiama un modello per questo, quindi piano, portafoglio e importi non partono dall'app verso un fornitore (sezione 4). I parametri fiscali e le ipotesi degli scenari li scrive una persona, con la fonte.

## 9. Roadmap

La UI compare presto e cresce con il sistema, invece di essere l'ultimo strato. Motivo pratico: è l'unico modo per usare il sistema mentre lo si costruisce, e un sistema che si usa si finisce.

Le fasi concluse sono qui per nome; cosa contenevano e quando si consideravano fatte sta in `docs/storia-desiderata.md`.

- **Fase 0 — verifica del percorso di fetch.** *(fatta)*
- **Fase 1 — ingest e ledger.** *(fatta)*
- **Fase 2 — riconciliazione, categorie, prima UI.** *(fatta)*
- **Fase 3 — metriche e cruscotto.** *(fatta)*
- **Fase 4 — budget e affinamenti.** *(fatta)*
- **Fase 5 — assistente.** *(fatta, poi tolta: sezione 5.9)*

Ogni fase è deployabile e usabile da sola. Nessuna fase richiede che la successiva esista per avere senso.

- **Fase 6 — il sync si comanda, la nota si scrive, cancellare è possibile.** *(fatta)*
- **Fase 7 — il primo setup è guidato.** *(fatta)*
- **Fase 8 — il ledger si copia, e si torna indietro.** *(fatta)*
- **Fase 9 — il budget si pianifica.** *(fatta)*
- **Fase 10 — si vede l'essenziale.** *(consegnata, v1.10.0)*
- **Fase 11 — le statistiche al posto dell'assistente.** *(consegnata, v1.16.0)*
- **Fase 12 — si pianifica verso un obiettivo.** *(da fare)* La sezione 5.16 a fette, ognuna usabile da sola:
  1. obiettivi, profilo, parametri fiscali per anno e confronto fra fondo pensione e PAC — la fetta che risponde alla domanda;
  2. il portafoglio dichiarato a mano, contro il versato netto di *Investimenti*;
  3. le proiezioni per scenari verso ciascun obiettivo.

**Stato (ottobre 2026).** Fasi 0-9 consegnate, più il cruscotto con i grafici e la rinomina in AmonHen, la sezione Categorie e regole nell'app, le regole sul testo contenuto nella descrizione o su un'espressione fra barre, la gestione dei giroconti e la loro prova per IBAN, i filtri del cruscotto e la sezione Conti e budget con creazione dei conti e dichiarazione dei saldi. La fase 6 ha aggiunto il pulsante di sync nell'app, la nota locale di un movimento, la cancellazione con il suo tombstone, la flag di reimport per conto e il cestino che ripristina, e la sezione 5.4 che spiega la differenza lasciata da una cancellazione a mano. La fase 7 ha aggiunto il setup guidato della sezione 5.10 e la configurazione che l'app scrive da sé, con la cartella di configurazione montata al posto dei due file. L'immagine la costruisce la CI: un tag `v*` fa girare i test e la build del bundle, poi pubblica su GHCR (`linux/amd64`), e il NAS tira l'immagine con il suo `AMONHEN_TAG` invece di costruire dal sorgente — il NAS non ha bisogno del repository. L'immagine e pubblicata: il tag `v1.3.0` ha fatto girare test e build del bundle, poi la CI l'ha costruita per linux/amd64 e messa su GHCR. La fase 8 ha aggiunto la copia che non c'era — snapshot datati e consistenti del ledger e della configurazione, con la ritenzione, il ripristino e il cron che li comanda (sezione 5.11) — e la prova locale in container dell'intero primo avvio: la banca finta che risponde dalle fixture, il wizard percorso davvero, lo snapshot e il ritorno dallo snapshot, così il primo avvio e il ripristino non si provano la prima volta sul NAS. Accettare una proposta decide i movimenti e basta: una regola nasce solo se la casella la chiede, e con il testo che si scrive nel dialogo. La fase 9 ha dato al budget una sezione sua e la pianificazione della sezione 5.12. Un conto collegato si sincronizza anche su un periodo scelto, passato compreso, con l'esito per finestra e i probabili doppioni dell'import tenuti da parte finché una persona decide (sezione 5.1). Le metriche si chiamano con parole che dicono cosa misurano invece che burn e runway. Una regola può cancellare o registrare un giroconto, ristretta a un conto e a un intervallo di importi; un conto si elimina dall'app, e i movimenti si cancellano o si categorizzano in blocco. Una regola di giroconto verso un conto creato a mano gli scrive l'altra gamba, e quel conto può contare nel patrimonio per il saldo calcolato dai movimenti (sezioni 5.5 e 5.8): è come si tiene il conto deposito di Revolut, che Enable Banking non espone. Lavoro aperto, tracciato nel backlog: il primo deploy sul NAS di quell'immagine e il consenso di Fineco da rinnovare.

## 10. Rischi

| Rischio | Mitigazione |
|---|---|
| Doppio conteggio nella zona di sovrapposizione tra sync e import storico | Test di reimport su periodo già sincronizzato, come criterio di uscita della fase 1 |
| Storico insufficiente per le metriche a 6 e 24 mesi | Backfill da export in fase 1; fino ad allora, riportare le metriche come parziali anziché calcolarle su dati troppo corti |
| Enable Banking cambia gli id o scade il consenso | Fallback hash + alert sulla scadenza del consenso PSD2; l'import file resta come percorso di recupero |
| Formati di export eterogenei tra istituti | Un adattatore per formato, isolato dal resto della pipeline |
| Il codice di integrazione esistente non è verificato contro l'API attuale | Fase 0 prima di qualsiasi refactoring; trattarlo come riferimento, non come base funzionante |
| Perdita delle funzioni che Actual dava gratis (budget, split, mobile) | Le fasi successive le ricostruiscono; ogni fase resta usabile da sola |
| Deriva verso l'over-engineering | Ogni feature nuova deve rispondere a "quale decisione mi fa cambiare?" |
| La specifica insegue il codice, e la fetta successiva implementa il prodotto vecchio | La specifica si aggiorna nello stesso cambiamento in cui la decisione cambia, e la versione sale |
| Dati finanziari personali a un fornitore terzo | Passano solo merchant normalizzati e nomi di categoria: nessun importo, nessun IBAN, nessun payload grezzo, e la funzione si può tenere spenta (sezione 5.5) |
| Un merchant che si chiama come un'istruzione | Le descrizioni entrano come dati, e l'unica risposta accettata è quella che rispetta lo schema: merchant e categorie già noti (sezione 5.5) |
| Costo e latenza che scivolano | Domanda limitata, una chiamata solo da un tocco, e il modello fuori dal percorso del sync (sezione 5.5) |
| Le regole crescono con la coda invece che con le decisioni prese | La casella è spenta di default: accettare assegna la categoria ai movimenti in attesa e non scrive niente in `rules`; la regola nasce solo se la si chiede, con il testo che si edita nel dialogo (sezione 5.5) |
| Un rimborso gonfia le Entrate (giugno 2026: cinque accrediti che erano denaro altrui contati come le entrate del mese) | Si mette nella categoria della spesa che compensa: esce dalle entrate e abbassa quella categoria. Denaro di altri solo di passaggio si dichiara ancora come il giroconto verso un conto proprio. La coppia con il singolo addebito non si modella, perché la contabilità viva non ne mostra nessuna |
| I parametri fiscali invecchiano e il confronto fra fondo e PAC dà una cifra sbagliata con aria sicura | Sono dati con anno e fonte, non codice; un anno mancante si dice invece di coprirlo con il precedente, e ogni cifra scrive l'anno che ha usato (sezione 5.16) |
| Una proiezione viene letta come una previsione | Tre scenari invece di uno, ipotesi scritte accanto al risultato, euro di oggi, e nessuna ipotesi stimata dal passato (sezione 5.16) |
| La pianificazione scivola verso la consulenza | Il sistema mostra le conseguenze di ripartizioni scritte da una persona e non ne propone una (sezione 3) |
| La chiave privata Enable Banking passa dall'app: si incolla in un campo e il server la scrive su disco | Il traffico è quello del tailnet e basta (sezione 4: nessuna esposizione pubblica); la chiave non torna mai in una risposta e non finisce nei log, e il campo mostra solo se una chiave c'è e se si carica. Resta possibile metterla a mano dove `pem_path` la indica |
| Un setup interrotto a metà lascia una configurazione incompleta | Lo stato si rilegge da `/api/setup` e ogni passo è riprendibile; una scrittura rifiutata non tocca il file, quindi una chiave sbagliata non sostituisce una buona, e `/connect` con la configurazione incompleta dice cosa manca invece di fallire |
