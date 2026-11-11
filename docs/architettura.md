# Architettura del backend — valutazione e forma di arrivo

Novembre 2026, sul `main` a `d2f7aa6`. È una valutazione, non una regola: nessun
requisito della specifica cambia, e niente di quello che descrive è ancora nel codice.

## 1. Quale pattern

### Esagonale (ports & adapters) per intero: è troppo

L'esagonale paga quando il dominio deve sopravvivere a più tecnologie intercambiabili
(più database, più trasporti, più fornitori) e quando i test del dominio vanno fatti
senza infrastruttura. Qui:

- **Il database è uno e non cambierà.** SQLite è una scelta di prodotto (un file, uno
  snapshot, un NAS), non un dettaglio. Un `TransactionRepository` astratto davanti a un
  solo SQLite sarebbe un'interfaccia con un'implementazione sola, per sempre.
- **Una parte del dominio è scritta in SQL, ed è giusto così.** `SPENDING_SQL`,
  `RARE_SQL`, `ESSENTIAL_SQL`, `CONTRIBUTION_SQL`, `CREDITS_WHERE` sono le definizioni
  uniche di cosa è spesa, raro, essenziale. Nell'esagonale "puro" andrebbero tirate fuori
  dalla persistenza e riscritte in Python sopra righe caricate in memoria: si
  perderebbero la definizione unica e le prestazioni, per una purezza che nessuno
  userebbe.
- **Un utente, un processo, un trasporto e mezzo** (FastAPI e la CLI). Non c'è un
  secondo cliente del dominio che giustifichi un core isolato da tutto.
- **La specifica stessa lo dice** (sezione 10, *Deriva verso l'over-engineering*): ogni
  cosa nuova deve rispondere a "quale decisione mi fa cambiare?". Uno strato di
  repository astratti non cambia nessuna decisione.

### Quello che calza: monolite modulare, *functional core / imperative shell*, porte solo ai bordi veri

Tre idee, ognuna presa per quello che risolve qui:

1. **Functional core, imperative shell.** Il calcolo (dedup, matching, normalizzazione,
   corrispondenza delle regole, aritmetica di metriche e budget) è puro e prende dati;
   la shell legge dal ledger, chiama il core, scrive. Il codice lo fa già in buona parte
   (`matching`, `dedup`, `eb_normalize`, gli adapter CSV/OFX sono puri).
2. **Uno strato di casi d'uso (application services)** fra il trasporto e il ledger.
   È il pezzo che manca davvero: oggi la sequenza "scrivi → regole di giroconto →
   abbina → passthrough → valida → categorizza" è ricostruita a mano da ogni chiamante
   (vedi 2.2).
3. **Porte esagonali solo dove esiste davvero un "fuori" che cambia:** la banca
   (Enable Banking oggi, la fixture-stub nei test, forse un'altra domani), il modello
   LLM, il file di configurazione, l'orologio. Lì un `Protocol` costa dieci righe e
   compra test senza `responses` e un secondo provider senza toccare `sync.py`.

Il ledger resta quello che è: un **table data gateway con le invarianti dentro** — non un
repository astratto — e va solo spezzato per sotto-dominio. In gergo è un "esagonale
leggero" o *pragmatic clean architecture*: le dipendenze puntano verso l'interno, ma
l'interno include SQL.

## 2. Il codice di oggi

### 2.1 Cosa è già buono

- **Le regole di business hanno una definizione sola** (i frammenti SQL in `ledger.py`)
  e tutti i lettori — metriche, grafici, budget, coda — la usano.
- **I bordi d'ingresso sono puri**: `eb_normalize`, `csv_adapter`, `ofx_adapter`
  producono `IncomingTransaction` senza toccare il database. È già la forma di un
  adapter esagonale.
- **`SyncService` riceve il client** invece di costruirlo, e accetta `today`: testabile
  senza rete.
- **Denaro come `Decimal`** dall'ingresso alla somma; le somme si fanno in Python, mai in
  `REAL`.
- **Invarianti verificate** (`validate`, `unbalanced`, il controllo della sezione 5.4 nel
  sync) invece che sperate.
- **Una transazione per batch** (`deferred_commits`): un'operazione grande o riesce o non
  lascia niente a metà.
- **Test**: ~11k righe, fixture da payload reali anonimizzati, la suite gira da un albero
  pulito. È ciò che rende possibile qualunque refactoring descritto sotto.

### 2.2 Dove si rompe

**a. La sequenza dopo l'ingest è scritta cinque volte, e i percorsi hanno già
divergito.**

|Chiamante|regole di giroconto prima|`link_transfers`|passthrough|`validate`|`categorize`|
|---|---|---|---|---|---|
|`SyncService.run` / `settle` (`sync.py:185`, `:314`, `:321`)|sì|sì|sì|sì|sì|
|`SyncService.run_period` (`sync.py:283`)|sì|sì|sì|sì|sì|
|import dall'app (`api.py:2019`)|**no**|sì|sì|sì|sì|
|`import` da CLI (`cli.py:619`)|**no**|sì|sì|sì|sì|
|decisione su un doppione trattenuto (`api.py:1965`)|**no**|sì|sì|**no**|sì|

La versione 1.34 della specifica vuole che una regola di giroconto si applichi *prima*
dell'abbinamento (sezione 5.3), e `apply_transfer_rules` lo spiega: una gamba che il
matcher ha già abbinato non è più di nessuna regola. Sull'import e sulla decisione di un
trattenuto, `categorize` applica le regole di giroconto *dopo* `link_transfers`: un
importo uguale su un altro conto può prendersi un giroconto che una regola nominava. Va
verificato con un test, ma la struttura lo permette — ed è esattamente il tipo di
deriva che un caso d'uso unico rende impossibile.

**b. `api.py` è il secondo dominio.** 2.735 righe, 74 route dentro una sola chiusura
`create_app`, 22 query SQL scritte negli handler (`api.py:779`, `:1340`, `:1391`,
`:1412`, `:1436`, …), la configurazione riletta dal disco e il client Enable Banking
costruito dentro le route (`_client(config)`). Una regola nuova (per esempio la fase 12,
sezione 5.16) oggi finirebbe lì, e la CLI dovrebbe riscriverla.

**c. `Ledger` è un god object.** 1.984 righe, circa 130 metodi: ingest e dedup,
trattenuti, cancellazioni e cestino, tag, split, flag di categoria, giroconti e mirror,
saldi dichiarati e apertura, settings, proposte. Le invarianti stanno bene in un posto
solo; dieci sotto-domini in una classe no: ogni modifica rilegge tutto.

**d. Le dipendenze verso il fuori non sono invertite in modo uniforme.**
`sync.py` importa `EnableBankingClient`, `RateLimitedError`, `ConsentExpiredError`
dal provider concreto; `dt.date.today()` / `datetime.now()` compaiono in 8 moduli
(11 volte solo in `api.py`); `load_config` è chiamato da route, CLI e sync.

**e. Le migrazioni non hanno versione.** `initialize` esegue in ordine nove funzioni
idempotenti a ogni avvio, ognuna che indovina lo stato guardando colonne e tabelle.
Funziona, ma l'ordine è un contratto implicito e una migrazione che ricostruisce una
tabella (`_allow_tag_rules`, `_widen_balance_key`, …) è sicura solo finché ogni
controllo è esatto.

### 2.3 Punteggio

Scala 1-5, misurata contro il pattern scelto sopra (non contro l'esagonale pieno).

|Criterio|Peso|Voto|Perché|
|---|---|---|---|
|Purezza del core (calcolo senza I/O)|15%|4|normalizzatori, matching, dedup puri; metriche e budget mescolano query e aritmetica|
|Strato dei casi d'uso / niente logica nel trasporto|20%|1,5|vedi 2.2 a e b|
|Coesione dei moduli di persistenza|15%|2,5|definizioni uniche, ma `Ledger` e `api.py` enormi|
|Inversione delle dipendenze esterne|10%|3|il client è iniettato nel sync, non altrove; tempo e config globali|
|Definizione unica delle regole di business|10%|4,5|i frammenti SQL condivisi|
|Gestione delle transazioni|10%|3,5|`deferred_commits` corretto ma implicito: 34 `with self.conn` annidabili per contatore|
|Schema e migrazioni|10%|3,5|vedi sezione 4|
|Test come rete di sicurezza|10%|4,5|ampi, realistici, indipendenti dalla macchina|

**Manutenibilità: 3,1 / 5 (≈ 62/100).**

**Robustezza ai cambiamenti**, per tipo di cambiamento prevedibile:

|Cambiamento|Oggi|Perché|
|---|---|---|
|Una nuova schermata / la fase 12 (sezione 5.16)|fragile|finisce in `api.py`, la CLI la duplica|
|Un nuovo formato di import|robusto|un adapter puro e un `CsvProfile`|
|Un secondo provider PSD2|medio-fragile|`sync.py` dipende dai tipi di Enable Banking|
|Cambiare l'ordine o un passo della pipeline d'ingest|fragile|cinque copie da tenere uguali|
|Una nuova definizione di spesa|robusto|un frammento SQL|
|Una colonna nuova|robusto|`_ADDED_COLUMNS`|
|Ricostruire una tabella (cambiare un `CHECK`)|medio|migrazione senza versione|

## 3. Come dovrebbe essere

### 3.1 La forma

```
amonhen/
  core/                    # puro: niente sqlite3, niente requests, niente dt.date.today()
    models.py              # Account, Posting, IncomingTransaction, decimali (oggi models.py)
    dedup.py  matching.py
    rules.py               # Rule, matching_rule, rule_key (la parte pura di merchants.py)
    metrics_math.py        # mediane, accrual, runway su serie già lette
    budget_math.py
  ledger/                  # persistenza + invarianti, un modulo per sotto-dominio
    schema.py  migrations.py  connection.py   # oggi db.py
    sql.py                 # SPENDING_SQL e compagni: le definizioni uniche, invariate
    ingest.py              # record, record_batch, pending→booked, trattenuti
    deletions.py           # tombstone, cestino, restore
    transfers.py           # link, review, mirror, passthrough (la parte su tabelle)
    balances.py            # dichiarazioni, apertura, check 5.4
    catalog.py             # conti, categorie, flag, tag
    queries.py             # le letture che oggi stanno negli handler (lista movimenti, coda)
    __init__.py            # Ledger come facciata che compone i pezzi, per i chiamanti di oggi
  ports.py                 # Protocol: BankProvider, LlmClient, ConfigStore, Clock
  services/                # casi d'uso: l'unico posto dove si orchestra
    ingest.py              # settle_after_ingest(): la pipeline, una volta sola
    sync.py                # SyncService, che dipende da BankProvider
    imports.py  review.py  budgets.py  setup.py  backup.py
  adapters/
    enable_banking/        # client + normalize: implementa BankProvider
    files/                 # csv, ofx
    llm_http.py            # implementa LlmClient
    config_json.py         # accounts.json: implementa ConfigStore
  entrypoints/
    api/                   # un APIRouter per sezione; create_app è la composition root
      transactions.py  review.py  sync.py  budgets.py  setup.py  ...
      schemas.py           # i BaseModel di richiesta e risposta
    cli.py
```

La regola delle dipendenze: `entrypoints → services → (ledger, core, ports)`,
`adapters → ports, core`. `core` non importa niente del progetto tranne sé stesso; un
`services/*` non importa mai `fastapi`; una route non scrive SQL.

### 3.2 I tre pezzi che contano

**La pipeline, una volta sola.** Tutti e cinque i chiamanti della tabella in 2.2 a
diventano una riga:

```python
# services/ingest.py
@dataclass(frozen=True)
class Settled:
    transfer_rules: int
    linked: int
    passthrough: int
    categorized: int

def settle_after_ingest(ledger: Ledger, passthrough: Sequence[Passthrough],
                        *, since: dt.date | None = None) -> Settled:
    """Quello che segue ogni scrittura di movimenti, qualunque sia la strada."""
    book = RuleBook(ledger.conn)
    with ledger.unit_of_work():
        rules = apply_transfer_rules(ledger, book)      # prima dell'abbinamento (sezione 5.3)
        linked = link_transfers(ledger, since=since)
        legs = link_passthrough_legs(ledger, passthrough)
        ledger.validate()
        applied = categorize(ledger, book)
    return Settled(rules, linked, legs, applied)

def import_file(ledger, parsed, passthrough) -> ImportResult:
    counts = ledger.record_batch(parsed)
    return ImportResult(counts, settle_after_ingest(ledger, passthrough))
```

**La porta verso la banca.** Quello che `SyncService` usa davvero, e niente di più:

```python
# ports.py
class BankProvider(Protocol):
    def fetch_transaction_windows(self, account_uid: str, date_from: dt.date,
                                  date_to: dt.date, max_days: int) -> Iterator[FetchedWindow]: ...
    def balances(self, account_uid: str) -> list[dict]: ...

class RateLimited(Exception): ...        # errori del dominio, non di Enable Banking
class ConsentExpired(Exception): ...

class Clock(Protocol):
    def today(self) -> dt.date: ...
    def now(self) -> dt.datetime: ...
```

L'adapter Enable Banking traduce le sue eccezioni in queste; `tools/eb_stub.py` e i test
possono implementare la porta direttamente, senza HTTP finto.

**Route sottili.** Una route valida l'input, chiama un servizio, traduce le eccezioni in
codici HTTP. La stessa funzione serve la CLI:

```python
# entrypoints/api/review.py
router = APIRouter(prefix="/api/sync")

@router.post("/held/{held_id}")
def decide_held(held_id: int, body: HeldDecision, deps: Deps = Depends(deps)) -> dict:
    with deps.ledger() as ledger:
        try:
            result = review.decide_held(ledger, held_id, body.decision, deps.config.passthrough)
        except review.NotFound as exc:
            raise HTTPException(404, str(exc))
        except review.Conflict as exc:
            raise HTTPException(409, str(exc))
    return result.as_payload()
```

`Deps` è un oggetto costruito una volta in `create_app` (ledger factory, `ConfigStore`,
`BankProvider` factory, `Clock`): è la *composition root*, e i test ne passano un altro.

### 3.3 Cosa non fare

- Non mettere un'interfaccia davanti a `Ledger`: un'implementazione sola, per sempre.
- Non portare i frammenti SQL in Python per "purezza".
- Non introdurre un ORM, un container di dependency injection, un bus di eventi o CQRS:
  le letture e le scritture stanno bene nello stesso file SQLite e nello stesso processo.
- Non fare tutto in un colpo: ogni passo sotto è deployabile da solo, come le fasi della
  sezione 9.

### 3.4 Ordine dei lavori

1. **`settle_after_ingest`** e i cinque chiamanti che la usano, con un test che importa un
   file con una regola di giroconto e un importo uguale su un altro conto. È il passo con
   più valore: chiude una divergenza reale. *Piccolo.*
2. **`Clock` e `BankProvider`** come `Protocol`, le eccezioni tradotte nell'adapter. *Piccolo.*
3. **`api.py` in router per sezione**, con `Deps` come composition root; le 22 query
   degli handler scendono in `ledger/queries.py`. Meccanico, coperto dai test dell'API.
   *Medio.*
4. **`Ledger` in moduli per sotto-dominio**, con `Ledger` che resta come facciata così
   nessun chiamante cambia. *Medio.*
5. **Separare calcolo e lettura** in `metrics.py` e `budgets.py`, solo dove un test lo
   chiede. *Quando serve.*

Dopo 1-3 la stima è manutenibilità ≈ 3,9 / 5; dopo 4 ≈ 4,2.

## 4. Lo schema, letto da DBA

In sintesi: **lo schema è buono e non va rifatto.** La partita doppia è modellata come si
deve (la categoria su una posting, non sulla transazione), le chiavi naturali hanno i loro
indici unici, `CHECK` sugli enum, `foreign_keys = ON`, WAL con `synchronous = NORMAL`,
tombstone per le cancellazioni. Quello che segue sono ritocchi, in ordine di valore;
nessuno è necessario per il refactoring sopra.

|#|Cosa|Rischio oggi|Proposta|Costo|
|---|---|---|---|---|
|1|`settings` usa chiavi con l'id di un conto (`sync:last_read:<id>`, `sync:limited:<id>`) senza FK, e `delete_account` non le cancella. `INTEGER PRIMARY KEY` senza `AUTOINCREMENT` può riusare l'id più alto dopo una cancellazione|un conto nuovo che eredita l'id di uno cancellato si mostra "limitato dalla banca" o "letto il…" con lo stato del vecchio|cancellare le due chiavi in `delete_account` (nessun cambio di schema); a lungo andare, due colonne `last_read_at` / `rate_limited_since` su `accounts`|minimo|
|2|Nessuna `PRAGMA user_version`|ordine delle migrazioni implicito, ogni avvio le prova tutte|`user_version` incrementale, le funzioni di oggi diventano i passi fino alla versione attuale; le nuove si aggiungono in coda|piccolo|
|3|Nessun indice `transactions(account_id, date)`|le letture per conto e periodo (saldi, sync di un periodo, filtro Movimenti) usano `transactions_date` e filtrano il conto a mano|`CREATE INDEX IF NOT EXISTS transactions_account_date ON transactions(account_id, date)`; verificare con `EXPLAIN QUERY PLAN` sulla copia del ledger prima di aggiungerlo|minimo|
|4|`rules.target` è un nome (categoria, conto o tag secondo `action`), `merchant_suggestions.category` pure|una rinomina deve ricordarsi di aggiornarli: `rename_category` lo fa, `Ledger.rename_account` no — una regola di giroconto verso un conto rinominato continua a nominare il vecchio nome, e il commento in `delete_account` dice che una regola così ricrea il conto come virtuale al sync dopo (da confermare con un test); niente integrità referenziale|accettabile per una tabella piccola e scritta a mano; se si tocca, `target_id INTEGER` con FK e il nome solo per la visualizzazione|medio, da non fare ora|
|5|FK senza `ON DELETE` su `budgets`, `budget_months`, `budget_items`, `account_balances`, `deleted_transactions`, `held_transactions`|cancellare una categoria con un budget fallisce con un errore di FK invece di un messaggio; `delete_account` pulisce a mano|esplicitare la politica (`CASCADE` per i budget di una categoria, `RESTRICT` dove si vuole il rifiuto) alla prossima ricostruzione di quelle tabelle, non per sé|da agganciare|
|6|`transfer_links` non impedisce che una gamba stia in due coppie|lo garantisce il codice (`_live_link`), non lo schema|indice unico parziale su ciascuna gamba per le coppie non rifiutate, dopo aver verificato sulla copia che non ci siano violazioni|piccolo|
|7|Importi come `TEXT` decimale, confronti con `CAST(… AS REAL)`|nessuno per i segni e le soglie; le somme sono già in `Decimal`|**lasciare così.** Centesimi `INTEGER` sarebbero la scelta da manuale, ma la migrazione tocca ogni riga e ogni query per un guadagno che qui non si vede|—|
|8|`accounts` tiene conti reali, virtuali e categorie (single-table inheritance), con flag che valgono solo per un tipo|un flag sul tipo sbagliato non è impedito dallo schema|`CHECK` del tipo `type = 'category' OR (income = 0 AND contribution = 0 …)` alla prossima ricostruzione; la tabella unica è giusta, perché la posting punta a "un conto" qualunque|piccolo, da agganciare|

I punti 1-3 si possono fare subito e sono indipendenti dal resto; 4-6 e 8 vanno fatti
solo quando una fetta ricostruisce quelle tabelle per un motivo suo, con la migrazione
provata su una copia di uno snapshot come dice il README (*Updating safely*). Il 7 no.

## 5. I protagonisti del pattern, uno per uno

Ogni protagonista con un esempio preso da AmonHen: prima quelli che si applicano, poi
quelli che qui non servono, in fondo un import seguito attraverso tutti gli strati.

### L'idea di fondo

Il pattern ha una sola legge, la **regola delle dipendenze**: le dipendenze puntano
verso l'interno. Il centro non sa che esistono FastAPI, SQLite, Enable Banking o il disco.
Tutto il resto serve a rispettare questa legge.

```
      [ FastAPI ]   [ CLI ]                ← adapter primari (chi chiama)
            \         /
        [ casi d'uso / servizi ]           ← orchestrazione
            /        |        \
      [ core puro ] [ ledger ]  [ porte ]  ← dominio + persistenza + contratti
                                   |
               [ Enable Banking ] [ LLM ] [ accounts.json ] [ orologio ]   ← adapter secondari (chi viene chiamato)
```

### 5.1 Cosa si applica

#### 1. Il core di dominio: le regole, senza I/O

**Cos'è:** il codice che risponde a "come funziona il mondo della finanza personale",
senza leggere o scrivere niente. Prende dati e restituisce dati.

**Responsabilità:** calcolo, decisioni, invarianti espresse come funzioni.

**Non può:** importare `sqlite3`, `requests`, `fastapi`, né chiamare `dt.date.today()`.
La data di oggi gli arriva come parametro.

**In AmonHen c'è già, ed è la parte migliore del codice:**

- **`dedup.content_hash(account_id, date, amount, description)`.** È una funzione pura:
  stessi input, stesso hash. Si testa senza database.
- **`matching.max_weight_matching(weights)`.** L'algoritmo ungherese sui giroconti riceve
  un dizionario di pesi e restituisce le coppie. Non sa che esistono le transazioni.
- **`merchants.matching_rule(...)`, `rule_key`, `merchant_name`.** Dicono quale regola
  spiega una descrizione, senza sapere da dove vengono le regole.

**Dove è sporcato:** `metrics.py` e `budgets.py` mescolano la query e la mediana nella
stessa funzione, quindi per testare "la mediana di sei mesi" serve un database. La
versione pulita separa le due cose: una funzione legge le serie dal ledger, un'altra
(pura) ci fa l'aritmetica.

**Perché conta:** la parte che si sbaglia più facilmente, cioè i numeri, diventa la più
facile da testare. Un test di una funzione pura gira in microsecondi.

#### 2. Le entità e i value object del dominio

**Cosa sono:** i "nomi" del dominio. Un value object è definito dal suo valore (due
importi da 10 € sono lo stesso importo). Un'entità ha un'identità che sopravvive ai
cambiamenti (un conto resta quel conto anche se lo rinomini).

**In AmonHen:**

- **`IncomingTransaction` (`models.py`)** è il contratto fra il mondo esterno e il ledger.
  Ogni sorgente (PSD2, CSV, OFX) deve produrre esattamente questo, ed è ciò che permette
  di aggiungere un formato di import senza toccare il ledger.
- **`Decimal`** fa da value object del denaro. `parse_decimal` / `format_decimal` sono il
  confine che impedisce ai `float` di entrare.
- **`Account`, `Posting`, `Rule`** sono dataclass, quindi entità "anemiche": dati senza
  comportamento.

**Verdetto:** si applica in forma leggera. Le dataclass vanno bene; non servono entità
con metodi (vedi più sotto, *Il rich domain model*).

#### 3. La persistenza: il ledger come *table data gateway*

**Cos'è:** lo strato che parla con SQLite. Nell'esagonale da manuale sarebbe un adapter
secondario dietro un'interfaccia `Repository`; qui quell'interfaccia non c'è (il motivo
è più sotto). Il ledger resta un modulo concreto, ma con confini netti.

**Responsabilità:**

- **Scrivere rispettando le invarianti** della partita doppia: ogni transazione ha le sue
  posting e la somma è zero.
- **Possedere le definizioni SQL del dominio**: `SPENDING_SQL`, `RARE_SQL`, `CREDITS_WHERE`.
- **Fornire le letture** di cui hanno bisogno i casi d'uso.

**Non può:** sapere di HTTP (nessun `HTTPException`), leggere `accounts.json`, chiamare
una banca.

**In AmonHen:**

- **Bene:** `Ledger.record()` contiene tutta la logica pending → booked e la doppia
  dedup. Nessun altro scrive in `transactions`.
- **Bene:** `SPENDING_SQL` è una regola di business scritta in SQL, ed è proprio questo il
  punto: "cos'è una spesa" si decide in un posto solo, e metriche, budget e grafici lo
  usano tutti.
- **Male:** `api.py:1340` e altre 21 query vivono negli handler HTTP. Sono letture del
  ledger finite nel posto sbagliato.
- **Male:** `Ledger` ha circa 130 metodi. Lo strato è giusto, la granularità no: va
  spezzato in `ingest`, `deletions`, `transfers`, `balances`, `catalog`.

#### 4. I casi d'uso (application services)

**Cosa sono:** le "frasi" del sistema, come *importa un file*, *sincronizza un periodo*,
*decidi un doppione trattenuto*, *rinomina una categoria*. Ognuno coordina core, ledger e
porte nell'ordine giusto, dentro una transazione.

**Responsabilità:**

- **L'ordine dei passi.**
- **Il confine della transazione** (tutto o niente).
- **Le eccezioni di dominio:** `NotFound`, `Conflict`, `PeriodInvalid`.

**Non può:**

- importare `fastapi`: un caso d'uso non sa di essere chiamato via HTTP;
- contenere calcoli, che stanno nel core;
- contenere SQL, che sta nel ledger.

**In AmonHen è lo strato che manca**, e la prova è quella della sezione 2.2 a: la
sequenza dopo l'ingest è ricostruita a mano in cinque posti, e i percorsi sono già
diversi. L'import fa:

```python
counts = ledger.record_batch(transactions)
links = link_transfers(ledger)            # ← l'abbinamento prima…
legs = link_passthrough_legs(ledger, ...)
ledger.validate()
applied = categorize(ledger, ...)         # ← …e le regole di giroconto solo qui dentro, dopo
```

Il sync invece chiama `apply_transfer_rules` **prima** di `link_transfers`, come chiede la
sezione 5.3 della specifica. Con un caso d'uso `settle_after_ingest()` questa differenza
non può nemmeno esistere, perché la sequenza è scritta una volta sola.

**`SyncService` è già un caso d'uso**, ed è fatto bene: riceve il client, la
configurazione e `today`, e coordina. È il modello da seguire per gli altri.

#### 5. Le porte (ports)

**Cosa sono:** interfacce che dicono "mi serve qualcuno che sappia fare X", scritte dal
punto di vista di chi le usa. In Python sono un `typing.Protocol`.

**Responsabilità:** definire il contratto minimo, con tipi ed eccezioni **del dominio** e
non del fornitore.

**Dove servono in AmonHen:** solo nei quattro punti in cui c'è davvero un "fuori" che può
cambiare o che in un test va sostituito.

|Porta|Perché esiste|Chi la implementa oggi / domani|
|---|---|---|
|`BankProvider`|la banca è esterna, lenta, a quote; potrebbe arrivare un secondo provider PSD2|`EnableBankingClient`, `tools/eb_stub.py`, un fake nei test|
|`LlmClient`|un fornitore terzo, spegnibile (sezione 5.5)|il client HTTP di `llm.py`, un fake|
|`ConfigStore`|`accounts.json` è letto e scritto da route, CLI e sync|il file JSON; un dizionario in memoria nei test|
|`Clock`|`today()` compare in 8 moduli: i test sul "mese corrente" dipendono dal giorno in cui girano|l'orologio di sistema, uno fisso nei test|

**L'esempio più istruttivo di cosa va storto senza porta:**

```python
# providers/enable_banking.py
class RateLimitedError(requests.HTTPError): ...
```

`sync.py` cattura `RateLimitedError`, che **è** un `requests.HTTPError`: il caso d'uso sa
quale libreria HTTP usa il fornitore. Con una porta, il dominio definisce
`RateLimited(Exception)` e l'adapter traduce:

```python
# adapters/enable_banking/client.py
try:
    response.raise_for_status()
except requests.HTTPError as exc:
    if exc.response.status_code == 429:
        raise RateLimited(...) from exc   # il dominio vede solo questo
```

#### 6. Gli adapter secondari (driven: quelli che il sistema chiama)

**Cosa sono:** le implementazioni concrete delle porte. Traducono il mondo esterno nei
tipi del dominio e viceversa.

**Responsabilità:** HTTP, autenticazione JWT, paginazione, retry, parsing dei formati,
conversione delle eccezioni.

**Non può:** prendere decisioni di dominio. Un adapter non decide se un movimento è un
giroconto.

**In AmonHen sono già quasi esemplari:**

- **`eb_normalize.normalize_transaction`** trasforma il payload grezzo di Enable Banking
  in `IncomingTransaction`. Le stranezze di Fineco (`_fineco_counterparty`) restano chiuse
  lì dentro: il ledger non sa che Fineco esiste.
- **`csv_adapter` con `CsvProfile`, e `ofx_adapter`:** ogni formato è un adapter e tutti
  producono lo stesso tipo. Per questo "un nuovo formato di import" è *robusto* nella
  sezione 2.3.
- **Da sistemare:** `EnableBankingClient` va dichiarato come implementazione di
  `BankProvider`, con le eccezioni tradotte.

#### 7. Gli adapter primari (driving: quelli che chiamano il sistema)

**Cosa sono:** i punti di ingresso, cioè FastAPI e la CLI. Traducono una richiesta
esterna in una chiamata a un caso d'uso.

**Responsabilità:**

- validare la forma dell'input (Pydantic, argparse);
- chiamare **un** caso d'uso;
- tradurre il risultato in JSON o testo, e le eccezioni di dominio in codici HTTP o exit
  code.

**Non può:** scrivere SQL, orchestrare più passi, contenere regole.

**Il test pratico:** una route sana è lunga 5-10 righe, e il comando CLI equivalente
chiama la **stessa** funzione. Oggi l'import da app (`api.py:2019`) e quello da CLI
(`cli.py:619`) sono due copie della stessa sequenza. Domani:

```python
# API
result = imports.import_file(ledger, parsed, deps.config.passthrough)
# CLI
result = imports.import_file(ledger, parsed, load_config(args.config).passthrough)
```

#### 8. La composition root

**Cos'è:** l'unico punto in cui si decide "per questa esecuzione, la porta X la
implementa Y". Costruisce gli oggetti concreti e li passa giù.

**In AmonHen:** `create_app()` per il server e `main()` per la CLI. Oggi `create_app` è
anche il contenitore di 74 route. Domani crea un oggetto `Deps` (factory del ledger,
`ConfigStore`, factory del `BankProvider`, `Clock`) e monta i router. Un test passa un
`Deps` diverso, e così si sostituisce la banca senza `responses`.

**Nota:** questa **è** la dependency injection, fatta a mano. Per un'app di queste
dimensioni non serve altro.

#### 9. L'unità di lavoro (unit of work)

**Cos'è:** il confine "questa operazione o riesce tutta o non lascia niente".

**In AmonHen c'è già:** `deferred_commits()` in `db.py`. È corretto, ma implicito: 34
`with self.conn` annidati gestiti con un contatore. Nella forma di arrivo lo apre il
**caso d'uso** (`with ledger.unit_of_work():`), non i metodi del ledger, così chi legge il
caso d'uso vede dove inizia e dove finisce la transazione.

### 5.2 Cosa non si applica, e perché

#### ✗ Il repository astratto davanti al database

**Cos'è nel pattern pieno:** `class TransactionRepository(Protocol)` più
`SqliteTransactionRepository`, così il dominio non sa che c'è SQLite.

**Perché no qui:** SQLite è una scelta di prodotto (un file, uno snapshot, il NAS), non
un dettaglio sostituibile. Un'interfaccia che avrà per sempre una sola implementazione è
solo burocrazia: ogni metodo si scrive due volte e ogni modifica si fa in due file. I test
usano già un SQLite in memoria vero, veloce e più fedele di un fake.

**Quando cambiare idea:** se si dovesse supportare anche Postgres, oppure se i test sul
ledger diventassero lenti.

#### ✗ Le regole di dominio portate fuori dall'SQL

**Cos'è nel pattern pieno:** il dominio non conosce SQL, quindi "cos'è una spesa" sarebbe
un metodo Python, `Transaction.is_spending()`.

**Perché no qui:** bisognerebbe caricare in memoria tutte le posting per filtrarle, o
tenere due definizioni (una in SQL per le query, una in Python per il dominio) che prima o
poi si separano. `SPENDING_SQL` come definizione unica vale più della purezza. **È il
compromesso centrale di questa architettura:** il core comprende anche dei frammenti SQL.

#### ✗ Il rich domain model / gli aggregati DDD

**Cos'è:** entità con comportamento e invarianti dentro, per esempio `account.record(txn)`
o `transaction.split(...)`, caricate e salvate intere come "aggregati".

**Perché no qui:** le invarianti di AmonHen sono **insiemistiche e trasversali**:

- un giroconto lega due transazioni di due conti;
- la dedup confronta con tutto lo storico;
- il saldo è la somma di tutte le posting.

Sono domande da database, non da oggetto in memoria. Un aggregato `Account` con dentro
migliaia di movimenti sarebbe lento e innaturale.

#### ✗ Gli eventi di dominio / il message bus

**Cos'è:** `TransactionRecorded` viene pubblicato, e qualcuno in ascolto abbina e
categorizza.

**Perché no qui:** la sequenza dopo l'ingest ha un **ordine preciso** (sezione 5.3: le
regole di giroconto prima dell'abbinamento). Con gli eventi l'ordine diventa implicito:
è lo stesso problema delle cinque copie, solo meno visibile. Una funzione che chiama
cinque passi in fila è più chiara.

#### ✗ CQRS

**Cos'è:** modelli, e magari database, separati per le letture e per le scritture.

**Perché no qui:** un utente, un file, WAL che lascia leggere mentre si scrive. Di CQRS
resta solo l'idea minima: le letture complesse stanno in `ledger/queries.py`, separate
dai metodi che scrivono.

#### ✗ Container di DI, ORM, DTO a ogni strato

- **Container di DI** (`dependency-injector` e simili): la composition root a mano è
  lunga dieci righe.
- **ORM:** escluso dalla specifica, e l'SQL scritto a mano è un pregio qui.
- **Un DTO per ogni passaggio fra strati:** `IncomingTransaction` attraversa core, servizi
  e ledger così com'è, e va bene. Servono solo i modelli Pydantic al confine HTTP, che ci
  sono già.

### 5.3 Un import attraverso gli strati

Un CSV di Fineco caricato dalla schermata **Importa**, nella forma di arrivo:

|#|Strato|Chi|Cosa fa|Cosa NON fa|
|---|---|---|---|---|
|1|Adapter primario|`entrypoints/api/imports.py`|valida il body (Pydantic), prende `Deps`, chiama `imports.import_file`|non scrive SQL, non sa dei giroconti|
|2|Composition root|`create_app` → `Deps`|ha già deciso quale `ConfigStore` e quale ledger usare|—|
|3|Adapter secondario|`adapters/files/csv_adapter`|righe CSV → `list[IncomingTransaction]`|non sa che esiste un database|
|4|Caso d'uso|`services/imports.import_file`|apre la transazione, `record_batch`, poi `settle_after_ingest`|non fa calcoli, non scrive SQL|
|5|Persistenza|`ledger/ingest.record_batch`|dedup a due livelli, pending → booked, posting|non decide l'ordine dei passi successivi|
|6|Core|`dedup.content_hash`, `matching.max_weight_matching`|calcola l'hash e l'abbinamento ottimo|non legge e non scrive niente|
|7|Caso d'uso|`settle_after_ingest`|regole di giroconto → abbinamento → passthrough → `validate` → categorie, **sempre in quest'ordine**|—|
|8|Adapter primario|di nuovo la route|`ImportResult` → JSON; `Conflict` → 409|—|

La CLI rifà i passi 3-7 **identici** e cambia solo l'1 e l'8: è il segno che gli strati
sono al posto giusto.

### 5.4 Le domande per orientarsi nel codice

- "Questa riga sa che c'è HTTP?" Allora sta nella route.
- "Sa che c'è SQLite?" Allora sta nel ledger.
- "Sa che c'è Enable Banking?" Allora sta in un adapter.
- "Decide l'ordine di più cose?" Allora sta in un caso d'uso.
- "Nessuna delle quattro?" Allora è core.

## 6. Gli strati costruiti da zero

La sezione 5 descrive gli strati partendo dal codice che c'è. Questa li fa comparire
uno alla volta, come se si costruisse un AmonHen piccolissimo su un foglio vuoto,
nell'ordine in cui ne nasce il bisogno, ognuno con il motivo per cui esiste.

L'esempio è una sola funzione dell'app: **"importo un CSV della banca e vedo quanto ho
speso questo mese"**.

### 6.1 Il dominio: i nomi delle cose

**Cos'è:** le parole del problema, scritte come tipi di dato. Prima di pensare a database
o pagine web ci si chiede: di cosa parla questo software? Di movimenti, conti, categorie,
importi.

```python
@dataclass(frozen=True)
class Movement:
    account: str
    date: dt.date
    amount: Decimal      # negativo = uscita
    description: str
```

**Il motivo:** questi concetti esistevano prima del software e esisteranno dopo. Un
movimento bancario è un movimento bancario sia che arrivi da un CSV sia da un'API, sia che
stia in SQLite sia su carta. Se si definiscono per primi e senza dipendenze, tutto il
programma ha un vocabolario comune: quando un pezzo di codice riceve un `Movement`, sa
esattamente cosa ha in mano.

**In AmonHen:** `models.py`, con `IncomingTransaction`, `Account` e `Posting`.

### 6.2 Il core: le regole, come funzioni pure

**Cos'è:** il codice che *ragiona* sui nomi del dominio. Prende dati e restituisce dati:
non legge file, non chiama la rete, non apre il database.

```python
def is_spending(m: Movement) -> bool:
    return m.amount < 0

def spent_in_month(movements: list[Movement], month: str) -> Decimal:
    return -sum((m.amount for m in movements
                 if is_spending(m) and m.date.isoformat().startswith(month)),
                Decimal(0))
```

**Il motivo:** è la parte che non deve sbagliare, perché produce i numeri su cui si
prendono decisioni. Se è pura, si testa con tre righe e nessuna preparazione: le si dà una
lista e si controlla il risultato. Non serve un database finto, non dipende dal giorno in
cui gira il test, non si rompe se cambia la libreria HTTP. Per la stessa ragione non
chiede mai "che giorno è oggi?": quella data gliela passa qualcun altro.

**In AmonHen:** `dedup.content_hash`, `matching.max_weight_matching`,
`merchants.matching_rule`. Qui sta anche il compromesso della sezione 5.2: alcune regole,
come `SPENDING_SQL`, sono scritte in SQL perché devono girare su migliaia di righe dentro
il database. Restano "core" nel senso che contano: sono definite una volta sola.

### 6.3 La persistenza: dove i dati sopravvivono

**Cos'è:** il codice che salva e rilegge i nomi del dominio. È l'unico che sa che esiste
SQLite.

```python
class Ledger:
    def __init__(self, conn): self.conn = conn

    def record(self, m: Movement) -> None:
        if self._already_there(m):      # niente doppioni
            return
        self.conn.execute("INSERT INTO transactions ...", (...))

    def movements(self, month: str) -> list[Movement]:
        rows = self.conn.execute("SELECT ... WHERE date LIKE ?", (month + "%",))
        return [Movement(...) for r in rows]
```

**Il motivo:** due ragioni.

- **Le invarianti vivono qui.** "Mai lo stesso movimento due volte", "le posting sommano a
  zero": se tutte le scritture passano da un punto solo, quel punto può garantirle. Se
  dieci parti del programma scrivono `INSERT` per conto loro, ognuna deve ricordarsene, e
  prima o poi una se ne dimentica.
- **Il resto del programma non deve sapere com'è fatto lo schema.** Chi chiama
  `ledger.movements("2026-11")` riceve dei `Movement`, non delle righe SQL. Se si aggiunge
  una colonna, cambia questo file e basta.

**In AmonHen:** `ledger.py` e `db.py`. Il difetto di oggi non è lo strato, è la
dimensione: un solo `Ledger` fa dieci mestieri diversi.

### 6.4 Le porte: cosa serve dal mondo esterno

**Cos'è:** una descrizione, solo la firma, di un servizio che serve e che sta *fuori* dal
programma. Non dice chi lo fa, dice cosa deve saper fare.

```python
class BankProvider(Protocol):
    def fetch(self, account: str, since: dt.date) -> list[Movement]: ...

class Clock(Protocol):
    def today(self) -> dt.date: ...
```

**Il motivo:** il mondo esterno è la parte che non si controlla. La banca cambia API, va
in limite di richieste, il consenso scade; l'orologio fa sì che un test passi a novembre e
fallisca a dicembre. Una porta dice "a me basta questo". In produzione ci va la banca vera,
nei test un finto che restituisce sempre gli stessi tre movimenti, e il codice che la usa
non se ne accorge.

La porta la scrive chi la *usa*, non chi la implementa. Per questo parla con i tipi del
dominio (`Movement`, `RateLimited`) e non con quelli del fornitore (`requests.HTTPError`).

**In AmonHen:** non esistono ancora come file. Ne servono quattro: la banca, l'LLM, la
configurazione e l'orologio. Solo quattro, perché sono gli unici "fuori" veri.

### 6.5 Gli adapter verso l'esterno: chi implementa le porte

**Cos'è:** il codice concreto che parla con il servizio esterno e traduce le sue risposte
nei nomi del dominio.

```python
class EnableBanking:                 # implementa BankProvider
    def fetch(self, account, since):
        raw = requests.get(...).json()         # JWT, paginazione, retry: affari suoi
        return [normalize(r) for r in raw]     # payload della banca → Movement

def parse_csv(path) -> list[Movement]:         # anche un formato di file è un adapter
    ...
```

**Il motivo:** le stranezze del mondo esterno restano chiuse qui dentro. Fineco scrive la
controparte dentro la causale, Revolut usa campi diversi: il resto del programma vede solo
`Movement` puliti. Aggiungere una banca o un formato vuol dire scrivere un adapter nuovo,
senza toccare niente al centro.

**In AmonHen:** `providers/eb_normalize.py`, `adapters/csv_adapter.py` e
`adapters/ofx_adapter.py`. Sono già la parte più pulita del codice.

### 6.6 I casi d'uso: le frasi del sistema

**Cos'è:** una funzione per ogni cosa che l'utente può *chiedere* al sistema. Mette
insieme i pezzi precedenti nell'ordine giusto.

```python
def import_file(ledger: Ledger, movements: list[Movement]) -> ImportResult:
    with ledger.unit_of_work():              # tutto o niente
        for m in movements:
            ledger.record(m)
        apply_transfer_rules(ledger)         # sempre prima…
        link_transfers(ledger)               # …dell'abbinamento
        categorize(ledger)
    return ImportResult(...)

def month_spending(ledger: Ledger, clock: Clock) -> Decimal:
    month = clock.today().strftime("%Y-%m")
    return spent_in_month(ledger.movements(month), month)
```

**Il motivo:** ogni azione dell'utente è una *sequenza* di passi, e la sequenza è essa
stessa una regola: in AmonHen le regole di giroconto vanno applicate prima
dell'abbinamento. Se la sequenza è scritta in un posto solo, è giusta ovunque. Se ogni
punto d'ingresso la ricostruisce a mano, le copie divergono, ed è quello che è successo:
cinque copie e tre comportamenti diversi (sezione 2.2 a).

Il caso d'uso non calcola (lo fa il core), non scrive SQL (lo fa il ledger) e non sa di
essere chiamato da una pagina web. Coordina e basta.

**In AmonHen:** `SyncService` è già fatto così. Il resto oggi è sparso dentro le route di
`api.py` e i comandi di `cli.py`.

### 6.7 Gli adapter d'ingresso: da dove arrivano le richieste

**Cos'è:** il codice che riceve una richiesta dal mondo, cioè un click nell'app o un
comando nel terminale, e la trasforma in una chiamata a un caso d'uso.

```python
# FastAPI
@router.post("/api/import")
def import_route(body: ImportRequest):
    movements = parse_csv(body.path)
    result = import_file(ledger, movements)
    return {"written": result.written}

# CLI
def cmd_import(args):
    result = import_file(ledger, parse_csv(args.file))
    print(f"scritti {result.written}")
```

**Il motivo:** HTTP e terminale sono due modi diversi di chiedere *la stessa cosa*. Questo
strato si occupa solo della forma: leggere il JSON, controllare che i campi ci siano,
rispondere 409 invece di sollevare un'eccezione. Il "cosa fare" lo delega. Il segnale che
funziona è che la route e il comando chiamano la stessa funzione e sono lunghi poche righe.

**In AmonHen:** `api.py` e `cli.py`. Oggi sono lo strato più gonfio, perché fanno anche il
lavoro della persistenza e dei casi d'uso.

### 6.8 La composition root: dove si monta tutto

**Cos'è:** l'unico punto del programma in cui si decide "stavolta la banca è quella vera,
il database è questo file, l'orologio è quello di sistema". Crea gli oggetti concreti e li
passa a chi ne ha bisogno.

```python
def create_app():
    deps = Deps(
        ledger=lambda: Ledger(sqlite3.connect("amonhen.db")),
        bank=EnableBanking(config),
        clock=SystemClock(),
    )
    app = FastAPI()
    app.include_router(imports_router(deps))
    return app
```

**Il motivo:** se ogni pezzo creasse da sé le cose che gli servono, non si potrebbero mai
sostituire. Raccogliendo le scelte in un punto, un test chiama `create_app` con un `Deps`
diverso (una banca finta, un database in memoria, un orologio fermo al 15 marzo) e prova
il programma intero senza toccare la rete.

**In AmonHen:** `create_app()` e `main()` della CLI. Ci sono già, ma oggi contengono anche
tutte le route.

### 6.9 Come si legge il tutto

Gli strati in fila, dal centro verso il bordo:

1. **Dominio:** di cosa parliamo.
2. **Core:** come si ragiona su quelle cose.
3. **Persistenza:** come le ricordiamo, e quali regole non si rompono mai.
4. **Porte:** cosa ci serve dal mondo, detto con le nostre parole.
5. **Adapter verso l'esterno:** chi ci dà quelle cose, tradotte.
6. **Casi d'uso:** cosa può chiedere l'utente, passo per passo.
7. **Adapter d'ingresso:** come l'utente lo chiede, dall'app o dal terminale.
8. **Composition root:** chi monta i pezzi.

Ogni strato conosce solo quelli più vicini al centro, mai quelli verso il bordo. Il
dominio non sa niente di nessuno. Il core conosce il dominio. Il caso d'uso conosce core,
persistenza e porte, ma non sa che esiste FastAPI. La route conosce il caso d'uso, ma non
sa che esiste SQLite.

**Partendo da zero, l'ordine in cui scrivere è lo stesso**, dal centro verso il bordo:

1. prima le dataclass del dominio;
2. poi le funzioni del core, ognuna con il suo test;
3. poi il ledger;
4. poi un caso d'uso, provato con una banca finta;
5. solo alla fine la route e la pagina.

Così ogni pezzo nuovo poggia su qualcosa di già testato, e la parte più fragile, il mondo
esterno, è l'ultima ad arrivare.
