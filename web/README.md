# AmonHen — PWA

Mobile-first React PWA over the `amonhen` FastAPI backend. Five screens in the bottom bar,
reachable from there or from the hamburger in the top bar — and above 1024 px from the rail, which
carries all eight — plus the entries with no column for them: **Importa**, **Assistente** (its own
section below) and **Configurazione**, the setup wizard:

- **Da confermare** — the review queue: the merchant proposals to accept or dismiss, each with the
  spending it would settle (amount, movements, span), the candidate
  transfer links with *Conferma* / *Rifiuta*, and the uncategorized movements with a category
  picker, a filter (state, free text, account) and an amber flag on the ones no automatic pass
  claimed. Rows leave the queue optimistically and come back if the request fails.
- **Movimenti** — a month of transactions with account, category, transfer and free-text filters, a
  running month total per row and the month total in the header. Tapping a row opens the category
  picker, or the transfer sheet when the row is a leg of a transfer.
- **Dashboard** — the landing screen: a filter bar (period, accounts, one category), three charts
  (spending per category in the period, income against expenses per month, tracked net worth),
  the monthly metrics of the desiderata (burn ricorrente, accantonamento episodico, burn atteso,
  runway stressato, quota incomprimibile, quota discrezionale, flusso di risparmio) and the
  explained spending anomalies.
- **Conti** — the management section: every real account with its balance, its opening figure and
  the 5.4 outcome, where you declare a balance, align the opening, add an account by hand and set a
  category's monthly budget.
- **Categorie e regole** — one entry per category: the name, how many rules and movements it holds
  and the two flags the metrics read, with the texts that assign it opening underneath. Each rule row
  shows the text it looks for, how many movements it holds right now, a category select and a
  *Rimuovi*; the group's last row writes a new one, and a rule assigns the category whose head was
  opened, so there is no category to choose. The bar at the top creates a category, and a search
  opens the groups that matched.
- **Configurazione** — the setup wizard, `inBar: false`, in its own section below: while nothing
  is configured it *is* the app, and afterwards it is where a bank is added or a consent renewed.

The category picker also offers to create a rule that looks for that merchant's text in the
description (`POST /api/rules`), and *È un giroconto* hands the row to the transfer sheet below.
The review screen can run the categorization cascade
(`POST /api/categorize`), and the picker can split one transaction across several categories.

## Navigation

Three paths into the same `onChange`, two of them the phone's: the bottom bar switches a section in
one tap, and the hamburger in the top bar opens a drawer that names each section in full, says what
it holds and carries the count of what is waiting. The drawer closes on a choice, on Escape and on
the backdrop, keeps focus inside itself while open, is `inert` while shut — nothing in it is a tab
stop off screen — and hands focus back to the hamburger when it closes. Above 1024 px both of those
surfaces are off and the rail takes over: the same list standing up in a 248 px column down the
left, full height, every section named in full, the current one marked with `aria-current="page"`.
The sections and their icons are declared once, in `src/components/Navigation.tsx`, and all three
paths render from that list — the rail and the drawer share the item itself (`.navitem`).
**Importa**, **Assistente** and **Configurazione** are `inBar: false`, because eight labels do not fit
the bar's five columns and the drawer names each of them in full.

## Importa

The historical import (desiderata 5.1, *path B*) as a screen: a bank's CSV export is brought in by
hand, with the columns named on the file. Choose the file, and `POST /api/import/csv/preview` answers
with the column names the header carries — which is what the menus need before anything can be
chosen — plus the first rows the mapping reads and the count it would write. Eleven choices, in the
order a statement reads: the delimiter, how many header rows to skip, the date column and its format
(seven shapes offered, from `2026-09-27` to `27/09/2026 14:30:00`), the amount column — or a *Dare*
and an *Avere* pair, which is what an Italian export carries — the decimal separator, one or two
description columns, an optional provider id, and the sign, for statements where money out is what is
positive. The account is a separate choice: a file does not say which account it belongs to. The
preview lists the rows with their line numbers and the amounts as the rest of the app shows money,
and *Importa* posts the whole statement as text to `POST /api/import/csv`, which is the command
line's pipeline (`read_csv` into `record_batch`, then transfers, passthrough labels and rules) — so
importing the same file twice writes nothing, the identity being the same content hash. A row the
mapping cannot read is listed with its line and does not stop the import; its reason is the parser's
own sentence, in English, as every backend `detail` is shown.

## Assistente

The section reads the numbers the backend already computed. Three chips ask the questions that come
up most often, a field takes a free one, and the answer arrives as a card whose caption says it was
generated and names the model and the fingerprint of the data. The card carries the figures the
packet contained and nothing else: a reading that cited a figure nobody computed is refused by the
server and shows up in the history as *rifiutata: citava una cifra non calcolata* — without the
figure itself, which is exactly what must not reach the screen.

Proposals come back with the reading and are cards of their own: a category proposal says it is
confirmed in **Da confermare**, where every proposal is, and a budget proposal has *Accetta* and
*Scarta* here. Nothing is applied by the model — accepting a budget calls
`POST /api/assistant/budgets/decision` and writes the budget the way the Conti screen does. The
history lists what has been asked, with the model and the refusal, and the state line under the
title says how many calls the day has left.

The section is also reachable from where the question is composed: *Regge?* on a budget row opens it
with that budget as the context. The question the row implies — *Questo budget regge?* — arrives in a
panel of its own that names the model that would answer it, with two buttons, *Chiedi* and *Lascia
perdere*; nothing reaches `POST /api/assistant/ask` until the first is pressed, the button that sent
it names the model while the request is in flight, and a call that fails leaves the panel standing so
the question can be tried again. No effect, timer or background loop asks in the person's place; the
reading says whether it was a new call or one already had.

## Configurazione

The setup wizard (desiderata 5.10) takes a fresh install to a reconciled ledger without a text editor,
and it is a section of the app rather than a separate page: `Configurazione` in the drawer and in the
rail, `inBar: false`. Five steps, in this order:

1. **Credenziali** — the Enable Banking application id, the private key pasted as PEM, the redirect
   URL (prefilled with the one on the file, or with `window.location.origin + "/callback"` when
   there is none yet) and the account holder's name, saved with `PUT /api/setup/credentials`, which
   writes `accounts.json` and the key beside it. After the save the step shows the saved redirect URL
   as a line to copy: registering it in the Enable
   Banking dashboard character for character is the one step that stays manual. The key is never
   read back — the payload answers whether it loads (`key_loads`) and says nothing about its
   contents — and a refused write leaves the file untouched, with the server's English
   `detail` shown as it is.
2. **Banca** — a country select (Italy by default) and the ASPSP list from
   `GET /api/setup/banks?country=IT`, already filtered and sorted, with a filter box over it.
   Choosing a bank posts `POST /api/setup/connect` and sends the browser to it, because the login
   happens at the bank and nowhere else.
3. **Conti** — every account the authorization wrote, with an editable name and start date
   (`PATCH /api/setup/accounts/{account_uid}`), a *Togli* (`DELETE /api/setup/accounts/{account_uid}`)
   and a marker of what the last authorization did: `added` or `refreshed`, from `last_connect`.
   The name is how the ledger knows the account, so two accounts under one name become one — which
   is why a name another entry already uses is refused.
4. **Primo sync** — `POST /api/sync`, and the per-account outcome is the content of the step rather
   than a toast: movements inserted and updated, transfers linked, errors, and the 5.4 state.
5. **Saldi e verifica** — per real account from `GET /api/accounts`: its verification state, the
   form that declares a balance read off the bank (`PUT /api/accounts/{id}/declaration`, available or
   booked) and, while the account is not verified, *Allinea il saldo iniziale*
   (`PUT /api/accounts/{id}/opening`). The closing button returns to the dashboard and drops
   `?setup=1` from the address with `history.replaceState`.

Gating: while `GET /api/setup` answers `configured: false` the wizard replaces the app shell and
opens at the first step whose requirement is unmet — *Credenziali* when the application id or the key
is missing, *Banca* when only the accounts are. It stays reachable once the system is configured, from
the same entry — the drawer, or the rail above 1024 px — starting at *Conti* so a bank can be added
or a consent renewed. `?setup=1` at
boot forces it open and lands on *Conti* when `last_connect` is present: that is how the browser comes
back from the bank, since `/callback` answers 303 to `/?setup=1` instead of a JSON document.

## Requirements

- Node 22+
- The backend listening on `127.0.0.1:8000` (only needed at runtime, never at build time)

## Development

```bash
npm install
npm run dev
```

Vite serves the app and proxies `/api` to `http://127.0.0.1:8000` (see `vite.config.ts`), so the
frontend and the ledger API share one origin during development.

## Build

```bash
npm run build
```

Runs `tsc --noEmit` and writes the production bundle to `dist/` (gitignored). The build assumes
the app is served from the site root (`base: "/"`) with an SPA fallback to `index.html`; assets
are requested relative to the root.

The bundle is read from disk on every request while the Python process can still be running
older code, so the app asks `GET /api/health` for its `api_version` on start. If the server is
older than `REQUIRED_API_VERSION` in `src/App.tsx` it shows a single screen saying so, with the
command to restart it, instead of rendering against response shapes it cannot read. Bump both
constants together whenever an endpoint's payload changes — or the meaning of a request field does,
as when `POST /api/rules` learned that a pattern between slashes is an expression: a server that
stored it as text would answer 201 and hold nothing, which is the silent misbehaviour the handshake
exists to prevent. The two constants stand at **19** today: the CSV import (`/api/import/csv` and its
preview) is what last moved them.

```bash
npm run preview   # serve the built bundle locally
```

## Dashboard

The dashboard is the default tab — the wizard replaces the shell only while nothing is configured —
and it is built around the charts being the first thing on it: the spending donut, the monthly flows
and the net-worth curve, then the metric tiles, then budgets,
anomalies, the category flags and the tracked accounts. The tiles are a grid of label and figure,
and what each one means sits behind one *Come si calcolano*.

### Cards

One card per metric with an Italian label, the amount formatted like the rest of the app, and a
short explanation. Money comes from `GET /api/metrics` as strings (or `null` when the ledger
cannot compute it); the runway is shown as months with one decimal, and "non calcolabile" when
null.

When the response marks the history as partial (`partial` or `episodic_partial`), a banner and
the affected cards say so — for example *"storico parziale: 5 mesi su 6"* — instead of
presenting the number as final.

The switch blocks of the **Categorie e regole** and **Conti** screens are optimistic: the switch
flips before the request, a failed `PATCH /api/categories/{id}` or `PATCH /api/accounts/{id}` rolls
it back and raises a toast. The flags feed straight back into the metrics list, which is refetched
after a successful change.

### Filtri

The bar above the charts carries the period chips and a *Filtri* button; the exact months, the
accounts and one category open behind it, so the charts stay where they belong. The API applies all
of it — the client never filters or sums:

- **period** — *Dal mese* / *Al mese* plus 3/6/12/24-month chips (the default is the last twelve
  months). It moves the charts and the series only: the metric cards keep the 6- and 24-month
  windows that define them, and each card says which one it used.
- **accounts** — chips, one or more. Spending is attributed to the account that paid it, so the
  accounts restrict everything that is an account fact: the spending, the liquidity, the savings
  flow and the net worth line.
- **category** — one, or *Tutte le categorie*. It restricts the spending alone: a category says
  nothing about the money coming in, nor about what the accounts are worth.

Every filtered response echoes what the server applied in `applied`, and *Aggiorna* refetches the
four readings together, so the pie, the bars and the line always describe the same window.

### Charts

Three panels, one endpoint each, all rendered with recharts and none of them doing arithmetic:
the API returns the sums, the components only turn strings into numbers.

- **Spese per categoria** — the month's spending as a donut with the total in the middle, from
  `GET /api/spending` over the filtered period. The legend beside it carries name, share and amount.
  `Uncategorized` is a slice like any other, so the total matches what actually left the
  accounts. The middle figure is sized in `cqmin` — the shorter side of that box — because the
  ring's radius follows the shorter side too: sized in `vw` it grew with the window while the
  hole stayed put, and on a wide window the amount crossed the arcs. The hole is 68% of the
  radius and the factor is 8, tuned by measuring the longest figure the ledger can produce
  (seven digits, separators and the symbol) inside the inner circle at 390 and at 846 px: 20 px
  of clearance for the live total, 7 px for a million. The currency symbol is drawn at 72% of
  the figure, which is width the digits get to use.
- **Entrate e uscite** — paired bars per month from `GET /api/flows`: income in green,
  expenses in red. The series is clipped to the months the ledger covers, and the month still
  running is dimmed, because a short bar there is a month that has not finished rather than a
  cheap month.
- **Patrimonio** — the tracked net worth from `GET /api/networth` (the period cuts the points it
  shows, not the running total), over the balances the banks
  reported (never reconstructed from movements). With no observation the panel says so; with a
  single one it prints the amount and explains that the curve starts from the second; below the
  chart each account shows its latest reported balance and its date.

A month with no data, or a ledger with nothing in it, shows a sentence per panel instead of an
empty axis.

### Giroconti

A transfer leg carries a violet *"Giroconto con «Conto»"* chip naming the account that holds its
other half (or *"Giroconto verso «Conto deposito»"* when the money went to an account of your own
that is not connected here), and *Da confermare* on a pairing the matcher proposed. The card says
what the matcher based the pair on and how sure it is, in words: two banks naming each other's
account is the strongest evidence there is, and the same amount on the same day is not enough to
overrule it. The **Giroconti** filter narrows the month to them, or excludes them.

Tapping a leg opens the transfer sheet instead of the category picker, because a leg has no
category to choose. It shows what the row is attached to, the other leg (date, account, amount)
and, for a proposal, *È un giroconto* / *Non è un giroconto* (`POST
/api/transfers/{a}/{b}/review`, `POST /api/transfers/unlink`).

Tapping any other row opens the category picker with *È un giroconto* at the top, which opens the
same sheet in marking mode: *Verso un conto tuo non collegato, o il nome di chi manda il denaro*
records the movement into a declared destination (`POST /api/transfers/passthrough`, the field
suggesting the destinations from `passthrough` and the ones already recorded), or *Oppure abbinalo a
un altro movimento* lists the legs the matcher itself
would have accepted (`GET /api/transfers/{id}/candidates`) to pair it with
(`POST /api/transfers/pair`). Undoing a leg a configured label explains says so in the toast,
because the next sync will put it back.

### Splits

The category sheet of a non-transfer transaction has a *Dividi in più categorie* mode: one row
per category with its amount, *Aggiungi riga*, a remove control per row, and a live total
against the transaction amount. Saving calls `PUT /api/transactions/{id}/splits`; when the rows
do not balance the backend's `detail` is shown as-is (422), and a balanced save stores the
splits. Transactions with more than one category posting show a *"N categorie"* chip in the
lists.

### Budget

The **Budget** panel of the **Conti** screen lists every category with its monthly budget, what it
has spent in the selected month and what is left, from `GET /api/budgets?month=YYYY-MM` (current
month by default, moved by the `‹`/`›` picker beside the title).
Each row has an inline editor: *Imposta budget* / *Modifica* opens a field, *Salva* calls
`PUT /api/budgets/{id}?month=YYYY-MM` with `{"amount":"300.00"}` — the month decides which
month's spend the answer reports, so the row comes back describing the month on screen — and
*Rimuovi* clears it with
`{"amount":null}`. Writes are optimistic and roll back with a toast on failure. The field accepts a
non-negative amount with at most two decimals; the endpoint itself refuses a negative amount
with 422 and rounds anything more precise to two decimals.

When the remaining amount is negative the row switches to an explicit over-budget state: a red
border and *"sforato di …"* instead of *"restano …"*. When no category has a budget yet the
block says so above the list, which still offers every editor.

### Anomalie

The **Anomalie** block lists the flagged movements from `GET /api/anomalies?days=31`: date,
category and amount, plus the Italian explanation the backend builds in `sentence`. It is
deterministic and explainable — the sentence carries the median, the score and the threshold it
was judged against. An empty state appears when nothing was flagged.

## Conti e budget

The **Conti** screen holds what manages the ledger's shape rather than reading it.

**Conti** — one row per real account: name, balance, the opening figure and date when it has one,
the 5.4 chip (*verificato al 12 set*, *non torna sui sospesi*, *non torna sul contabile*,
*discrepanza …*, or *saldo non verificato*) and the *Investimento* switch. Two actions per row:

- **Dichiara saldo** opens a sheet (date, amount, *Disponibile* / *Contabilizzata*) and posts
  `PUT /api/accounts/{id}/declaration`. The tag carries which of the bank's two figures it is
  (`manual:available`), so the assertion compares it with the computed balance that means the
  same, and the toast then says whether the two agree — the only reason to declare a figure.
- **Allinea il saldo iniziale** sits on each check (`verification.checks`) and posts
  `PUT /api/accounts/{id}/opening` with that check's date, figure and kind. It solves the opening
  so the declared figure is what the ledger now computes: the `anchor` path, which the command
  line and the app share through `Ledger.anchor_opening`. Aligning twice changes nothing.

**Nuovo conto** opens the same sheet pattern for an account no bank reports here — the broker, or
a cash account: name, institution, currency, and an opening figure with the date it refers to
(`POST /api/accounts`). The name must be new: the endpoint refuses one already in the ledger
instead of quietly handing back the existing account. An account cannot be renamed or deleted
from the app — that would mean deleting postings, and it stays a command-line operation.

## Categorie e regole

The screen holds what a category *is* and what falls into it, because those are the same decision
seen from its two ends.

The bar at the top creates a category (`POST /api/categories`): a name in *Nuova categoria*, then
*Aggiungi*. Creating a category categorizes nothing by itself — it is a place movements can be
pointed at, and they arrive from a proposal, from a rule or from a row you open.

Below it, one entry per category. The head carries the name, how many rules and movements the
category holds, and the two flags the metrics read via `PATCH /api/categories/{id}`: *Episodica* (a
rare event the accrual spreads over 24 months) and *Incomprimibile* (the part of spending that could
not be cut). The flags sit on the head that opens the rules, so a category and what fills it are read
— and decided — in one place; the switch flips before the request and rolls back on failure.

Opening an entry shows the rules that assign it — the text it looks for, how many movements it holds
right now, a category select and a *Rimuovi* — and under them the field that writes a new one. A rule
assigns the category whose head was opened, so the form is one text and one button. Writing a rule
applies it to the ledger immediately: it categorizes the movements already imported that were waiting
in the queue, and dismisses the proposal it has just answered.

A pattern written between slashes is a regular expression (`/amazon (eu|payments)/`): one rule for a
family the bank spells in too many ways to list, matched with `re.search` against the same text the
plain rules see — spaces collapsed, case ignored — so an expression and a written word describe the
same descriptions. The kind is not a column: the pattern itself says it, and `rule_pattern()` is the
only place that reads the slashes. An expression that does not compile is refused by `POST
/api/rules` with a 422 and the reason, which the screen shows as it is, so a rule that could never
match does not reach the ledger; a lone slash and `//` stay plain text, so a pattern that merely
holds a slash is not read as one by accident.

Where two patterns match, the longer pattern decides — the narrower claim — and an expression is no
exception: one written to name a family is longer than the words it replaces, while a broader one
steals nothing from a narrower text that still matches. A movement holding a category no matching rule
would give it is left alone: that one is a person's decision. Correcting
a rule moves the movements it held, removing it passes them to the broader rule that still matches,
or back to the queue. A search keeps the categories it matched and, inside them, only the rules that
matched; a category with no rule yet is still on the screen, saying so, with the field to give it
one.

## La coda

The screen opens on what needs a decision — the proposals and the transfer candidates — and only
then shows the backlog of uncategorized movements, which is work to get through rather than a
queue of decisions. The tab badge counts the decisions (`proposals_total + transfers_total`), and
the subtitle breaks the rest down: *"30 da decidere · 329 senza categoria, di cui 188 sfuggite"*.

Every row in the backlog carries what the automatic passes already made of it, from
`GET /api/review` (`review_state`, `proposed_category`):

- **proposta: <categoria>** — a pending proposal exists for that merchant, so the decision is
  already waiting in the block above.
- **sfuggita a regole, proposte e giroconti** (amber) — nothing claimed it: no rule categorized it,
  the classifier proposed nothing and the transfer matcher did not pair it. A row that reaches the
  backlog has already escaped the transfer matcher, because linking a pair moves a leg's posting to
  the clearing account; so what is left to check is the classifier.

Three filters narrow the list, all applied by the API: the state chips (*Tutte*, *Con proposta*,
*Sfuggite*), a free-text search on the description (case-insensitive) and an account select that
offers only the accounts with rows in the backlog. The counts beside the chips are the whole
backlog and never a function of the filter, so a narrow view cannot make the work look smaller.

## Proposte da confermare

The review screen opens with the **Proposte da confermare** block fed by `GET /api/suggestions`:
one card per merchant with the proposed category and its source (`classificatore` or `modello`),
and *Accetta* / *Rifiuta* wired to `POST /api/suggestions/decision` (the merchant travels in the
body). Accepting assigns the chosen category to the movements waiting for that merchant — the rule
is a separate thing the checkbox asks for — so the block and the queue are both refetched
afterwards; dismissing only drops the proposal. Both decisions are optimistic.

Every card carries the **stake** of the decision (`stake` in the response): the total waiting for
that merchant, how many movements it is, and the span they cover — one amount and one date when
exactly one movement is waiting. A proposal covers a merchant, not a movement, so this is what a yes
would settle; when nothing is waiting any more the card says so instead of showing a zero. The stake
is read with the queue's own predicate, so it cannot contradict the list underneath.

The category on a card is an editable select, pre-filled with the proposal, and *Accetta*
(`POST /api/suggestions/decision` with a `category`) assigns that category to the movements waiting
for the merchant. A **Crea una regola per «merchant»** checkbox sits above the row, off by default:
left alone, accepting writes nothing to `rules`, because a rule is a statement about the movements the
bank has not printed yet and one per accepted proposal would be one per spelling. Ticked, *Accetta*
opens a dialog whose field arrives with the merchant name and is editable — what is written there is
the rule's pattern, and `/…/` makes it an expression — and *Accetta e crea la regola* writes both the
decision and the rule; *Annulla*, the ✕ or Escape leave the proposal and its movements untouched. The
same checkbox decides the single-movement sheet, which writes the merchant name as the rule's text
with no dialog. The select's last option is *"Nessuna categoria: rifiuta la
proposta"*: with it the button becomes *Rifiuta* and the same call sends `dismiss`, because the two
outcomes are one gesture apart. The review bucket is never offered — a rule may not point at it — and
the app learns its name from the handshake instead of assuming it.

The select's last option, *Nuova categoria…*, opens a name field on the card: the category is created
(`POST /api/categories`) and arrives already chosen for that proposal, so the gesture that needed it
is one tap away.

Two buttons fill the block. **Proponi categorie** runs `POST /api/propose` (the statistical
classifier) and **Chiedi al modello** runs `POST /api/llm-suggest` (the optional LLM). Both are
disabled with a busy label while running and refresh the suggestions afterwards. If no model is
configured the second answers 503 and its `detail` is shown verbatim in the toast, which is how
the operator learns `AMONHEN_LLM_URL` / `AMONHEN_LLM_MODEL` are missing.

## PWA

- `public/manifest.webmanifest` — standalone display, theme/background `#0b0d16`, `name` identical
  to the document's `<title>`, and 192 px and 512 px icons rendered from
  `src/assets/eye-mark.svg` over the app palette: the same mark the inscription shows, drawn at 56%
  of the square, which keeps it inside the central 80% a maskable crop preserves. The 180 px
  apple-touch icon is the same drawing at the same proportion, and the document is what links it.
- `public/sw.js` — caches the hashed `/assets/*` on first fetch and nothing else. The document is
  deliberately not cached: it names the assets, so a stale copy points at files a rebuild has
  replaced, which is a blank screen and the one way an update can look like it never happened.
  `/api/*` is never cached either, so an offline shell would have nothing to show.
- The API serves `index.html` (and everything else the catch-all answers) with `Cache-Control:
  no-cache`, for the same reason: the browser must ask before using the shell, and the revalidation
  still answers 304 when nothing changed.
- `index.html` carries the manifest link, the theme colour and the `apple-mobile-web-app-*` meta
  tags. The service worker is registered in production only (`src/main.tsx`).

Icons are plain PNGs rendered from `src/assets/eye-mark.svg` — 512, 192 and 180 (apple-touch) —
by opening a throwaway page that loads the drawing and `src/styles.css` in a browser whose
viewport is the target size, then taking a screenshot of each. The mark fills the central 56% so
a maskable crop has nothing to bite.

## Design

The app has one visual identity, and it lives in the `:root` block of `src/styles.css`: the
field's three glows, the fill levels, the palette, the type scale, the radii and the two
motion curves are tokens there. A component that needs a colour reads a token.

The direction is minimal and borderless: **nothing draws a line**. A panel is a slightly
lighter fill, a control a lighter fill still, a state a tint of its own colour, and the only
lines left in the interface are the faint separators between the rows of a list.

- **The field.** A fixed layer paints an amber glow top-left, a violet one top-right and a
  teal one below, painted once and composited rather than repainted on scroll. Colours were
  chosen against the lightest patch those glows can produce and then verified on the real
  render: with the app hidden, the brightest background pixel measured `rgb(37,33,31)`.
- **Three fills, no borders.** `--fill-1` (5% white) is a resting lastra, `--fill-2` (8%) a
  control, `--fill-3` (12%) what is pressed or chosen; `--sep` (7%) is the only line. Depth
  comes from a thread of light along the top edge plus a low shadow. Measured on the real
  render against those fills over the lightest patch: body text 14.8 / 12.8 / 11.6 / 10.1,
  `--muted` 8.0 / 7.0 / 6.3 / 5.5, `--faint` 7.2 / 6.2 / 5.6 / 4.9, the brass 10.7, money in
  10.4, money out 8.1.
- **The drop-down, and who draws it.** A `select`'s menu is painted by the engine from the
  control's own colour, and a translucent colour there composites over the browser's light
  ground: a white menu with the app's near-white text inside it. Every select and its
  options therefore use one opaque fill, `--menu`, measured at 12.7:1 — including the ones
  that carry `class="input"`, where the 8% fill of the field rule had been winning on
  specificity. The arrow is this stylesheet's: `appearance: none` and a 12×8 chevron at
  16 px from the right edge, the same inset the text keeps on the other side, because the
  engine's own sat 3.5 px from that edge — inside the 22 px curve of the pill, where it
  read as crammed against the wall. Where the engine hands the menu over
  (`::picker(select)`, Chrome 135 and later, declared on the picker as well as on the
  control) it is a lastra with the panels' 18 px radius, as wide as its control, its rows
  44 px tall and the option in force in the brass that marks a chosen row everywhere else;
  without it the native menu stays, opaque and legible, with the platform's own highlight.
- **A glow on a filled control carries no offset.** The brass glow under a filled button is
  centred (`0 0 30px -8px`): with a downward offset it is not a halo around the button but a
  coloured smear detached below it — profiled on the render, the old value contributed 0
  above the pill and 30 down to 21 for 12 px below it, the new one 25 above and 22 below
  at the same distance.
- **A state is a tint, not an outline.** The semantic chips are their own colour on a 15%
  tint of it — 6.4 for attention and the app's own work, 6.3 for money in, 5.2 for money out,
  5.3 for a transfer, 5.9 for a split. 15% is the ceiling: at 22% the red and the violet drop
  below 4.5. There is no `--danger` and no `--warning` any more, because money leaving and
  what went wrong are the same colour, and attention is the app's own brass.
- **What identifies a control.** With no outline the boundary is the fill, and a subtle fill
  on this ground cannot reach the 3:1 WCAG 1.4.11 asks of a non-text cue: 5% reads at 1.15
  against the field, 8% at 1.27, 12% at 1.46. That is a deliberate trade of the borderless
  brief, affordable because every control also carries its own label or placeholder and the
  keyboard focus ring is a 2 px brass outline.
- **One family of shapes.** Buttons, chips, fields and selects are all pills; panels and
  lists use 14 to 30 px radii; nothing has a square corner — the menu a select opens
  included, wherever the engine lets this stylesheet paint it — and the browser's own
  button border is removed globally — checkboxes and radios are the one exception, since
  there the mark *is* the control.
- **Type.** Plus Jakarta Sans variable 200-800, Latin subset, 27.3 kB, kept in `src/assets/`
  so that Vite emits it into the hashed `/assets/` directory the service worker caches — a
  font in `public/` would never be cached and would come back from the network on every
  offline start. `OFL.txt` sits beside it. Figures stay tabular, and the face was picked by
  measuring that in the browser: a proportional digit breaks a column of amounts. Screen
  titles, metric values and amounts are weight 800, because the figure is what the screen
  exists to show.
- **Dense, not airy.** Screen gap 14, panel gap 10, metric gap 8, rows at 62 px: this carries
  more per screen than the airier pass before it while every control still clears 44 px.
- **Charts carry no frame at all.** No grid and no axis lines: slices and bars are gradients,
  the bars have round caps, and the exact numbers live in the tooltip. A block containing a
  chart is a lastra like the metric tiles, so one screen does not speak two languages.
- **The inscription opens the app.** The quote — "There was an eye in the Dark Tower that did
  not sleep", *The Fellowship of the Ring* — sits at the top of every section with the mark
  beside it: the Eye of Sauron, a round ball of brass with a dark slit pupil, ringed by nine
  tongues of flame that all lean the same way, above Barad-dûr drawn in three tints of the text
  colour, because the app is named after the Seat of Seeing and this is the one place that says
  so. The drawing lives in one file, `src/assets/eye-mark.svg`, and takes every colour from the
  tokens here rather than carrying literals: `src/styles.css` paints it and `public/` rasterises
  the same file for the installed icons. It is a masthead and not a hero: 56 px wide, 54.3 px
  tall, beside the words at 390 px, where the whole band measures 55.7 px — measured, because a
  band that stacks the mark above the quote takes from the dashboard exactly what it is telling
  you to look at. The wizard is the exception — a screen to be worked through has no inscription.
- **Motion.** One entrance per screen, staged 35 ms apart and eased on a spring; a press is
  answered under the finger with a scale. There is no `will-change`.
  `prefers-reduced-motion: reduce` zeroes the delays as well as the durations, because a
  zero-length animation that still waits 175 ms holds its block invisible for 175 ms.
- There is no preloader and no entrance outside that stagger: an app that has data to show
  shows it.

## Layout

Safe-area insets are respected (notch, home indicator), and the content padding carries the inset
of the two floating bars as well. The layout works from 360 px up without horizontal scrolling.
Measured at 390 px against a copy of the ledger, with `prefers-reduced-motion` on so that the
entrance animation cannot distort a measurement: the document is exactly as wide as the viewport,
no control is under 44 px, no element draws a border, no filled box is left with a corner radius
under 2 px, and at the foot of every section the last block clears the floating bar.

**Above 1024 px the window gets the column it deserves.** One phone column centred in a wide window
wastes most of it: measured before this layer existed, the column was 720 px of 1484 — 382 px empty
per side — with every panel, card and list row 692 px wide, one per row. The cap is a single token,
`--shell` (720 px, then 1100 from 1024, 1240 from 1440), and the top bar reads it too — the bottom
bar below 1024, the rail's own `--rail` above — because they are the frame of that column and not
unrelated measures. From 1024 the screen
becomes a two-column grid, and the panels that share a row are marked where they are written
(`panel--pair`: the two period charts, the accounts and the budgets) rather than guessed from what
they contain — with two charts drawn instead of three, or one of the two lists missing, a guess
leaves a panel half-wide next to an empty half. The net-worth curve has no partner and stays full
width. A list of cards — the assistant's, the rule groups — turns back into a grid of cards: each
entry gets back the radius, fill and shadow `.card-list > .card` had taken away to make it a row of
one sheet, and the sheet itself stops drawing a surface. The queue's own list is the exception: above
1024 it is the left half of a two-column panel, so its proposals stay one per row. A list of rows
(movements, accounts, budgets) keeps its sheet and its hairline at every width. From 1440 the eight
metric tiles fit on one row (145 px each; the longest figure asks for 103 of them), which is the case
a wide window exists for. Prose keeps a book's measure: `.chart-note`, `.screen__subtitle` and
`.assistant__answer` cap at 72 `ch`, and at 1484 the widest note measures 72 characters a line.

**And the sections get a rail instead of a floating pill.** A bottom bar of five words in the
middle of a window, plus a drawer for the two names that did not fit, is the phone's answer to a
question the window already answers: from 1024 the same list stands up in a column 248 px wide
down the left — full height, the drawer's shape (rounded on the right) and the bottom bar's glass,
every section named in full, the queue's badge on the one that has one. 248 and not the 232 a first
pass used: with 232 the label "Da confermare" plus the badge asked for 115 px of the 109 it had and
wrapped, leaving "Da" alone on a line. The rail is not centred in the window, and neither is
anything else any more: `.app` carries the rail's width as padding, so the column, the top bar, the
toast and the space reserved at the foot (which no bar needs now) all sit on the axis to its right.
The three shapes are one list — the item is shared by the drawer and the rail, and the bottom bar
keeps its compact variant, which is why a two-line "Da / confermare" is right there and wrong
here.

**And a sheet opens at the side, not from the floor.** A sheet that rises from the bottom is the
phone's shape: the thumb is down there, and the page that dims behind it is the page it covers. From
1024 the same `<dialog>` docks at the right edge instead — `clamp(460px, 40%, 520px)` wide, full
height, rounded on the left and flush on the right, the mirror of the rail — so the list it was
opened from stays on screen beside it. The drag handle of a bottom sheet is not drawn any more
(it promises a downward close) and the ✕ in the header is the way out; Escape, the backdrop and the
focus trap are the browser's and are untouched, because nothing about the dialog was reimplemented:
this is one block of CSS on a container that already existed. The page behind stops scrolling while
it is open (`body:has(dialog[open])`), since a panel as tall as the window is exactly where a page
sliding underneath is noticed. Below 1024 the sheet still comes from the bottom, byte for byte.

**And the movement list becomes a table, while the queue is read in two.** Five columns — date,
description, category, account, amount — is the shape to aim at, and at 1024 they do not fit: the
description was left 118 px, fifteen characters a line, in the first attempt that gave the account a
column of its own. So the account stays under the title, where the phone puts it, until 1440, and from
there it takes its own column and the description widens (537 px measured at 1484). The header sticks
under the top bar and its widths are fixed, because the header and the rows are two separate grids: an
`auto` column would be sized from each one's own content, which puts the label over the wrong column
(the header's "Categoria" is 58 px, the rows' pills up to 293). A pill too long for its column wraps
inside it rather than spilling over the account beside it. In the review queue the proposals stay on
the left and the one you pick is shown on the right — merchant, source, the category in force, the
stake, what accepting would write, and the controls themselves — while the card in the list keeps only
its head (its stake sentence would be the same sentence twice). The controls are written once and
placed in both, and the stylesheet hides the one the width does not need; the size rule travels with
them, because a copy that lands outside `.proposal` inherits the generic button row — where the button
shares the space — and next to a select as wide as its longest option that leaves the label no room at
all.

Below 1024 nothing moves, and that is checked rather than hoped: on the same ledger, against the
build before the change, every visible element's box at 390 and 768 is compared — 530, 796 and 278
per screen, no box differs — all eight screenshots (four screens at two widths) come out
byte-identical, and the bottom sheet itself, captured open at both widths, is byte-identical too.
