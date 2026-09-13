# AmonHen — PWA

Mobile-first React PWA over the `amonhen` FastAPI backend. Five screens, reachable from
the bottom bar or from the hamburger in the top bar:

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

The category picker also offers to create a rule that looks for that merchant's text in the
description (`POST /api/rules`), and *È un giroconto* hands the row to the transfer sheet below.
The review screen can run the categorization cascade
(`POST /api/categorize`), and the picker can split one transaction across several categories.

## Navigation

Two paths into the same `onChange`: the bottom bar switches a section in one tap, and the hamburger
in the top bar opens a drawer that names each section in full, says what it holds and carries the
count of what is waiting. The drawer closes on a choice, on Escape and on the backdrop, keeps focus
inside itself while open, is `inert` while shut — nothing in it is a tab stop off screen — and hands
focus back to the hamburger when it closes. The sections and their icons are declared once, in
`src/components/Navigation.tsx`, and both paths render from that list; **Assistente** is `inBar: false`, because six labels do not fit the bar's five columns and the drawer names it in full.

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

The section is also reachable from where the question is born: *Cosa è cambiato?* on the dashboard
and *Regge?* on a budget row open it with that figure as the context (`POST /api/assistant/ask` with
`context`).

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
exists to prevent.

```bash
npm run preview   # serve the built bundle locally
```

## Dashboard

The dashboard is the default tab and is built around the charts being the first thing on it: the
spending donut, the monthly flows and the net-worth curve, then the metric tiles, then budgets,
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
  accounts.
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
body). Accepting creates
a rule whose pattern is that merchant name, which categorizes matching transactions, so the block
and the queue are both refetched afterwards; dismissing only drops the proposal. Both decisions are
optimistic.

Every card carries the **stake** of the decision (`stake` in the response): the total waiting for
that merchant, how many movements it is, and the span they cover — one amount and one date when
exactly one movement is waiting. A proposal covers a merchant, not a movement, so this is what a yes
would settle; when nothing is waiting any more the card says so instead of showing a zero. The stake
is read with the queue's own predicate, so it cannot contradict the list underneath.

The category on a card is an editable select, pre-filled with the proposal, and *Accetta*
(`POST /api/suggestions/decision` with a `category`) writes the rule with the category that was
chosen rather than the one proposed. The select's last option is *"Nessuna categoria: rifiuta la
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

- `public/manifest.webmanifest` — standalone display, theme/background `#0b1220`, 192 px and
  512 px icons.
- `public/sw.js` — caches the hashed `/assets/*` on first fetch and nothing else. The document is
  deliberately not cached: it names the assets, so a stale copy points at files a rebuild has
  replaced, which is a blank screen and the one way an update can look like it never happened.
  `/api/*` is never cached either, so an offline shell would have nothing to show.
- The API serves `index.html` (and everything else the catch-all answers) with `Cache-Control:
  no-cache`, for the same reason: the browser must ask before using the shell, and the revalidation
  still answers 304 when nothing changed.
- `index.html` carries the manifest link, the theme colour and the `apple-mobile-web-app-*` meta
  tags. The service worker is registered in production only (`src/main.tsx`).

Icons are plain PNGs generated from the same bar-chart glyph; regenerate them with any 192/512
rasterizer if the artwork changes.

## Layout

Safe-area insets are respected (notch, home indicator), the layout works from 360 px up without
horizontal scrolling, and every control has a tap target of at least 44 px.
