# Desiderata — AmonHen, sistema di monitoring finanziario personale

Versione 1.9 — settembre 2026

*0.1 · prima stesura. 0.2 · allineamento al costruito: fasi 0-4 e cruscotto
consegnati, regole sul testo contenuto nella descrizione, giroconti visibili e
gestibili, invariante di §5.4 esposta per figura, rata del mutuo rimossa.
0.3 · filtri del cruscotto (periodo, conti, categorie) e sezione Conti e budget,
con creazione di un conto e dichiarazione dei saldi dall'app.
0.4 · la prova dei giroconti è l'IBAN che ciascuna banca stampa sulla propria
gamba, e l'IBAN del conto si legge dall'endpoint dei dettagli; le cinque sezioni
si raggiungono dalla barra in basso o dal menu in alto, che le nomina per esteso
e dice cosa contengono. Le due vie sono una decisione: la barra cambia sezione
con un tocco, il menu sta dove una quinta parte di schermo non arriva.
0.5 · l'assistente di §5.9 è specificato — una lettura in prosa dei numeri
calcolati altrove, con proposte confermabili e nessuna aritmetica propria — e la
ri-autorizzazione di un conto rinfresca la voce che ha già invece di accodarne
una seconda.
0.6 · l'assistente di §5.9 è costruito, con i suoi guardiani in codice; il denaro
che non è né spesa né entrata si dichiara invece di indovinarlo (§5.3), comprese
le quote della cointestata e i rimborsi; i confini rimasti sono rinominati —
pacchetto `amonhen`, variabili `AMONHEN_*`, database `amonhen.db`.
0.7 · la coda dice cosa una proposta decide — quanto denaro, su quanti movimenti e
quando — e le regole si presentano raggruppate per la categoria che assegnano.
Il modello di §5.9 è configurato e ha risposto alla sua prima domanda vera: `.env`
viene letto all'avvio, da `uv run` e da docker compose allo stesso modo.
0.8 · la categoria di una proposta si corregge prima di accettarla, e non
sceglierne nessuna è il rifiuto: accettare scrive la regola con la categoria
scelta, non con quella proposta.
0.9 · le categorie si creano da dove si guardano — Conti e budget — e da dove
servono, la tendina di una proposta; il cruscotto mette i grafici prima e compatta
filtri e metriche; il documento dell'app non si mette in cache, perché una copia
vecchia punta ad asset che un rilascio ha già sostituito.
1.0 · le categorie e le regole sono una sezione sola: una voce per categoria, con
i suoi flag e le regole che la riempiono, e la riga per scriverne una dentro il
gruppo — una regola assegna la categoria sotto cui sta, quindi non c'è niente da
scegliere. Conti e budget resta i conti e i budget del mese.
1.1 · una regola può essere un'espressione regolare, scritta fra barre: copre una
famiglia che la banca scrive in troppi modi per elencarli, vede lo stesso testo
delle regole — spazi collassati, maiuscole ignorate — e vince su un testo;
un'espressione che non compila si rifiuta invece di restare lì a non combaciare.
1.2 · il progetto prende il nome del prodotto anche fuori: il repository su
GitHub e la cartella locale sono `amonhen`, non più `bank-connector`, e §7
perde la frase che diceva il contrario.
1.3 · la fase 6: il ledger si aggiorna da un pulsante nell'app invece che da un
terminale, un movimento porta una nota locale che il sync non tocca, si cancella
davvero — con il tombstone che tiene il sync dal rimetterlo, una flag per conto
che decide se può tornare e un cestino che lo ripristina — e la §5.4 spiega la
differenza che una cancellazione lascia invece di gridare mismatch. L'immagine
la costruisce la CI su un tag, e il NAS la tira: non ha più bisogno del repo.*
*1.4 · il primo setup è guidato dall'app (§5.10): le credenziali Enable Banking
— chiave privata incollata compresa —, l'istituto scelto fra quelli che il
provider accetta invece che a memoria, i conti da tenere con il nome che il
ledger userà, il primo sync con l'esito per conto e il saldo dichiarato che fa
passare la §5.4 da `non verificato` a `verificato`. La schermata è un gate al
primo avvio e resta raggiungibile dopo, perché un consenso scade e una banca si
aggiunge. Compose monta la cartella di configurazione e non i due file, così un
container appena creato può far nascere `accounts.json`; `/callback` torna
nell'app invece di rispondere JSON grezzo.*
*1.5 · il backup smette di essere una cosa che non c'era (§5.11): snapshot datati
e consistenti del ledger e della configurazione, presi con l'API di SQLite perché
il server può stare scrivendo, con la ritenzione che li tiene bounded, il
ripristino scritto come procedura e la copia sul NAS che il cron comanda. La
stessa fetta porta una prova locale in container dell'intero primo avvio —
l'immagine costruita dal checkout, la cartella di configurazione con la proprietà
che ha il NAS, il wizard percorso contro una banca finta che serve le fixture
anonimizzate — perché il primo avvio non si prova la prima volta sul NAS e il
ripristino non si prova la prima volta che serve.*
*1.6 · il desktop smette di essere un telefono largo: sopra i 1024 px la colonna
di contenuto si prende lo spazio che la finestra ha (1100, e 1240 da 1440) invece
di restare 720 px in mezzo al vuoto, il cruscotto affianca i due grafici del
periodo, la coda va a due colonne e poi a tre, e da 1440 le otto tessere stanno
su una riga. Le sezioni smettono di essere una pillola in fondo alla finestra: la
stessa lista sale in un rail laterale, che sostituisce la barra in basso e il menu
— le due vie di §0.4 restano quelle del telefono, che sotto i 1024 px è ancora la
forma dell'app. E il contenuto non si allarga fino a sciogliere ciò che è stretto
per natura: i paragrafi tengono le 72 battute di una riga di libro, e il setup,
che è un modulo, resta una colonna.*
*1.7 · le schede si aprono da destra invece che dal fondo: sopra i 1024 px la
scheda di un movimento — categoria, nota, split —, il giroconto, «Dichiara saldo»
e «Nuovo conto» sono un pannello ancorato al lato, alto quanto la finestra, così
quello che si stava guardando resta visibile accanto — la stessa finestra di
prima, con lo stesso Esc, lo stesso backdrop e la stessa trappola del fuoco.
Sotto i 1024 px il foglio dal basso resta quello del telefono. (Il budget non è
una scheda: si modifica nella riga che lo mostra.)*
*1.8 · le due schermate che si guardano di più prendono la forma della finestra.
I movimenti sono una tabella — data, descrizione, categoria, importo, e il conto
che si prende una colonna sua dove c'è spazio — con l'intestazione che resta in
cima mentre si scorre, invece di una riga che si allarga fino a mille e duecento
pixel. La coda si guarda in due: l'elenco delle proposte a sinistra, il dettaglio
di quella scelta a destra con i suoi comandi, così si decide senza aprire niente.
Sotto i 1024 px le due schermate restano quelle del telefono.*
*1.9 · l'import di un estratto conto si comanda dall'app: un file CSV, le
colonne mappate a mano — data, importo o Dare e Avere, descrizione, formato della
data e dei decimali — l'anteprima di cosa diventano le righe prima che qualcosa
venga scritto, e l'esito con quante ne sono entrate e quante erano già presenti.
L'idempotenza è la stessa impronta di contenuto del percorso da riga di comando,
quindi reimportare lo stesso file non scrive niente; una riga che non si legge si
riporta con la sua riga invece di fermare il file.*

Questo file è la definizione di prodotto: cosa il sistema deve fare, i vincoli,
i non-obiettivi, l'ordine dei lavori e lo stato di ciascuna fase (§9). `CLAUDE.md`
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

1. **Vista unificata del flusso.** Tutti i conti collegati confluiscono in un unico ledger riconciliato, con storico profondo abbastanza da rendere calcolabili le metriche di §5.6.
2. **Burn rate robusto alla varianza mensile**, con separazione esplicita tra componente ricorrente e componente episodica.
3. **Riconciliazione automatica dei trasferimenti** tra conti: un movimento interno appare una volta sola e non conta come spesa.
4. **Ripetibilità**: il dato si aggiorna da solo, senza download manuali. Il sync Enable Banking è **parte del sistema**, non un servizio esterno a cui il sistema si appoggia.
5. **Interfaccia propria.** Il sistema ha una UI mobile-first da cui rivedere le categorie, correggere gli split e leggere le metriche. Non è un requisito opzionale: è il modo in cui il sistema viene effettivamente usato.

## 3. Non-obiettivi

Esplicitamente fuori scope, per evitare scope creep:

- Integrazione API con il broker. Il patrimonio si aggiorna con snapshot manuale mensile.
- Calcolo di rendimenti di portafoglio (TWR, IRR). Il broker è già un cruscotto.
- Previsioni di spesa, forecasting, ottimizzazione automatica del budget.
- Categorizzazione completamente automatica senza revisione umana.
- Multi-utente, multi-valuta, condivisione.
- Gestione dei crediti verso terzi. Le spese anticipate per altri non vengono modellate come crediti: **un rimborso o una quota non sono entrate**, si dichiarano (§5.3) e restano fuori dalle entrate come i giroconti — verso l'altra gamba quando il conto è collegato, verso una destinazione dichiarata quando non lo è. Quello che non si modella è la *coppia*: l'accredito esce dalle entrate, ma niente dice quale spesa compensi, quindi la categoria che avrebbe ridotto resta com'è.
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

**Percorso B — import file (bootstrap e recupero).** Import di export CSV/OFX scaricati manualmente da ciascun istituto. Serve a due cose:

1. **Seed dello storico.** Le API PSD2 restituiscono tipicamente una finestra limitata (ordine dei 90 giorni; verificato: chiedendo il 2026-01-01 sono tornati movimenti dal 2026-06-14). Le metriche di §5.6 richiedono 6 mesi per la mediana mobile e 24 mesi per l'accantonamento episodico: senza backfill da export non sono calcolabili prima di due anni di esercizio. L'import storico è quindi un prerequisito, non un extra.
2. **Recupero.** Consenso PSD2 scaduto, istituto temporaneamente indisponibile, buchi nel sync.

Requisiti comuni a entrambi i percorsi:

- Idempotenza: `external_id` del provider quando presente, con fallback `hash(data, importo, descrizione, conto)`. L'export CSV di solito non contiene l'`external_id`, e allora il fallback è il solo discriminante nella zona di sovrapposizione tra i due percorsi: va testato esplicitamente reimportando un periodo già sincronizzato e verificando che il conteggio non cambi. Quando invece l'estratto una colonna di identificativo ce l'ha, la sezione **Importa** la mappa e quell'identificativo prende il posto dell'impronta come identità.
- Un adattatore per formato di export, che normalizza verso lo schema comune. I formati differiscono per istituto (colonne, segno dell'importo, formato data, separatore decimale).
- L'adattatore si può scegliere invece di scriverlo: dalla sezione **Importa** dell'app si dice quali colonne sono la data, l'importo (o Dare e Avere), la descrizione, il formato della data e dei decimali, e l'identificativo della banca quando c'è, e l'anteprima mostra le prime righe mappate prima che qualcosa venga scritto. Le righe che non si leggono si contano con la loro riga invece di fermare il file; i profili scritti per banca restano per la riga di comando.
- Gestione della transizione pending → booked senza duplicare la transazione.
- Payload grezzo conservato integralmente, con indicazione del percorso di provenienza, per poter riprocessare senza ri-fetchare né ri-scaricare.
- **Una cancellazione è una decisione che il sync rispetta.** Un movimento si cancella dal ledger e resta in `deleted_transactions` con l'identità con cui il ledger deduplica (l'identificativo della banca, altrimenti l'impronta di contenuto così com'era), il payload, la nota, com'era la riga e quando è stata tolta: senza quella copia il sync successivo riscriverebbe il movimento, e a mano non resta niente da rileggere. Un `PDNG` cancellato sopprime anche il `BOOK` che la banca manda dopo, anche quando lo contabilizza con un altro riferimento e un'altra data. La soppressione riconosce il movimento in tre modi, e sono le relazioni che il ledger conosce già: l'identificativo con cui è stato cancellato, lo stesso contenuto che arriva dall'*altro* percorso di ingest — è la zona di sovrapposizione di §5.1, dove l'impronta è il solo discriminante — e la gamba contabilizzata di un movimento in attesa cancellato qui, che la banca manda giorni dopo con un altro riferimento e un'altra data. Esatta ovunque altro: quattro accrediti identici nello stesso giorno sono quattro movimenti, e cancellarne uno non deve sopprimere il suo gemello, quindi un movimento dello stesso stato non si riconosce mai dal solo contenuto. Una leg di un giroconto non si cancella lasciando l'altra appesa al conto di clearing: il link si rifiuta, l'altra gamba torna in coda, e la cancellazione lo dice. Il cestino di un conto elenca ciò che è stato tolto — data, importo, descrizione, nota e quando è sparito — e il ripristino di una riga la rimette nel ledger dal payload conservato, con la sua nota: una seconda volta è rifiutata, e il ripristino passa dalle stesse regole dell'ingest, quindi un movimento che il ledger già tiene non viene scritto due volte. Quello che il ripristino non può sapere è un movimento tornato sotto un'identità che il tombstone non porta — il limite dell'impronta nella zona di sovrapposizione — e il posto dove accorgersene è la lista del cestino.
- **Il ritorno di una cancellazione è una decisione del conto.** Una flag per conto — spenta, perché cancellare deve significare cancellare — dice se il sync successivo riporta i movimenti cancellati: accesa, li riscrive dal tombstone con la loro nota e segna che sono tornati; spenta, li lascia fuori e l'esito del sync li conta fra i soppressi. Si accende per un conto solo, perché la ragione è la storia di quel conto — un consenso rinnovato, un periodo cancellato per sbaglio — non una proprietà del ledger, e spegnerla di nuovo non ricancella ciò che è tornato.
- **La ri-autorizzazione rinfresca, non accoda.** Un consenso può morire mentre la sessione che lo contiene è ancora valida, e rinnovarlo produce una sessione nuova mentre l'uid del conto resta lo stesso: la voce di `accounts.json` che ha quell'uid si aggiorna sul posto — nome e data d'inizio restano, perché il primo è il nome con cui il ledger conosce il conto e la seconda è la storia che ha già importato — e solo un conto mai visto viene aggiunto. Accodare una seconda voce significava, per un ledger che riconosce i conti per nome, un secondo conto con la stessa storia dentro.

### 5.2 Modello a partita doppia

Ogni movimento è composto da N *postings* la cui somma è zero.

- **Spesa**: conto reale −X, categoria di spesa +X.
- **Giroconto**: conto A −X, conto B +X quando entrambe le gambe sono collegate; altrimenti la seconda gamba va su un conto virtuale — il conto di clearing per una coppia, un conto intitolato all'etichetta per una gamba sola verso un conto proprio non collegato. Nessuna categoria: non è spesa per costruzione, non per regola.
- **Split**: più postings di categoria sullo stesso movimento.

### 5.3 Riconciliazione trasferimenti

- Match su: importo opposto, conti diversi, |Δt| ≤ 2 giorni, nessuna delle due gambe già appaiata.
- **La prova è l'IBAN che ciascuna banca stampa sulla propria gamba.** Una gamba che nomina il conto dell'altra è evidenza; una che ne nomina un altro è una contraddizione, e la coppia si rifiuta: è la coincidenza d'importo che il matcher esiste per non accettare. Due accrediti dello stesso importo nello stesso giorno si distinguono così, e non tirando a indovinare.
- L'IBAN del conto si legge da `GET /accounts/{uid}/details` — la sessione elenca gli uid e nient'altro — e il sync lo registra sul conto quando manca. Senza quell'IBAN la prova non è disponibile, e i candidati si ordinano solo per chi nomina una controparte: entrambe le gambe (più forte), una sola, nessuna. Il metodo del link dice quale dei tre casi è stato (`…-unverified` quando il confronto non era possibile).
- Mai match sulle descrizioni (incoerenti tra istituti).
- In caso di ambiguità (più candidati compatibili), risoluzione via matching bipartito di peso massimo, non greedy.
- Ogni link ha un livello di confidenza e resta rivedibile a mano: si conferma, si annulla, si registra una gamba sola verso una destinazione dichiarata (§5.3) e si abbinano due gambe a mano. L'abbinamento manuale accetta solo le coppie che il matcher stesso accetterebbe: conti reali diversi, importi uguali e opposti, nessuna split da perdere.
- Annullare una coppia **rifiuta** il link invece di cancellarlo, così il matcher non la ripropone al sync successivo; annullare una gamba sola la riporta in coda, senza categoria.
- **Il denaro che non è né spesa né entrata si dichiara.** Una voce di `passthrough` in `accounts.json` nomina una destinazione — il conto virtuale in cui finisce il lato non reale — e i testi che la banca stampa su quei movimenti, con `incoming_only` per le etichette che nominano una persona o una ditta: lo stesso nome vale nelle due direzioni, e il nome di una ditta porterebbe fuori dal burn il premio oltre al rimborso. Serve perché i due casi non si riconoscono altrimenti: un conto proprio non collegato non ha una contro-gamba da appaiare, e un accredito da fuori non ha un addebito che lo compensi. Sulla contabilità viva nessuno degli accrediti di un mese di prova ha un addebito di pari importo: quello che hanno in comune è chi li manda, non cosa pagano. Restano quindi fuori dalle entrate e fuori dalle spese, la loro categoria non viene toccata, e restano sul libro col nome della destinazione.

### 5.4 Invariante di correttezza

Per ogni conto e ogni periodo:

```
saldo_iniziale + Σ movimenti == saldo dichiarato dalla banca
```

Questa è la quantità conservata del sistema. Va verificata a ogni sync e l'esito è **visibile per conto** (pannello Conti), non sepolto in un log: non è una metrica di spesa, è lo stato di affidabilità di quel conto. La banca dichiara due figure per la stessa data — disponibile e contabilizzata — e ognuna si confronta con il saldo calcolato che significa la stessa cosa, così un controllo che fallisce dice quale delle due non torna, ed è ciò che distingue un movimento in attesa da un duplicato. Un conto per cui nessuno ha dichiarato un saldo resta `non verificato`: il silenzio non è un assenso. Se non torna, ogni numero a valle è inaffidabile.

**Una differenza spiegata non è un guasto.** Gli esiti visibili per conto sono quattro, non tre: oltre a *verificato*, *mismatch* e *non verificato*, un conto la cui differenza è esattamente ciò che una persona ha cancellato a mano si legge **d'accordo salvo N movimenti cancellati a mano**, con l'importo, perché il ledger e la banca discordano davvero, ma per una decisione presa qui, e un rosso che nessuno può far sparire insegna a ignorare l'unica riga che conta. Ogni figura si confronta con i movimenti che conterrebbe: quella disponibile conta anche i sospesi cancellati, quella contabilizzata no. Una differenza che i tombstone non spiegano resta un mismatch, e il sync non chiama guasto ciò che è spiegato: lo annota.

### 5.5 Categorizzazione

Pipeline a cascata, dal deterministico al probabilistico:

1. Normalizzazione del merchant (stringa grezza → nome pulito), usata dalle proposte e dal classificatore; le regole lavorano sulla descrizione.
2. Regole su un testo contenuto nella descrizione del movimento, o su un'espressione regolare scritta fra barre — una regola copre una famiglia di movimenti, non un solo nome; l'espressione copre le famiglie che la banca scrive in troppi modi per elencarli. Copertura attesa 80-90%.
3. Classificatore statistico leggero (logistica su char n-gram) sulla parte restante.
4. LLM solo sulla coda: transazioni mai viste, in batch asincrono, output sempre marcato "da confermare".

Nessuno stadio scrive una categoria definitiva senza che sia rivedibile. Nessuno stadio è bloccante per il sync.

**La coda dice cosa una proposta decide.** Le proposte — del classificatore e del modello — sono per *merchant*, non per movimento: un sì copre tutti i movimenti di quel merchant. Accanto alla categoria proposta, quindi, la coda porta quanto denaro aspetta, su quanti movimenti e quando sono passati, letto con lo stesso predicato della coda stessa: la cifra di una proposta non può contraddire la lista che le sta sotto. Una proposta i cui movimenti sono già stati decisi — da una regola o da una persona — resta senza niente da pesare, e lo dice invece di mostrare uno zero.

**La proposta si corregge.** La categoria proposta è un punto di partenza, non un verdetto: si cambia prima di accettare, e accettare scrive la regola — e quindi i movimenti — con la categoria *scelta*. Non sceglierne nessuna è il rifiuto, perché è lo stesso gesto con l'esito opposto: una proposta che non merita una categoria non deve restare in coda per sempre. Il modello e il classificatore sbagliano su merchant che non hanno mai visto — misurato: il classificatore indovina l'86% dei merchant tenuti fuori dall'addestramento contro il 47% della categoria più frequente, e il 92% di ciò che propone sopra la soglia di confidenza — quindi la correzione è il modo in cui la coda resta utile mentre i due proponenti migliorano con quello che la persona decide.

**Categorie e regole sono una sezione sola.** Ciò che una categoria è e ciò che ci finisce sono la stessa decisione vista dai due capi, e stanno in un elenco solo: una voce per categoria, con i due flag che le metriche leggono — episodica, incomprimibile — e quante regole e quanti movimenti tiene. Sotto si aprono i testi che le assegnano, e in fondo al gruppo la riga che ne scrive uno: una regola assegna la categoria sotto cui sta, quindi non c'è niente da scegliere. Trenta pattern sono trenta decisioni, otto categorie sono un budget. Cercare apre i gruppi che hanno trovato qualcosa, e una categoria la cui regola si corregge si sposta da sola. Una categoria si crea qui, dove si guarda, e dalla tendina con cui una proposta si corregge: una categoria non categorizza niente da sola, è il posto dove i movimenti possono finire, e ci arrivano da una proposta, da una regola o da un movimento aperto.

**Una regola è un testo, o un'espressione.** Scritta fra barre — `/amazon (eu|payments)/` — la regola è un'espressione regolare: una sola regola per la famiglia che la banca scrive in troppi modi per elencarli. L'espressione vede lo stesso testo che vedono le regole — spazi collassati, maiuscole ignorate — perché una parola e un'espressione devono descrivere gli stessi movimenti. Il tipo di una regola sta nel suo pattern, non in una colonna: quel che si è scritto è quel che si rilegge, nell'elenco come nella rimozione. Un'espressione che non compila si rifiuta quando la si scrive — l'API risponde 422 con il motivo, e la riga in fondo al gruppo lo mostra — perché una regola che non potrà mai combaciare non deve arrivare al ledger. Dove due pattern combaciano vince il più lungo — la più stretta — che sia un testo o un'espressione: un'espressione scritta per nominare una famiglia è più lunga delle parole che sostituisce e ne prende i movimenti, una più larga non ruba niente a un testo più stretto che combacia ancora. Una barra sola e `//` restano testo, così un pattern che contiene una barra non diventa un'espressione per sbaglio.

### 5.6 Metriche esposte

Solo queste, in ordine di priorità:

- **Burn ricorrente**: mediana mobile a 6 mesi delle spese non episodiche.
- **Accantonamento episodico**: somma one-off ultimi 24 mesi / 24. Gli eventi rari non vanno rimossi, vanno modellati come processo separato con frequenza propria.
- **Burn atteso** = burn ricorrente + accantonamento episodico.
- **Runway stressato** = liquidità / burn atteso. La rata del mutuo non è più una voce fissa del denominatore: un pagamento del mutuo è un movimento come gli altri, e se deve contare sta in una categoria.
- **Quota incomprimibile vs discrezionale**: quanto sarebbe tagliabile se servisse.
- **Flusso di risparmio**: trasferimenti verso conti di investimento. È l'unico ponte tra monitoring delle spese e monitoring del patrimonio. PAC, contributi al fondo pensione e TFR non sono spese.

Il cruscotto mostra tre serie osservate — spesa per categoria (con la fetta "senza categoria" in evidenza), entrate e uscite per mese, patrimonio osservato — e i grafici non fanno aritmetica: ogni serie si calcola nel backend, così una torta non può risultare più piccola del denaro che è uscito. Il cruscotto si filtra per periodo, per conti e per categoria, e i tre filtri non pesano uguale: il **periodo** decide cosa mostrano grafici e serie; i **conti** restringono tutto ciò che è di conto — le spese attribuite al conto che le ha pagate, la liquidità, il risparmio, il patrimonio; la **categoria** restringe solo le spese, perché una categoria non descrive il denaro che entra né quello che i conti valgono. Il cruscotto si legge dall'alto: prima i grafici, con il solo periodo sempre in vista e il resto dei filtri a un tocco di distanza, poi le metriche in griglia — etichetta e cifra, con quello che significano dietro un solo *Come si calcolano*. Un pannello di cinque campi sopra i grafici li spingeva fuori dalla schermata, che è il contrario di quello per cui la schermata esiste.

Le card di §5.6 non seguono il periodo: le loro finestre di 6 e 24 mesi sono la definizione della metrica, non una vista, e ogni card dichiara la finestra che ha usato. Un filtro si applica nel backend, mai nel browser.

Conti e budget si gestiscono da una sezione dell'app, non dal cruscotto: l'elenco dei conti con saldo, figura iniziale ed esito della verifica, la dichiarazione di un saldo letto dalla banca, l'allineamento del saldo iniziale perché l'invariante di §5.4 torni a valere, la creazione di un conto reale a mano (il broker, o una banca non collegata), il budget mensile di ogni categoria. I flag delle categorie e la loro creazione stanno invece nella sezione che le categorie le definisce insieme alle regole che le riempiono (§5.5).

Esplicitamente escluse perché decorative: patrimonio a frequenza giornaliera, medie su singolo mese, rendimenti calcolati internamente.

### 5.7 Anomalie

Detection statistica deterministica, non LLM: z-score robusto su MAD per categoria, oppure soglia sul p95 storico della categoria. Deve essere spiegabile con una frase.

### 5.8 Patrimonio

Patrimonio **osservato**, non ricostruito: `account_balances` tiene ciò che la banca dichiara per un conto in una data, e lo scrivono il sync (per ogni conto raggiungibile), `balances` su richiesta e `anchor` per una dichiarazione a mano. La serie somma l'ultimo saldo noto di ogni conto reale tracciato, e un conto conta dalla sua prima osservazione: la curva comincia dove cominciano i dati, senza back-fill né interpolazioni. Liquidità, runway e patrimonio contano solo i conti reali tracciati.

Quello che una banca non dichiara — il broker — entra come conto reale con un saldo dichiarato a mano, non con una tabella separata: l'aggiornamento resta manuale e raro, e ha lo scopo fiscale di fine anno (valore di fine anno e giacenza) finché il broker è su entità estera in regime dichiarativo.

Motivazione della separazione: spese e patrimonio sono processi con frequenza di campionamento e struttura del rumore diverse di ordini di grandezza. Unirli fa entrare la volatilità di mercato nelle metriche di spesa.

### 5.9 Assistente *(costruita)*

Una sezione dell'app che discute i numeri che il backend ha già calcolato — spese, budget, patrimonio, coda — e le proposte che ne derivano. Non è una chat generica sul mondo, e non è un secondo motore di calcolo.

**Cosa fa.** Riceve una domanda, o un contesto che la contiene già, insieme ai dati *già calcolati* che servono a rispondere: le serie del cruscotto, i totali, le categorie, i budget, e i movimenti che li compongono. Restituisce una lettura in prosa: perché questo mese è diverso, cosa ha spinto il burn, quale categoria sta scivolando, se quel budget regge, da dove cominciare nella coda. Può anche **proporre**: una categoria per un merchant che nessuna regola copre (la strada che esiste da §5.5), un budget mensile per una categoria che non ne ha, una regola da scrivere quando lo stesso merchant torna tre volte.

**Come tratta i numeri.** L'unica aritmetica ammessa è quella del backend. L'assistente non somma, non stima, non arrotonda a occhio: cita le cifre che riceve, e ogni cifra che compare nella sua prosa è una di quelle. Un numero che non è nella risposta dell'API non può comparire nel testo; se serve, si calcola prima e si passa dopo. Non è un proposito: la lettura si confronta cifra per cifra con quelle passate — separatori italiani e date comprese — e una che ne citi un'altra si rifiuta, si registra e non si mostra. Il testo generato è marcato come tale nell'interfaccia, così una cifra dentro una frase non viene mai letta come una cifra calcolata — è la stessa regola di §8, vista dal lato di chi legge.

**Cosa non può fare.** Non scrive nel ledger: nessuna categoria, nessun budget, nessuna regola, nessuno split, nessun giroconto. Ogni sua proposta è una riga da confermare con lo stesso gesto delle proposte di §5.5, e finché non è confermata non cambia niente. Non gira nel percorso del sync (§8). Non risponde con SQL: le query restano scritte a mano. Non vede identificativi: niente IBAN, niente numeri di conto, niente nomi di controparte che non siano già il merchant normalizzato, e il payload grezzo non esce dalla macchina.

**Come si difende dagli input.** Le descrizioni dei movimenti sono testo che arriva da fuori: un merchant può chiamarsi come un'istruzione. Entrano quindi come dati, dentro la struttura della domanda, e l'unica risposta accettata è quella conforme a ciò che è stato chiesto — merchant che erano nella domanda, categorie che esistono, campi dello schema previsto. Una risposta fuori schema si scarta, si registra, e non si esegue.

**Come si controlla.** Il modello è configurazione, non codice: endpoint, nome e chiave stanno nell'ambiente, e la specifica non fissa un fornitore. Ogni chiamata ha un tetto: la domanda è limitata (i merchant sono al massimo venti, le serie sono quelle del cruscotto), le chiamate sono contate, la stessa domanda sugli stessi dati non si ripete, e l'impronta che lo decide è quella delle figure — non dell'elenco dei merchant già proposti, che cambia proprio perché l'assistente ha risposto, e un rifiuto o un timeout sono un messaggio per la persona — nessuna funzione dell'app dipende dall'assistente, e senza configurazione la sezione dice che è spenta invece di fallire. Ciò che si chiede e ciò che torna si registra, con il modello usato e l'impronta dei dati passati, così una lettura si può rileggere fra sei mesi sapendo su cosa era basata.

**Dove sta.** Una sezione propria, raggiungibile dal menu, e i punti di ingresso dove la domanda nasce da sola: la riga di un budget che sta per saltare, che passa *quel* budget invece di chiedere alla persona di ricomporre il contesto in una frase. Un ingresso generico dal cruscotto c'è stato e non serve: una domanda senza contesto è una domanda che nessuno fa, e la sezione basta a sé.

*Fatto quando*: davanti a un mese strano si ottiene in una schermata una spiegazione che cita solo cifre già calcolate e almeno una proposta confermabile con un gesto; e la stessa domanda sugli stessi dati non viene richiesta due volte.

### 5.10 Primo setup guidato *(costruita)*

Il primo avvio era una decina di passi a mano e nessuno di essi stava nel prodotto: creare `accounts.json` da un template, mettere la chiave privata accanto, far combaciare tre indirizzi (quello che il browser raggiunge, `redirect_url` nel file, la callback registrata nel dashboard), aprire a mano `/connect` scrivendo il nome dell'ASPSP a memoria, poi editare lo stesso file per tenere solo i conti voluti fra i quattro che una banca risponde, poi sincronizzare, e infine dichiarare un saldo o il conto restava `non verificato` per la §5.4. L'app conosce già il proprio indirizzo, la lista degli istituti che Enable Banking accetta e i conti che un'autorizzazione ha appena scritto: quasi tutti quei passi chiedevano a una persona qualcosa che il sistema sa.

**Il gate è la prima schermata, non un manuale.** Quando la configurazione manca, l'app apre il setup al posto delle sezioni, al primo passo che ha qualcosa da chiedere; a sistema configurato la stessa schermata resta raggiungibile dal menu, perché un consenso PSD2 scade e una banca si aggiunge, e il passo utile in quel momento è quello dei conti. Il wizard non è una modalità che si chiude per sempre: è dove la configurazione si guarda e si cambia.

**Cinque passi.**

1. *Credenziali.* Application ID, chiave privata incollata, indirizzo di ritorno, nome dell'intestatario. L'indirizzo lo propone l'app dalla propria origine — è quello che il browser raggiunge, quindi è quello giusto per costruzione — e la chiave si carica subito: una che non è una chiave privata si rifiuta lì, dove è stata incollata, invece di diventare un sync che fallisce domani. Resta a mano **una** cosa, ed è l'unica che il sistema non può scrivere al posto tuo: registrare quell'indirizzo nel dashboard Enable Banking, carattere per carattere. La schermata mostra la stringa esatta, e il rifiuto della banca (`Redirect URI not allowed`) torna verbatim.
2. *Banca.* Il nome dell'ASPSP deve combaciare con quello che Enable Banking conosce, e chiederlo a memoria era un modo per sbagliarlo: la lista arriva dall'API, filtrata per paese, e si sceglie da lì. L'autorizzazione si apre nella stessa scheda, perché è lì che il ritorno deve arrivare.
3. *Conti.* Una banca risponde con tutti i conti che l'autorizzazione copre — Fineco ne dà quattro — e prima si potavano editando il file a mano. Qui si tiene quello che serve, si dà a ciascuno il nome con cui il ledger lo conoscerà e la data da cui importarne la storia. Il nome è la chiave del ledger: un nome che un'altra voce già usa si rifiuta, invece di scoprire nel ledger che due conti erano uno.
4. *Primo sync.* Il pulsante chiede i movimenti adesso e risponde per conto con quello che ha scritto, come quello della barra in alto (§5.4 compresa): il primo sync non è un passaggio a vuoto, è la prima volta che si vede cosa è arrivato.
5. *Saldi e verifica.* Un conto senza saldo dichiarato è `non verificato` (§5.4), e un ledger che nessuno ha confrontato con la banca non è ancora affidabile: qui si dichiara il saldo letto dall'istituto, si allinea l'apertura e si legge l'esito per conto. Il setup si può chiudere con un conto ancora non verificato, ma lo dice.

**Chi scrive la configurazione.** `accounts.json` ha due scrittori, e la scrittura è la stessa: il callback OAuth aggiunge o rinfresca le voci delle autorizzazioni, il setup scrive le credenziali e cura le voci; le chiavi che il sistema non conosce sopravvivono a entrambi. La chiave privata si scrive accanto al file, dove `pem_path` la indica, e **non torna mai indietro**: l'API dice se c'è e se si carica, non la restituisce, non la registra. `load_config` resta severo — chi legge la configurazione per lavorare continua a fallire forte — mentre lo stato del setup si legge anche da un documento assente, perché "non c'è ancora niente" e "questo server è rotto" sono due cose diverse.

**Un avvio a freddo deve poter partire.** Un container appena creato non ha né `accounts.json` né `private.pem`, quindi compose monta la cartella di configurazione e non i due file: è la differenza tra un primo avvio possibile e un `up` che pretende che il setup sia già stato fatto da riga di comando. Per la stessa ragione `/connect` e `/callback` con la configurazione incompleta dicono cosa manca invece di rispondere 500, e il ritorno dal login è un 303 dentro l'app invece del JSON grezzo che nessuno leggeva: la schermata che ha iniziato l'autorizzazione è quella che deve dire cosa è arrivato.

Restano fuori, ciascuna per una ragione diversa: la configurazione dell'assistente (il modello è configurazione d'ambiente, §5.9, e l'app in container non scrive l'`.env` dell'host) e le dichiarazioni `passthrough` (§5.3: si capiscono dai testi che la banca stampa, che al primo avvio non ci sono ancora).

*Fatto quando*: davanti a un'installazione nuova, dall'app e senza terminale, si arriva a un conto collegato, sincronizzato e verificato dalla §5.4, e l'unico passo che resta a una persona è registrare l'indirizzo di ritorno nel dashboard della banca.

### 5.11 Backup e ripristino *(costruita)*

Il ledger vive in un volume del container e la configurazione in una cartella montata, e nessuno dei due era copiato da niente. Il rischio che conta non è il disco rotto: è il sync che riscrive un periodo, un conto tolto per sbaglio, un `DELETE` digitato male. Senza una copia l'unica risposta è rifare il backfill e rimettere a mano le decisioni prese in mesi di coda.

**Cosa si copia.** Il database del ledger e la configurazione che lo rende ripristinabile — `accounts.json` e la chiave privata che `pem_path` nomina — perché un ledger senza le sessioni che lo alimentano non si rilegge da nessuna banca da solo. Non l'`.env`: quella è configurazione della macchina, non del ledger, e una copia in più di un file con le chiavi dell'assistente è un rischio senza contropartita.

**Come.** Una cartella per snapshot, nominata con il momento in cui è stato preso (`2026-09-26T101500Z`), che contiene il database, i file di configurazione e un `manifest.json` con l'ora, la provenienza, lo sha256 di quello che ha scritto, i conteggi delle righe e l'elenco di cosa ha copiato. Il database si copia con l'API di backup di SQLite e non leggendo il file: il server può stare scrivendo, e una copia presa in quel momento può risultare strappata — una copia che sembra un backup e contiene mezzo movimento è peggio di nessun backup. La scrittura passa da una cartella temporanea e prende il nome definitivo solo alla fine, quindi un giro interrotto non lascia qualcosa che sembra uno snapshot buono, e una cartella senza nome non conta nemmeno per la ritenzione. La ritenzione tiene gli N più recenti (quattordici per impostazione predefinita) e non tocca niente quando è a zero: senza, la cartella cresce di un database alla volta per sempre.

**Dove, e cosa non è ancora.** Sul NAS la copia la fa il cron, dentro il container, scrivendo nella cartella `backups/` che l'host monta. Uno snapshot sul disco del NAS **non è ancora un backup**: sta sugli stessi dischi del ledger. Portarlo fuori è compito dello strumento di backup del NAS puntato su quella cartella, o di un `docker compose cp` a mano. Il prodotto scrive la copia e la rende leggibile; la ridondanza è dell'ambiente, e non si finge.

**Come si torna indietro.** Si ferma l'app — fermarla è ciò che chiude il database, quindi mentre la copia atterra non sta scrivendo nessuno — si copia `amonhen.db` dallo snapshot al posto di quello vivo, si rimette la proprietà dell'utente del container e si riaccende. Un ripristino mai provato non è un ripristino: per questo la prova locale qui sotto include il giro intero, snapshot, guasto e ritorno, invece di fermarsi al comando che scrive la cartella.

*Fatto quando*: dopo un errore che ha rovinato il ledger si torna allo stato di ieri sera con la procedura di ripristino, senza risincronizzare e senza rimettere a mano le decisioni; e la prova locale dimostra quel giro — snapshots, guasto e ritorno — prima che serva davvero, non solo che i comandi esistano.

## 6. Modello dati minimo

```
accounts             (id, nome, tipo: reale|virtuale|categoria, istituto, iban, uid_esterno, valuta,
                      saldo_iniziale, data_iniziale, flag: episodico | incomprimibile | investimento,
                      ripristina_cancellati)
transactions         (id, conto, data, importo, descrizione, stato BOOK|PDNG, external_id, content_hash,
                      origine psd2|import, payload_grezzo, controparte, conto_controparte, nota)
postings             (id, transaction_id, account_id, importo, note)
deleted_transactions (id, conto, chiave, data, importo, descrizione, stato, external_id, content_hash,
                      origine, payload_grezzo, controparte, conto_controparte, nota, cancellato_il,
                      ripristinato_il)
transfer_links       (leg_a, leg_b, confidenza, metodo, confermato_da_umano: 1 confermato, 0 da rivedere, -1 rifiutato)
rules                (chiave, testo, categoria)
account_balances     (conto, data, saldo, origine)
budgets              (categoria, importo, aggiornato_il)
merchant_suggestions (merchant, categoria, origine, decisione: pending | accepted | dismissed)
settings             (chiave, valore)
```

Vincolo di integrità: per ogni `transaction_id`, `SUM(postings.importo) = 0`.

**La nota di un movimento è locale, e nient'altro si scrive a mano.** Un movimento porta una
`notes` che la banca non manda e che nessun percorso di ingest tocca su una riga che esiste:
sopravvive alla promozione `PDNG`→`BOOK`, che riscrive data, descrizione e identificativo della
stessa riga, e alla riimportazione del periodo. L'unica scrittura che non viene da una persona è
il tombstone che restituisce a un movimento appena ricreato la nota che quello cancellato aveva,
nel reimport e nel ripristino. È l'unico campo del
movimento che una persona può modificare: importo, data e descrizione sono ciò che la banca ha
dichiarato, e la verifica di §5.4 confronta proprio quella dichiarazione con il ledger.

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
- Mai lasciare che la prosa dell'assistente contenga un numero che il backend non ha calcolato, o che venga letto come se l'avesse calcolato: le cifre nel testo sono citazioni di cifre già calcolate, e il testo è marcato come generato (§5.9).

## 9. Roadmap

La UI compare presto e cresce con il sistema, invece di essere l'ultimo strato. Motivo pratico: è l'unico modo per usare il sistema mentre lo si costruisce, e un sistema che si usa si finisce.

**Fase 0 — verifica del percorso di fetch.** *(fatta)*
Script usa e getta, fuori dall'architettura: autentica, chiama lista conti e transazioni, scrive il JSON grezzo su disco. Nessun parsing, nessuna persistenza strutturata.
*Fatto quando*: esistono su disco dump reali di almeno due istituti, con transazioni sia `BOOK` che `PDNG`. Da anonimizzare, diventano le fixture dei test di parsing.

**Fase 1 — ingest e ledger.** *(fatta)*
Schema a postings su SQLite. Modulo di integrazione Enable Banking riscritto o adattato contro le fixture della fase 0, che scrive direttamente nel ledger. Import degli export storici per il backfill (obiettivo: 24 mesi dove disponibili).
*Fatto quando*: l'assert sui saldi passa su ogni conto, reimportare un periodo già sincronizzato non genera duplicati, e una query risponde a "quanto è uscito davvero il mese scorso, esclusi giroconti".

**Fase 2 — riconciliazione, categorie, prima UI.** *(fatta)*
Transfer matching, normalizzazione merchant, regole deterministiche. UI minima: due schermate, la coda delle transazioni da confermare e la lista movimenti filtrabile. Backend FastAPI, frontend React, servito come PWA dietro Tailscale.
*Fatto quando*: si può categorizzare una settimana di movimenti dal telefono senza toccare il database a mano.

**Fase 3 — metriche e cruscotto.** *(fatta)*
Calcolo di burn ricorrente, accantonamento episodico, runway stressato, quota incomprimibile. Schermata di sintesi mensile. Editing degli split.

**Fase 4 — budget e affinamenti.** *(fatta)*
Budget mensili per categoria, anomalie su statistica robusta, classificatore statistico sulla coda, LLM per la normalizzazione dei merchant mai visti.

**Fase 5 — assistente.** *(fatta)*
La sezione di §5.9: una lettura in prosa delle serie e dei budget già calcolati, con proposte confermabili e nessuna aritmetica propria.
*Fatto quando*: davanti a un mese strano una schermata spiega cosa è cambiato citando solo cifre già calcolate, e almeno una proposta si conferma con un gesto.

Ogni fase è deployabile e usabile da sola. Nessuna fase richiede che la successiva esista per avere senso.

**Fase 6 — il sync si comanda, la nota si scrive, cancellare è possibile.** *(fatta)*
Un pulsante in cima all'app chiede i conti adesso e risponde con quello che ha
scritto, per conto; ogni movimento porta una nota locale che nessun percorso di
ingest scrive; un movimento si cancella davvero, e il tombstone che ne resta tiene
il sync dal rimetterlo, con una flag per conto che decide se può tornare e un
cestino che lo ripristina riga per riga; la verifica di §5.4 dice quando la
differenza è ciò che qualcuno ha cancellato. L'immagine si costruisce in CI a ogni
tag e il NAS la tira.
*Fatto quando*: un movimento appena fatto si legge dall'app senza aprire un
terminale; cancellare un movimento sbagliato non viene disfatto dal sync
successivo e il conto dice che la differenza è quella; un tag fa girare i test e
pubblica l'immagine (`linux/amd64`). Il primo deploy di quell'immagine sul NAS
resta lavoro aperto, perché nessuna immagine è ancora stata messa in esercizio lì.

**Fase 7 — il primo setup è guidato.** *(fatta)*
La configurazione si scrive dall'app (§5.10): credenziali Enable Banking con la
chiave privata incollata, istituto scelto fra quelli che il provider accetta,
conti da tenere con il nome che il ledger userà e la data da cui importarli,
primo sync con l'esito per conto, saldo dichiarato e apertura allineata. Gate al
primo avvio e sezione raggiungibile dopo, per aggiungere una banca o rinnovare un
consenso. Compose monta la cartella di configurazione, così un container appena
creato può far nascere `accounts.json`, e `/callback` torna nell'app invece di
rispondere JSON.
*Fatto quando*: un'installazione nuova arriva dall'app a un conto sincronizzato e
verificato senza toccare la riga di comando, e l'unico passo manuale che resta è
la registrazione della callback nel dashboard della banca.

**Fase 8 — il ledger si copia, e si torna indietro.** *(fatta)*
Snapshot datati e consistenti del ledger e della configurazione (§5.11): il comando che li scrive da dentro il container con l'API di backup di SQLite, la ritenzione che li tiene bounded, il ripristino scritto come procedura, e il cron sul NAS che li comanda. La stessa fetta porta una prova locale in container dell'intero primo avvio — l'immagine costruita dal checkout, la cartella di configurazione con la proprietà che ha il NAS, il wizard percorso contro una banca finta che serve le fixture anonimizzate — perché il primo avvio non si prova la prima volta sul NAS, e il ripristino non si prova la prima volta che serve.
*Fatto quando*: uno snapshot si rilegge come un ledger — `validate` passa, i conti e i movimenti ci sono — e la prova locale arriva dal wizard al ripristino senza toccare né una banca vera né il ledger vero.

**Stato (settembre 2026).** Fasi 0-8 consegnate, più il cruscotto con i grafici e la rinomina in AmonHen, la sezione Categorie e regole nell'app, le regole sul testo contenuto nella descrizione o su un'espressione fra barre, la gestione dei giroconti e la loro prova per IBAN, i filtri del cruscotto e la sezione Conti e budget con creazione dei conti e dichiarazione dei saldi. La fase 6 ha aggiunto il pulsante di sync nell'app, la nota locale di un movimento, la cancellazione con il suo tombstone, la flag di reimport per conto e il cestino che ripristina, e la §5.4 che spiega la differenza lasciata da una cancellazione a mano. L'assistente di §5.9 è configurato e ha risposto alla sua prima domanda vera, e il modello si accende da `.env`, che ora è letto all'avvio sia da `uv run` sia da docker compose. La fase 7 ha aggiunto il setup guidato di §5.10 e la configurazione che l'app scrive da sé, con la cartella di configurazione montata al posto dei due file. L'immagine la costruisce la CI: un tag `v*` fa girare i test e la build del bundle, poi pubblica su GHCR (`linux/amd64`), e il NAS tira l'immagine con il suo `AMONHEN_TAG` invece di costruire dal sorgente — il NAS non ha bisogno del repository. L'immagine e pubblicata: il tag `v1.3.0` ha fatto girare test e build del bundle, poi la CI l'ha costruita per linux/amd64 e messa su GHCR. La fase 8 ha aggiunto la copia che non c'era — snapshot datati e consistenti del ledger e della configurazione, con la ritenzione, il ripristino e il cron che li comanda (§5.11) — e la prova locale in container dell'intero primo avvio: la banca finta che risponde dalle fixture, il wizard percorso davvero, lo snapshot e il ritorno dallo snapshot, così il primo avvio e il ripristino non si provano la prima volta sul NAS. Lavoro aperto, tracciato nel backlog: il primo deploy sul NAS di quell'immagine e il consenso di Fineco da rinnovare.

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
| Il testo dell'assistente viene letto come un calcolo | Le cifre nella prosa sono citazioni delle serie del backend, il testo è marcato come generato (§5.9), e una lettura che citi una cifra non calcolata viene rifiutata invece che mostrata |
| Dati finanziari personali a un fornitore terzo | Passano solo aggregati, merchant normalizzati e nomi di categoria: nessun IBAN, nessun payload grezzo, e la funzione si può tenere spenta (§5.9) |
| Un merchant che si chiama come un'istruzione | Le descrizioni entrano come dati, e l'unica risposta accettata è quella che rispetta lo schema: merchant e categorie già noti (§5.9) |
| Costo e latenza che scivolano | Domanda limitata, chiamate contate, nessuna ripetizione della stessa domanda sugli stessi dati, e l'assistente fuori dal percorso del sync (§5.9) |
| Un rimborso gonfia le Entrate (giugno 2026: cinque accrediti che erano denaro altrui contati come le entrate del mese) | Si dichiara, come il giroconto verso un conto proprio: la voce esce dalle entrate e resta visibile a parte. La coppia con l'addebito compensato non si modella, perché la contabilità viva non ne mostra nessuna |
| La chiave privata Enable Banking passa dall'app: si incolla in un campo e il server la scrive su disco | Il traffico è quello del tailnet e basta (§4: nessuna esposizione pubblica); la chiave non torna mai in una risposta e non finisce nei log, e il campo mostra solo se una chiave c'è e se si carica. Resta possibile metterla a mano dove `pem_path` la indica |
| Un setup interrotto a metà lascia una configurazione incompleta | Lo stato si rilegge da `/api/setup` e ogni passo è riprendibile; una scrittura rifiutata non tocca il file, quindi una chiave sbagliata non sostituisce una buona, e `/connect` con la configurazione incompleta dice cosa manca invece di fallire |
