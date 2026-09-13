# AmonHen

> "The Eye of Sauron the Terrible few could endure." — J.R.R. Tolkien, *Il Silmarillion*

Named after Amon Hen, the Seat of Seeing.

Personal finance monitoring: one reconciled ledger for every connected
account, so the numbers answer "what did I actually spend, and what would
happen if I lost the salary".

The full product definition lives in
[`desiderata-monitoring-finanziario.md`](desiderata-monitoring-finanziario.md).
The system is custom and autonomous: it owns its ledger, its ingest pipeline
and (from phase 2) its own UI. Actual Budget is not a dependency.

## How it works

```
Enable Banking PSD2 ──┐
                      ├─→ normalize ─→ double-entry ledger (SQLite) ─→ metrics
CSV / OFX export ─────┘
```

- **PSD2 sync** (`uv run amonhen sync`): fetches every configured account through
  Enable Banking, with RS256 JWT auth, 30-day windows and continuation-key
  pagination. Banks cap history at roughly 90 days, so this path covers the
  present, not the past.
- **File import** (`uv run amonhen import`): CSV (one profile per bank layout) and
  OFX/QFX exports. This is how deep history is seeded, and how a bank is
  recovered when a PSD2 consent expires.
- Both paths converge on the same `transactions` table and the same dedup
  rule, and both keep the raw payload on disk in the database.
- **Review and categorize** (`uv run amonhen serve`): a mobile-first PWA over the
  FastAPI surface, with the queue of movements to confirm and the filterable
  transaction list. It is the way the system is actually used.

Every transaction is double-entry: its postings sum to zero. A spend is a
posting on a real account balanced by one on a category account; an internal
transfer leg is balanced by the transfer clearing account, which is why a
giroconto never counts as spending — by construction, not by a rule.

## Requirements

- Python 3.13+ and [`uv`](https://docs.astral.sh/uv/)
- An Enable Banking application (application ID + RS256 private key)
- `accounts.json` with the connected sessions, copied from
  `accounts.example.json`

## Usage

```bash
uv sync

uv run amonhen --help                            # short form of the entry point below
uv run amonhen --db dumps/verify.db accounts     # --db is global and picks another ledger
uv run python -m amonhen sync            # fetch all configured accounts
uv run python -m amonhen spend --month 2026-08
uv run python -m amonhen import statement.csv --account "Revolut" --profile revolut
uv run python -m amonhen accounts        # ledger accounts and balances
uv run python -m amonhen balances        # record the balances the bank declares
uv run python -m amonhen anchor --account "Revolut personale" --as-of 2026-09-12
uv run python -m amonhen balance-check --account "Revolut personale" --as-of 2026-09-12
uv run python -m amonhen validate        # every transaction must balance
uv run python -m amonhen daemon --interval-hours 6   # sync loop
uv run python -m amonhen serve --sync-interval-hours 6   # API + PWA + sync
uv run python -m amonhen rule-add "addebito sdd" "Bollette"   # a text the description contains
uv run python -m amonhen rule-remove "addebito sdd"           # drop it, movements released
uv run python -m amonhen category-add "Groceries"      # a category for the UI
uv run python -m amonhen categorize      # apply the rules
uv run python -m amonhen rules           # list them
uv run python -m amonhen metrics         # burn, accrual, runway, savings flow
uv run python -m amonhen category-flags Salute --episodic
uv run python -m amonhen account-flags "Fondo pensione" --investment
uv run python -m amonhen split 42 Groceries=30.00 Household=12.50
uv run python -m amonhen budget Groceries 300   # monthly budget
uv run python -m amonhen budgets                # budget, spent, left
uv run python -m amonhen anomalies              # explained outliers
uv run python -m amonhen suggest                # classifier proposals
uv run python -m amonhen llm-suggest            # needs AMONHEN_LLM_*
```

The PWA source lives in `web/`: `npm --prefix web install`,
`npm --prefix web run dev` (proxies `/api` to `127.0.0.1:8000`) and
`npm --prefix web run build`. The API serves the built `web/dist`.

The app has five sections, reachable from the bottom bar or from the hamburger in the top bar. The
bar switches in one tap; the drawer it opens names each section in full, says what the section
holds and carries the count of what is waiting, which is more than a fifth of the screen can.

The app opens on the **Dashboard**: three charts first (spending per category,
income against expenses per month, tracked net worth over the balances the banks
reported) and the metric cards of section 5.6, with a filter bar deciding what the
charts show — the period (two month pickers, or a 3/6/12/24-month chip), the
accounts, and one category. The period moves the charts; the accounts restrict
everything that is an account fact (spending by the account that paid it,
liquidity, savings, net worth); the category restricts the spending alone, because
a category says nothing about the money coming in. The cards keep the 6- and
24-month windows that define them — they follow accounts and categories, not the
period, and each card says which window it used. **Da confermare** is the
review queue — proposals and transfer candidates to decide, then the
uncategorized backlog with a filter and an amber flag on the movements that no
rule, proposal or transfer pairing claimed — **Movimenti** the filterable
transaction list, each transfer row marked with the account its other half sits
on and narrowable to the transfers alone, where opening a row confirms, undoes or
makes a pairing by hand, **Conti** the management section — every real account
with its balance, its opening figure and the 5.4 outcome, where you declare a
balance read off the bank, align the opening so the invariant holds again, add an
account by hand (the broker, or a bank that is not connected here), set the
monthly budget of a category and flag a category as episodic or incompressible —
and **Regole** the rules: a rule is a text the description
contains, plus the category that follows from it. One rule covers a family of
movements (`addebito sdd`, `ipercoop`, `amazon prime`) instead of one merchant
name, and each row shows how many movements the rule holds right now, so a rule
that reaches nothing shows itself. Where two patterns match, the longer one
decides — it is the narrower claim — and a movement holding a category no
matching rule would give it is left alone: that one is a person's decision.
Creating a rule categorizes what was waiting, correcting one moves the movements
it held, removing it passes them to the broader rule
that still matches, or back to the queue — so the list and the ledger never
disagree. Every number in a
chart comes from the API already summed — no aggregation happens in the browser,
and a series with no data shows a sentence instead of an empty axis.

`balance-check` is the correctness invariant from the desiderata (section
5.4): `saldo_iniziale + Σ movimenti == saldo dichiarato dalla banca`. It is an
assertion on the ingest process; a mismatch means duplicates or gaps and every
number downstream is unreliable. The bank declares two figures for the same date
and they differ by the pending movements, so both are asserted against the
computed balance that means the same — its available figure against everything,
its booked figure against the settled movements alone — and a failure names
which of the two does not match: pending movements, or the ledger itself.
`anchor` sets the opening balance from a bank-declared balance so the invariant
has a baseline, since PSD2 does not return history. It solves the opening with
the movements the declared figure actually contains: a booked balance leaves the
pending movements out of the opening instead of folding them into it. A figure
you type by hand has no bank tag to say which of the two it is, so `--kind
available|booked` says it (default `available`, the pending-inclusive one). The
app shows the outcome per account in the **Conti** section — `verificato al …`, `non torna sui sospesi`,
`non torna sul contabile`, `discrepanza …`, or `saldo non verificato` when no
balance was ever declared, which is not the same as verified: an assertion nobody
can see is not one you can lean on.

CSV profiles: `revolut`, `fineco`, `actual`. Missing one? Add an adapter
rather than transforming the file by hand.

## Connecting a bank

1. Make three places agree character for character — scheme, host, port, path:
   the address the browser reaches, `redirect_url` in `accounts.json`, and the
   callback registered in the Enable Banking dashboard. Behind Tailscale the
   cleanest address is the tailnet name with the HTTPS that Tailscale provisions:

   ```bash
   tailscale serve --bg localhost:8000   # https://<node>.<tailnet>.ts.net
   ```

   so `redirect_url` is `https://<node>.<tailnet>.ts.net/callback` and that is
   what gets registered. `http://<host>:8000/callback` works too, but Enable
   Banking rejects a non-HTTPS redirect that is not localhost, and that address
   only resolves on the machine running the app. The `:3000/callback` of earlier
   versions belongs to the Flask app this one replaced: nothing listens there, so
   the bank's redirect never arrives — which is what an expired consent looks
   like when you try to renew it.
2. Open `<that address>/connect?bank=FinecoBank&country=IT` (the bank name must
   match an Enable Banking ASPSP exactly — no guessing; for Fineco it is
   `FinecoBank`) and complete the bank login.
3. `/callback` writes the authorized session into `accounts.json`. An account the
   file already lists, by uid, is **refreshed in place**: the new session replaces
   the old one and the name and start date it had are kept, so the ledger account
   and the history already imported stay where they are. An account the file does
   not know is added. The response says which was which:

   ```json
   {"session_id": "…", "accounts": ["…"],
    "written": [{"account": "FinecoBank", "action": "refreshed"}],
    "next": "run `uv run amonhen sync` to import this session"}
   ```

   A bank that returns several accounts writes all of them (Fineco answers with
   four). Read `written`, and edit `accounts.json` to keep the ones you want
   before syncing: the ledger matches an account by the name in `notes`, so two
   entries under one name are one account and their movements would land in it
   together.
4. Import it:

   ```bash
   uv run python -m amonhen sync
   ```

   `session_expiry` in the entry is when the Enable Banking **session** stops
   being valid, not when the bank's consent ends — the consent can end first, and
   months earlier (Fineco's did). The symptom is `consent expired` in the sync and
   a 401/403 on the account, and renewing it is this flow again.

`/connect` forwards the bank's own refusal verbatim when something is wrong —
for example `Enable Banking refused the request: 400 Redirect URI not allowed`
means the registered URL and `accounts.json` disagree.

## Configuration

`accounts.json` (gitignored) holds the Enable Banking credentials and the
connected accounts. Every runtime path and tunable reads a `AMONHEN_<NAME>`
environment variable: `AMONHEN_DB_PATH`, `AMONHEN_CONFIG_FILE`,
`AMONHEN_EB_API`, `AMONHEN_SYNC_INTERVAL_HOURS`, `AMONHEN_UNCATEGORIZED`,
`AMONHEN_HOST`, `AMONHEN_PORT`.

The optional model — it proposes a category for merchants no rule covers, and it
reads the numbers back to you in **Assistente** — is configured with
`AMONHEN_LLM_URL`, `AMONHEN_LLM_API_KEY` and `AMONHEN_LLM_MODEL`.
**`AMONHEN_LLM_URL` is the whole endpoint** — the client posts to it as given,
with no path appended — so a provider's base URL is not enough:

```bash
AMONHEN_LLM_URL=https://api.deepseek.com/chat/completions
AMONHEN_LLM_MODEL=deepseek-v4-flash
AMONHEN_LLM_API_KEY=sk-…
```

`.env` carries these for docker compose; a plain `uv run` needs them in the shell,
or the `.vscode/launch.json` entry *monitor llm-suggest*, which sets the URL and
the model and takes the key from your environment. The request is a chat
completion with `temperature: 0` and `response_format: {"type": "json_object"}`,
which DeepSeek and OpenAI honour only when the prompt contains the word *json* —
the system prompt does — and the answer is accepted only for the merchants that
were asked about and the categories that already exist. Without a URL the feature
is off and the API answers 503 with an explanation; nothing else depends on it,
and it is never part of a sync.

`passthrough` declares the money that is neither spending nor income: what you
move to an account that is **not** connected to Enable Banking, and what arrives
because somebody else is paying their share or giving a bill back. Each
declaration has a destination — the virtual account the other side is recorded
into — and the texts the bank prints on those movements:

```json
"passthrough": [
  { "destination": "Conto deposito senza vincoli",
    "labels": ["Conto deposito senza vincoli"] },
  { "destination": "Rimborsi e quote",
    "labels": ["Nome di chi condivide il conto", "Nome di chi rimborsa"],
    "incoming_only": true }
]
```

A label naming another person or a firm sets `incoming_only`, and it should: the
same name matches both directions, and the name of a firm would take the premium
out of the burn as happily as it takes the reimbursement out of income. Without the
declaration those legs count as spending (the deposit account alone was the
largest single line of the burn on the real ledger) or as income (on the real
ledger, five credits of somebody else's money were the whole of one month's
*Entrate*). With it the money goes to the virtual account: out of the burn, out
of income, out of the review queue, still on the books, and its balance says how
much has moved.

Two candidates were rejected on the evidence. Pairing a refund with the debit it
compensates — same merchant, opposite amount, within *n* days — finds nothing in
the real ledger: none of those credits has a matching debit, because what
they have in common is who sent them, not what they paid for. And a *category*
named for refunds cannot work either: a category posting on a credit leaves the
credit in *Entrate* and out of every spending total.

The declaration is the systematic way; a single movement can also be recorded by
hand from **Movimenti**: open the row, *È un giroconto*, and name the own account
(the field offers the declared labels and the ones already recorded). The same
sheet answers a pairing the matcher proposed (*È un giroconto* /
*Non è un giroconto*) and pairs two movements by hand, offering only the legs the
matcher's own rules would have accepted.

## Assistente

The **Assistente** section (desiderata 5.9) reads the numbers the backend has
already computed and talks about them. It is not a chat about the world and not a
second calculator: the packet it is handed is built from the same functions the
screens read, so the prose and the charts cannot be about two different ledgers.

Three rules are enforced in code rather than promised in a prompt.

- **Every number in the prose was sent.** The reading is checked token by token
  against the figures of the packet — "1.234,56" and "1234.56" are the same
  figure, an Italian date is folded to the ISO the packet uses — and refused whole
  if it cites anything else. A refusal is recorded and never shown.
- **A proposal names something the request contained**: a merchant and a category
  that were in the packet, or a category with no budget and a positive amount.
  Anything else is dropped and logged. Nothing is written to the ledger: a
  category proposal waits in `merchant_suggestions` where every other proposal
  waits, a budget one in `budget_proposals`, and a person accepts either.
- **Nothing identifying is sent**: no IBAN, no account number, no raw payload,
  and no counterparty that is not already the normalized merchant. An IBAN
  printed inside a bank description is replaced by `[iban]` before the packet
  leaves the process.

The question and a fingerprint of the data are the key: asking the same thing
about the same figures does not reach the model twice. The fingerprint covers the
figures, not the merchant list — that list changes because the assistant answered,
and hashing it would make the same question cost a second call. Calls are counted
per day (`CALL_LIMIT`, 20) and the count is on the screen; the model, the
fingerprint and the answer are kept in `assistant_readings`, so a reading can be
read again in six months knowing what it was based on.

Where the question is born, the section is reachable from there: **Cosa è
cambiato?** on the dashboard, **Regge?** on a budget row. Either one opens the
section and asks about *that* figure. Without `AMONHEN_LLM_URL` the section says
it is off, and nothing else in the app depends on it.

## On the NAS

`docker-compose.yaml` builds and runs everything; nothing else is needed.

```bash
cp .env.example .env          # fill AMONHEN_LLM_API_KEY, adjust the cadence
docker compose up -d --build
docker compose logs -f amonhen
```

What it mounts, and why:

- `./accounts.json` → `/config/accounts.json`, **writable**: `/callback` writes a
  new authorization there.
- `./private.pem` → `/config/private.pem`, read-only. `pem_path` is resolved
  relative to the config file, so the same `accounts.json` works in the checkout
  and behind the mount.
- the volume `amonhen-data` → `/data`, where `AMONHEN_DB_PATH` points. That
  variable is also what keeps the ledger somewhere the `amonhen` user can write:
  a bare `docker run` without it defaults the database inside `/app`.
- `web/dist` is built inside the image, so the API serves the PWA itself.

The port is published on `${AMONHEN_BIND_ADDRESS:-127.0.0.1}:8000`: the container
is reachable from the host, and Tailscale carries it to the phone. To use it from
outside the house — including the OAuth callback above — serve it over the
tailnet:

```bash
tailscale serve --bg localhost:8000    # https://<node>.<tailnet>.ts.net
tailscale serve status
```

The image declares a `HEALTHCHECK` on `/api/health`, so `docker ps` says
`healthy` while the process is up: the quickest way to tell a working app from a
crashed one without a shell on the NAS. The Python and the bundle live in the
image, so a code change means `docker compose up -d --build`.

Two mounts carry state and one is written to while the app runs: `/data` holds the
ledger, `/config` holds `accounts.json`, and the container's user (uid 10001) must
be able to **write the file** — the OAuth callback rewrites it. The image creates
both directories owned by that user, but a bind-mounted file keeps the host's own
mode: on a Linux NAS make it writable by 10001 (`chown 10001:10001 accounts.json`,
or `chmod 664` with the container's group), or `/callback` will fail with a
permission error while everything else works.

The image defaults the two state paths (`/data/amonhen.db`, `/config/accounts.json`),
so a bare `docker run` with nothing but the config mount comes up instead of dying on
a root-owned `/app`. It does **not** default the bind address: `settings.py` keeps
`127.0.0.1` because the API has no authentication, and a published port is a
decision. compose sets `AMONHEN_HOST=0.0.0.0` for you; a bare run needs it too, or
the port answers nothing.

## Layout

|Path|Role|
|---|---|
|`amonhen/db.py`|SQLite schema: accounts, transactions, postings, transfer links, reported balances|
|`amonhen/ledger.py`|The single write path; dedup, pending→booked, spend and balance queries|
|`amonhen/providers/`|Enable Banking client and payload normalization|
|`amonhen/adapters/`|CSV/OFX import, one profile per bank layout|
|`amonhen/sync.py`|Per-account fetch → normalize → ledger|
|`amonhen/transfers.py`|Internal-transfer candidate graph, linking, and the candidates a manual pairing may choose|
|`amonhen/matching.py`|Maximum-weight bipartite matching|
|`amonhen/merchants.py`|Merchant normalization and the rules on the description|
|`amonhen/metrics.py`|Burn, episodic accrual, runway, savings flow, and the dashboard series|
|`amonhen/anomalies.py`|Deterministic, explained outliers (robust z-score on MAD)|
|`amonhen/classifier.py`|Char n-gram logistic classifier proposing categories|
|`amonhen/llm.py`|The one place a chat-completion request is built, sent and parsed|
|`amonhen/suggestions.py`|Optional LLM proposals for unseen merchants|
|`amonhen/assistant.py`|Desiderata 5.9: a reading of the numbers already computed, and the guards on it|
|`amonhen/api.py`|FastAPI surface and PWA host|
|`amonhen/cli.py`|`python -m amonhen`|
|`web/`|React PWA source (built to `web/dist`, served by the API)|
|`tools/`|Raw dump probe and the fixture anonymizer|
|`tests/fixtures/`|Anonymized Enable Banking fixtures and synthetic import fixtures|

## Known limitations

- `spend` and the burn metrics exclude transfers between tracked accounts and the
  legs the `passthrough` declarations cover. Anything else that moves
  money to an account you own but have not declared, and that the bank reports
  like a payment, still looks like spending; declaring its label — or recording
  that one movement by hand in **Movimenti** — is the fix, and
  in a Revolut export the label is the account name the transfer carries
  (`To Conto deposito senza vincoli`). `liquidity`, the runway and the
  **Patrimonio** chart count only the tracked real accounts: money moved to a
  declared but unconnected account leaves them, because its balance is not
  visible here. Tracking that account is the only way to see it come back.
- **Income is any settled inflow into a tracked account that is not a passthrough
  leg**, so a refund, or somebody paying back their share of a joint expense,
  counts as *Entrate* until a declaration or a hand mark says otherwise. What is
  not modelled is the *pair*: the credit is taken out of income, but nothing says
  which spending it compensates, so the category it would net down is left alone.
  On the real ledger a month containing no salary showed four figures of income
  because that money was either moved in from an account that is not connected
  here or sent by somebody else.
- The transfer candidate rule is deliberately conservative: equal magnitude,
  opposite sign, different tracked accounts, at most two days apart, and a pair
  where only one side names the counterparty account is refused. Ambiguity
  inside that candidate graph is resolved exactly, by maximum-weight bipartite
  matching, and every link stays reviewable from the UI. A pairing made by hand
  offers exactly those legs, so it cannot take money out of the burn on the
  operator's word alone.
- The dashboard filters are the period, a set of accounts and one category, and
  they are applied by the API. The metric cards deliberately ignore the period —
  their windows are what those metrics are — so a card and a chart can describe
  different windows; each card says which one it used.
- The `revolut` CSV profile treats every row as a settled movement; it does not
  read the export's `State` column, because no real Revolut export was
  available to verify the values.

## Development

```bash
uv run pytest
```

Fixtures under `tests/fixtures/enable_banking/` are anonymized real payloads;
do not add personal data to them. `tools/anonymize_dump.py` regenerates them
from raw dumps.

## Status

|Phase|Scope|State|
|---|---|---|
|0|Verify the Enable Banking fetch path, build parsing fixtures|done|
|1|Ingest and double-entry ledger (sync, import, balance assert)|done|
|2|Transfer reconciliation, categorization, first UI (FastAPI + React PWA)|done|
|3|Metrics, monthly summary, split editing|done|
|4|Budgets, anomalies, classifier and optional LLM proposals|done|
|UI|Dashboard: spending per category, monthly income/expense, observed net worth|done|
|UI|Dashboard filters (period, accounts, category) and the Conti section: accounts, declared balances, budgets|done|
