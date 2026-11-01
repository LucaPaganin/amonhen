# Storia di `desiderata-monitoring-finanziario.md`

Le voci di versione più vecchie e il dettaglio delle fasi concluse, spostati dalla specifica senza cambiarli. Le regole vive stanno nella specifica: questo file dice come ci si è arrivati.

## Versioni

*0.1 · prima stesura. 0.2 · allineamento al costruito: fasi 0-4 e cruscotto
consegnati, regole sul testo contenuto nella descrizione, giroconti visibili e
gestibili, invariante della sezione 5.4 esposta per figura, rata del mutuo rimossa.
0.3 · filtri del cruscotto (periodo, conti, categorie) e sezione Conti e budget,
con creazione di un conto e dichiarazione dei saldi dall'app.
0.4 · la prova dei giroconti è l'IBAN che ciascuna banca stampa sulla propria
gamba, e l'IBAN del conto si legge dall'endpoint dei dettagli; le cinque sezioni
si raggiungono dalla barra in basso o dal menu in alto, che le nomina per esteso
e dice cosa contengono. Le due vie sono una decisione: la barra cambia sezione
con un tocco, il menu sta dove una quinta parte di schermo non arriva.
0.5 · l'assistente della sezione 5.9 è specificato — una lettura in prosa dei numeri
calcolati altrove, con proposte confermabili e nessuna aritmetica propria — e la
ri-autorizzazione di un conto rinfresca la voce che ha già invece di accodarne
una seconda.
0.6 · l'assistente della sezione 5.9 è costruito, con i suoi guardiani in codice; il denaro
che non è né spesa né entrata si dichiara invece di indovinarlo (sezione 5.3), comprese
le quote della cointestata e i rimborsi; i confini rimasti sono rinominati —
pacchetto `amonhen`, variabili `AMONHEN_*`, database `amonhen.db`.
0.7 · la coda dice cosa una proposta decide — quanto denaro, su quanti movimenti e
quando — e le regole si presentano raggruppate per la categoria che assegnano.
Il modello della sezione 5.9 è configurato e ha risposto alla sua prima domanda vera: `.env`
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
GitHub e la cartella locale sono `amonhen`, non più `bank-connector`, e la sezione 7
perde la frase che diceva il contrario.
1.3 · la fase 6: il ledger si aggiorna da un pulsante nell'app invece che da un
terminale, un movimento porta una nota locale che il sync non tocca, si cancella
davvero — con il tombstone che tiene il sync dal rimetterlo, una flag per conto
che decide se può tornare e un cestino che lo ripristina — e la sezione 5.4 spiega la
differenza che una cancellazione lascia invece di gridare mismatch. L'immagine
la costruisce la CI su un tag, e il NAS la tira: non ha più bisogno del repo.*
*1.4 · il primo setup è guidato dall'app (sezione 5.10): le credenziali Enable Banking
— chiave privata incollata compresa —, l'istituto scelto fra quelli che il
provider accetta invece che a memoria, i conti da tenere con il nome che il
ledger userà, il primo sync con l'esito per conto e il saldo dichiarato che fa
passare la sezione 5.4 da `non verificato` a `verificato`. La schermata è un gate al
primo avvio e resta raggiungibile dopo, perché un consenso scade e una banca si
aggiunge. Compose monta la cartella di configurazione e non i due file, così un
container appena creato può far nascere `accounts.json`; `/callback` torna
nell'app invece di rispondere JSON grezzo.*
*1.5 · il backup smette di essere una cosa che non c'era (sezione 5.11): snapshot datati
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
— le due vie della sezione 0.4 restano quelle del telefono, che sotto i 1024 px è ancora la
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
*1.10 · una chiamata al modello parte solo da un tocco. L'ingresso dal budget
(«Regge?», sezione 5.9) apriva la sezione e chiedeva da sé, mentre la schermata si
disegnava: una chiamata esterna spesa senza che nessuno l'avesse chiesta e senza
che si vedesse. Ora la domanda che il contesto compone arriva pronta, con il
pulsante che la manda e uno che la lascia cadere, il modello si nomina mentre la
richiesta è in volo, e la lettura continua a dire se è nuova o già avuta — e una
chiamata che non riesce non porta via la domanda composta. È la regola della sezione 8
scritta dove il prodotto la può rispettare: nessun effetto, nessun timer e nessun
giro automatico chiede al modello al posto della persona.*
*1.11 · accettare una proposta decide i movimenti e non scrive una regola se non
la si chiede. Una regola per ogni accettazione era una regola per ogni modo in cui
una banca stampa lo stesso esercente, e il loro numero cresceva con la coda invece
che con le decisioni prese: ora la casella che la chiede è spenta quando la coda si
apre, e quando la si accende il testo della regola si edita in un dialogo —
precompilato con il nome del merchant, che è un punto di partenza e non la regola.
Quello che l'accettazione senza regola scrive è una decisione della persona, e le
regole non la sovrascrivono: è ciò che rende la casella spenta una scelta invece di
un rinvio.*
*1.12 · il budget si pianifica mese per mese e ha una sezione sua. L'importo di
una categoria era uno solo, uguale per tutti i mesi, e cambiarlo riscriveva anche
i mesi passati: ora è un default che vale da un mese in avanti, che un mese può
sovrascrivere per sé, e i mesi già vissuti tengono il tetto che avevano. Dentro
il tetto si possono scrivere delle voci — descrizione, importo, data facoltativa,
priorità essenziale / importante / rimandabile — scritte da zero, copiate da un
movimento passato o dal mese prima, e sempre modificabili; quando superano il
tetto la sezione dice quali ci stanno, a partire dalle essenziali, e non sceglie
cosa tagliare. Lo speso resta per categoria: una voce non si collega al
movimento che la realizza. Conti e budget si separano: la sezione Conti tiene i
conti, la sezione Budget la pianificazione (sezione 5.12).*

*1.13 · le metriche si chiamano con parole che dicono cosa misurano: spesa
mensile tipica, riserva per spese rare, spesa mensile attesa, mesi di autonomia,
spesa irrinunciabile e tagliabile, investito — al posto di burn, runway,
accantonamento episodico, quota incomprimibile e discrezionale, flusso di
risparmio. I flag delle categorie diventano *spesa rara* e *irrinunciabile*.
L'app, l'assistente e questo file usano gli stessi nomi; i nomi interni del
codice e dell'API restano quelli di prima. Una sezione si scrive con la parola,
non con il simbolo.*

*1.14 · una regola fa una cosa a certe condizioni: oltre ad assegnare una
categoria può cancellare i movimenti — quelli che ci sono, dopo averli mostrati, e
quelli che arriveranno — o registrarli come giroconto verso una destinazione, e si
restringe a un conto e a un intervallo di importi (sezione 5.5). La regola chiesta
da un movimento aperto si scrive in un dialogo, come quella chiesta da una
proposta, invece di nascere in silenzio con il nome del merchant. Un conto si
elimina con i suoi movimenti, e se è collegato a una banca il sync smette di
chiederlo; i movimenti di una pagina si scelgono tutti insieme, per cancellarli o
dar loro una categoria.*
*1.15 · un conto collegato si sincronizza anche su un periodo scelto, passato
compreso (sezione 5.1): finestra per finestra, ciascuna con quello che la banca ha
restituito o l'errore con cui l'ha rifiutata, una larghezza di finestra per conto
che si dimezza quando la banca rifiuta l'intervallo, e le finestre riuscite scritte
anche se un'altra fallisce. Il cursore della sync incrementale e `start_sync_date`
non si spostano. Un movimento che somiglia a uno importato da file — stesso conto,
giorno e importo, descrizione diversa — non si scrive: aspetta che una persona lo
scriva o lo scarti, perché l'impronta di contenuto non distingue una descrizione
riformulata da un secondo movimento.*
*1.16 · l'app dice quale rilascio si sta guardando: in fondo al menu e al rail c'è
la versione del bundle, e accanto quella del server quando le due non coincidono
— il bundle si legge dal disco mentre il processo gira il suo codice, quindi
possono differire.*
*1.17 · una regola di giroconto può puntare a un conto reale creato a mano: per un
conto che nessuna banca espone — il conto deposito di Revolut — la regola scrive
sul conto il movimento opposto e li collega come giroconto confermato, così i
giroconti escono da spese ed entrate in blocco e il conto ha i suoi movimenti. Un
conto può dire che il suo saldo è quello calcolato dai movimenti: patrimonio e
saldi lo leggono così, e un saldo dichiarato su di lui resta la verifica della
sezione 5.4. Prima una destinazione non poteva essere un conto reale, e il
patrimonio era solo osservato.*

*1.18 · una proposta mostra i movimenti che decide — giorno, conto, importo e
descrizione della banca — e non solo il totale: un nome non basta per dire sì, il
giorno e l'importo sono ciò che si riconosce. Prima l'elenco su desktop mostrava il
solo nome, e i movimenti non si vedevano da nessuna parte. La verifica di un conto
dice «non torna sui sospesi» o «sul contabile» solo se l'altra figura è stata
dichiarata e torna: Revolut dichiara solo il disponibile, e ogni sua differenza si
leggeva come un problema di sospesi anche senza sospesi.*

*1.19 · il saldo iniziale è un punto fisso, e il ricalcolo dice cosa sposta. Un conto
collegato lo prende dalla banca al primo sync, dalla figura contabilizzata se c'è, e
da lì non si muove più da solo; ricalcolarlo è un'azione chiusa in fondo al pannello,
che prima di scrivere mostra di quanto cambia e avverte che quella differenza non
verrà più segnalata. Una verifica che non torna mostra invece quanto manca e gli
ultimi movimenti del conto. Prima *Allinea il saldo iniziale* stava accanto a ogni
controllo: premuto su un rosso lo faceva tornare verde per costruzione, e due pedaggi
che Revolut aveva già tolto dal disponibile senza esporli finirono nel saldo iniziale e
furono contati due volte quando arrivarono.
1.20 · i conti virtuali si vedono. In fondo a **Conti** c'è l'elenco dei conti in cui è
finito il denaro che non è né spesa né entrata — una casa comprata, un versamento
sbagliato e ripreso — con il saldo, il numero di movimenti e i movimenti stessi a
richiesta; il conto di clearing resta fuori, perché pareggia una coppia e non è un posto
dove il denaro va. Prima un giroconto verso un conto non collegato usciva dalla spesa e
non si ritrovava più. E l'import CSV ripara le lettere accentate che un export ha scritto
due volte codificate ("PiÃ¹Me" per "PiùMe"), come fa l'estratto italiano di Revolut: la
stessa spesa via PSD2 ha le lettere giuste, e l'impronta che le confronta non coincideva.
1.21 · il broker ha un valore, e il rendimento è un movimento. Un conto d'investimento
creato a mano si aggiorna con *Aggiorna il valore* in **Conti**, o leggendo gli estratti
PDF di Scalable in **Importa**: la differenza tra il valore e il saldo dei movimenti è
scritta come un movimento verso il conto virtuale *Rendimento investimenti*, e il valore
diventa il saldo dichiarato. Prima il saldo dichiarato a mano restava rosso per tutto
quello che il mercato aveva fatto, e riallinearlo nascondeva il rendimento nel saldo
iniziale.
1.22 · niente lettore dei PDF di Scalable. Leggere gli estratti ogni trimestre era più
lavoro di quanto valga una curva del patrimonio: tra una rivalutazione e l'altra il
broker vale quanto ci è stato versato, che le regole dei giroconti tengono aggiornato da
sole, e il valore si scrive a mano quando serve — almeno a fine anno, per la
dichiarazione.
1.23 · l'app risponde a due domande: dove sono finiti i soldi, e come va questo mese
rispetto al solito. Il cruscotto comincia da lì, le altre cifre stanno sotto *Dettagli*, la
navigazione ha cinque voci più *Gestione*, e una riga mostra un dato forte e l'azione
frequente: il resto è dietro *Dettagli*. Il broker non si traccia più: il suo conto tiene
solo la liquidità, dichiarata a mano, e il portafoglio finisce nel conto virtuale
*Investimenti*, senza valore di mercato; sparisce *Investito* e sparisce lo scopo fiscale.
La liquidità era gonfiata dal portafoglio. I tag si mettono a mano o con una regola e
contano nei calcoli: una spesa è rara o irrinunciabile per la sua categoria o per un suo
tag, con una definizione sola. **Movimenti** nasconde di base giroconti e interessi. Le
anomalie partono da 100 €, lasciano fuori cambi valuta e spese rare, e si leggono senza
statistica. C'è una **Guida** con i concetti, e le pagine perdono i paragrafi che spiegavano.
1.24 · *Dove sono finiti* mostra le categorie con una spesa nel mese, dalla più alta, e sotto
ciascuna scrive in parole la distanza dal solito; il solito ha la sua scheda nella Guida.
1.25 · la spesa è al netto dei rimborsi: un accredito in una categoria che non è *Entrata*
abbassa quella categoria. Cade la frase per cui la categoria compensata restava com'era.
1.26 · esiste il *contributo alle spese*, denaro che copre tutte le spese e non una: abbassa
il totale e nessuna categoria, quindi spesa tipica, spesa attesa e autonomia ne sono al netto,
e irrinunciabile e tagliabile scendono in proporzione sul conto su cui arriva. Ogni categoria
può avere una descrizione.*

## Fasi concluse

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
Calcolo di spesa mensile tipica, riserva per spese rare, mesi di autonomia, spesa irrinunciabile. Schermata di sintesi mensile. Editing degli split.

**Fase 4 — budget e affinamenti.** *(fatta)*
Budget mensili per categoria, anomalie su statistica robusta, classificatore statistico sulla coda, LLM per la normalizzazione dei merchant mai visti.

**Fase 5 — assistente.** *(fatta)*
Quanto descritto nella sezione 5.9: una lettura in prosa delle serie e dei budget già calcolati, con proposte confermabili e nessuna aritmetica propria.
*Fatto quando*: davanti a un mese strano una schermata spiega cosa è cambiato citando solo cifre già calcolate, e almeno una proposta si conferma con un gesto.

**Fase 6 — il sync si comanda, la nota si scrive, cancellare è possibile.** *(fatta)*
Un pulsante in cima all'app chiede i conti adesso e risponde con quello che ha
scritto, per conto; ogni movimento porta una nota locale che nessun percorso di
ingest scrive; un movimento si cancella davvero, e il tombstone che ne resta tiene
il sync dal rimetterlo, con una flag per conto che decide se può tornare e un
cestino che lo ripristina riga per riga; la verifica della sezione 5.4 dice quando la
differenza è ciò che qualcuno ha cancellato. L'immagine si costruisce in CI a ogni
tag e il NAS la tira.
*Fatto quando*: un movimento appena fatto si legge dall'app senza aprire un
terminale; cancellare un movimento sbagliato non viene disfatto dal sync
successivo e il conto dice che la differenza è quella; un tag fa girare i test e
pubblica l'immagine (`linux/amd64`). Il primo deploy di quell'immagine sul NAS
resta lavoro aperto, perché nessuna immagine è ancora stata messa in esercizio lì.

**Fase 7 — il primo setup è guidato.** *(fatta)*
La configurazione si scrive dall'app (sezione 5.10): credenziali Enable Banking con la
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
Snapshot datati e consistenti del ledger e della configurazione (sezione 5.11): il comando che li scrive da dentro il container con l'API di backup di SQLite, la ritenzione che li tiene bounded, il ripristino scritto come procedura, e il cron sul NAS che li comanda. La stessa fetta porta una prova locale in container dell'intero primo avvio — l'immagine costruita dal checkout, la cartella di configurazione con la proprietà che ha il NAS, il wizard percorso contro una banca finta che serve le fixture anonimizzate — perché il primo avvio non si prova la prima volta sul NAS, e il ripristino non si prova la prima volta che serve.
*Fatto quando*: uno snapshot si rilegge come un ledger — `validate` passa, i conti e i movimenti ci sono — e la prova locale arriva dal wizard al ripristino senza toccare né una banca vera né il ledger vero.

**Fase 9 — il budget si pianifica.** *(fatta)*
Quanto descritto nella sezione 5.12: un tetto per categoria e per mese con il suo default, le voci dentro il tetto con data e priorità, la copia da un movimento passato o dal mese prima, e i mesi passati che restano quello che erano.
*Fatto quando*: il mese prossimo si pianifica dall'app e cambiare un default non riscrive i mesi già vissuti.

**Fase 10 — si vede l'essenziale.** *(consegnata, v1.10.0)*
Le decisioni della versione 1.23. Il cruscotto risponde alle due domande, una riga di ogni pagina mostra un dato forte e l'azione frequente, la navigazione è una sola su telefono e PC — Dashboard, Da confermare, Movimenti, Budget, Conti, e *Gestione* per Categorie e regole, Importa, Assistente, Configurazione e Guida. La pagina **Budget** non cambia. **Movimenti** nasconde di base giroconti e interessi del deposito e dice quanti sono; **Da confermare** perde le sezioni vuote e le etichette uguali su ogni riga, e ogni data dice l'anno quando non è quello corrente. La citazione resta in fondo al menu, non in cima a ogni pagina. Tag, broker e anomalie come nelle sezioni 5.13, 5.8 e 5.7.
*Fatto quando*: aperta l'app, dove sono finiti i soldi e come va il mese si leggono senza scorrere; la liquidità non contiene il portafoglio; una spesa rara per tag cambia la riserva e la spesa tipica; le correzioni al ledger reale sono provate su una copia.

## La sezione 5.9 quando c'era

L'assistente, tolto nella versione 1.38, com'era specificato.

### 5.9 Assistente *(costruita)*

Una sezione dell'app che discute i numeri che il backend ha già calcolato — spese, budget, patrimonio, coda — e le proposte che ne derivano. Non è una chat generica sul mondo, e non è un secondo motore di calcolo.

**Cosa fa.** Riceve una domanda, o un contesto che la contiene già, insieme ai dati *già calcolati* che servono a rispondere: le serie del cruscotto, i totali, le categorie, i budget, e i movimenti che li compongono. Restituisce una lettura in prosa: perché questo mese è diverso, cosa ha spinto la spesa, quale categoria sta scivolando, se quel budget regge, da dove cominciare nella coda. Può anche **proporre**: una categoria per un merchant che nessuna regola copre (la strada che esiste dalla sezione 5.5), un budget mensile per una categoria che non ne ha, una regola da scrivere quando lo stesso merchant torna tre volte.

**Come tratta i numeri.** L'unica aritmetica ammessa è quella del backend. L'assistente non somma, non stima, non arrotonda a occhio: cita le cifre che riceve, e ogni cifra che compare nella sua prosa è una di quelle. Un numero che non è nella risposta dell'API non può comparire nel testo; se serve, si calcola prima e si passa dopo. Non è un proposito: la lettura si confronta cifra per cifra con quelle passate — separatori italiani e date comprese — e una che ne citi un'altra si rifiuta, si registra e non si mostra. Il testo generato è marcato come tale nell'interfaccia, così una cifra dentro una frase non viene mai letta come una cifra calcolata — è la stessa regola della sezione 8, vista dal lato di chi legge.

**Cosa non può fare.** Non scrive nel ledger: nessuna categoria, nessun budget, nessuna regola, nessuno split, nessun giroconto. Ogni sua proposta è una riga da confermare con lo stesso gesto delle proposte della sezione 5.5, e finché non è confermata non cambia niente. Non gira nel percorso del sync (sezione 8). Non risponde con SQL: le query restano scritte a mano. Non vede identificativi: niente IBAN, niente numeri di conto, niente nomi di controparte che non siano già il merchant normalizzato, e il payload grezzo non esce dalla macchina.

**Come si difende dagli input.** Le descrizioni dei movimenti sono testo che arriva da fuori: un merchant può chiamarsi come un'istruzione. Entrano quindi come dati, dentro la struttura della domanda, e l'unica risposta accettata è quella conforme a ciò che è stato chiesto — merchant che erano nella domanda, categorie che esistono, campi dello schema previsto. Una risposta fuori schema si scarta, si registra, e non si esegue.

**Come si controlla.** Il modello è configurazione, non codice: endpoint, nome e chiave stanno nell'ambiente, e la specifica non fissa un fornitore. Ogni chiamata ha un tetto: la domanda è limitata (i merchant sono al massimo venti, le serie sono quelle del cruscotto), le chiamate sono contate, la stessa domanda sugli stessi dati non si ripete, e l'impronta che lo decide è quella delle figure — non dell'elenco dei merchant già proposti, che cambia proprio perché l'assistente ha risposto, e un rifiuto o un timeout sono un messaggio per la persona — nessuna funzione dell'app dipende dall'assistente, e senza configurazione la sezione dice che è spenta invece di fallire. **Nessuna chiamata parte da sola**: ogni punto di ingresso compone la domanda e la manda un tocco, perché una chiamata esce dalla macchina verso un fornitore esterno ed è contata, non un effetto di una schermata che si disegna; mentre la richiesta è in volo la schermata nomina il modello, e la lettura che torna dice se è nuova o già avuta. Una chiamata che non riesce non porta via la domanda composta: resta al suo posto, con il motivo dell'errore accanto, e si riprova. Ciò che si chiede e ciò che torna si registra, con il modello usato e l'impronta dei dati passati, così una lettura si può rileggere fra sei mesi sapendo su cosa era basata.

**Dove sta.** Una sezione propria, raggiungibile dal menu, e i punti di ingresso dove la domanda è già composta: la riga di un budget che sta per saltare, che passa *quel* budget invece di chiedere alla persona di ricomporre il contesto in una frase — la domanda arriva pronta sulla schermata, e aspetta il tocco che la manda. Un ingresso generico dal cruscotto c'è stato e non serve: una domanda senza contesto è una domanda che nessuno fa, e la sezione basta a sé.

*Fatto quando*: davanti a un mese strano si ottiene in una schermata una spiegazione che cita solo cifre già calcolate e almeno una proposta confermabile con un gesto; e la stessa domanda sugli stessi dati non viene richiesta due volte.
