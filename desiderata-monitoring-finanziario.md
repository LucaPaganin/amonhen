# Desiderata — AmonHen, sistema di monitoring finanziario personale

Versione 0.6 — settembre 2026

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
pacchetto `amonhen`, variabili `AMONHEN_*`, database `amonhen.db`.*

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

- Idempotenza: `external_id` del provider quando presente, con fallback `hash(data, importo, descrizione, conto)`. L'export CSV non contiene l'`external_id`, quindi il fallback è il solo discriminante nella zona di sovrapposizione tra i due percorsi: va testato esplicitamente reimportando un periodo già sincronizzato e verificando che il conteggio non cambi.
- Un adattatore per formato di export, che normalizza verso lo schema comune. I formati differiscono per istituto (colonne, segno dell'importo, formato data, separatore decimale).
- Gestione della transizione pending → booked senza duplicare la transazione.
- Payload grezzo conservato integralmente, con indicazione del percorso di provenienza, per poter riprocessare senza ri-fetchare né ri-scaricare.
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

### 5.5 Categorizzazione

Pipeline a cascata, dal deterministico al probabilistico:

1. Normalizzazione del merchant (stringa grezza → nome pulito), usata dalle proposte e dal classificatore; le regole lavorano sulla descrizione.
2. Regole su un testo contenuto nella descrizione del movimento — una regola copre una famiglia di movimenti, non un solo nome. Copertura attesa 80-90%.
3. Classificatore statistico leggero (logistica su char n-gram) sulla parte restante.
4. LLM solo sulla coda: transazioni mai viste, in batch asincrono, output sempre marcato "da confermare".

Nessuno stadio scrive una categoria definitiva senza che sia rivedibile. Nessuno stadio è bloccante per il sync.

### 5.6 Metriche esposte

Solo queste, in ordine di priorità:

- **Burn ricorrente**: mediana mobile a 6 mesi delle spese non episodiche.
- **Accantonamento episodico**: somma one-off ultimi 24 mesi / 24. Gli eventi rari non vanno rimossi, vanno modellati come processo separato con frequenza propria.
- **Burn atteso** = burn ricorrente + accantonamento episodico.
- **Runway stressato** = liquidità / burn atteso. La rata del mutuo non è più una voce fissa del denominatore: un pagamento del mutuo è un movimento come gli altri, e se deve contare sta in una categoria.
- **Quota incomprimibile vs discrezionale**: quanto sarebbe tagliabile se servisse.
- **Flusso di risparmio**: trasferimenti verso conti di investimento. È l'unico ponte tra monitoring delle spese e monitoring del patrimonio. PAC, contributi al fondo pensione e TFR non sono spese.

Il cruscotto mostra tre serie osservate — spesa per categoria (con la fetta "senza categoria" in evidenza), entrate e uscite per mese, patrimonio osservato — e i grafici non fanno aritmetica: ogni serie si calcola nel backend, così una torta non può risultare più piccola del denaro che è uscito. Il cruscotto si filtra per periodo, per conti e per categoria, e i tre filtri non pesano uguale: il **periodo** decide cosa mostrano grafici e serie; i **conti** restringono tutto ciò che è di conto — le spese attribuite al conto che le ha pagate, la liquidità, il risparmio, il patrimonio; la **categoria** restringe solo le spese, perché una categoria non descrive il denaro che entra né quello che i conti valgono. Le card di §5.6 non seguono il periodo: le loro finestre di 6 e 24 mesi sono la definizione della metrica, non una vista, e ogni card dichiara la finestra che ha usato. Un filtro si applica nel backend, mai nel browser.

Conti e budget si gestiscono da una sezione dell'app, non dal cruscotto: l'elenco dei conti con saldo, figura iniziale ed esito della verifica, la dichiarazione di un saldo letto dalla banca, l'allineamento del saldo iniziale perché l'invariante di §5.4 torni a valere, la creazione di un conto reale a mano (il broker, o una banca non collegata), il budget mensile di ogni categoria e i flag delle categorie.

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

**Dove sta.** Una sezione propria, e i punti di ingresso dove la domanda nasce da sola: una card del cruscotto, una riga della coda, un budget sforato. L'ingresso contestuale passa *quella* serie o *quel* movimento, invece di chiedere alla persona di ricomporre il contesto in una frase.

*Fatto quando*: davanti a un mese strano si ottiene in una schermata una spiegazione che cita solo cifre già calcolate e almeno una proposta confermabile con un gesto; e la stessa domanda sugli stessi dati non viene richiesta due volte.

## 6. Modello dati minimo

```
accounts             (id, nome, tipo: reale|virtuale|categoria, istituto, iban, uid_esterno, valuta,
                      saldo_iniziale, data_iniziale, flag: episodico | incomprimibile | investimento)
transactions         (id, conto, data, importo, descrizione, stato BOOK|PDNG, external_id, content_hash,
                      origine psd2|import, payload_grezzo, controparte, conto_controparte)
postings             (id, transaction_id, account_id, importo, note)
transfer_links       (leg_a, leg_b, confidenza, metodo, confermato_da_umano: 1 confermato, 0 da rivedere, -1 rifiutato)
rules                (chiave, testo, categoria)
account_balances     (conto, data, saldo, origine)
budgets              (categoria, importo, aggiornato_il)
merchant_suggestions (merchant, categoria, origine, decisione: pending | accepted | dismissed)
settings             (chiave, valore)
```

Vincolo di integrità: per ogni `transaction_id`, `SUM(postings.importo) = 0`.

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

**Esito (settembre 2026).** La strumentazione è su `main` in un commit dedicato e il lavoro sta su un branch; il percorso Actual è uscito dal branch; il livello che parla con Enable Banking è un modulo interno (`providers/`), scritto contro le fixture anonimizzate della fase 0. Il prodotto si chiama AmonHen, e dal 2026 anche i confini lo dicono: il pacchetto è `amonhen`, le variabili sono `AMONHEN_*`, il database è `amonhen.db`. La cartella del repo resta `bank-connector`, che è il nome che l'ha ospitato prima che il prodotto avesse il suo.

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

**Stato (settembre 2026).** Fasi 0-4 consegnate, più il cruscotto con i grafici e la rinomina in AmonHen, la sezione Regole nell'app, le regole sul testo contenuto nella descrizione, la gestione dei giroconti e la loro prova per IBAN, i filtri del cruscotto e la sezione Conti e budget con creazione dei conti e dichiarazione dei saldi. Lavoro aperto, tracciato nel backlog: la prima chiamata vera al modello (la chiave è dell'utente, e senza quella la sezione resta spenta), l'immagine da provare sul NAS, e il branch da portare su `main`.

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
