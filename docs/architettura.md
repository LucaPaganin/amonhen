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
