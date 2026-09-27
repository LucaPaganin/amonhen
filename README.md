# AmonHen

> "There was an eye in the Dark Tower that did not sleep." — J.R.R. Tolkien, *The Fellowship of the Ring*

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
- **File import** (CSV from the **Importa** section of the app; CSV with a named profile per bank
  layout, or OFX/QFX, from `uv run amonhen import`). This is how deep history is seeded, and how a
  bank is recovered when a PSD2 consent expires.
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

Neither `accounts.json` nor `private.pem` has to exist before the first start:
the app writes both — the credentials and the key from its setup screen, the
connected accounts from the bank's callback — so an install with nothing
configured comes up on that screen instead of failing. `accounts.example.json`
documents the shape of the file for anyone who would rather write it by hand.

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
uv run python -m amonhen backup --dest backups --keep 14   # snapshot the ledger and its configuration
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

The document is served `no-cache` and the service worker caches only the hashed
`/assets/`, so reloading after a rebuild loads the new bundle. A cached shell points
at files that rebuild has replaced: that is a blank screen, and it is the one way an
update can look like it never happened.

The app has five sections in the bottom bar, reachable in one tap there or from the hamburger in the
top bar; the drawer it opens names each section in full, says what the section holds and carries the
count of what is waiting, which is more than a fifth of the screen can, and adds the three sections
with no column there — **Importa**, **Assistente** and **Configurazione**, the setup wizard (see
*Connecting a bank*). Above 1024 px both of those surfaces are off and the same list stands up as a rail down the
left, with all eight sections named in full. The wizard is what a fresh install opens on: with
nothing configured it replaces the app shell and starts at the first step whose requirement is
unmet, and `?setup=1` in the address forces it open, which is how the browser comes back from a
bank. Afterwards the same entry is where a bank
is added or a consent renewed.

The app opens on the **Dashboard**, which is built around one priority: the charts
come first. The period — a 3/6/12/24-month chip — sits on a bar with a *Filtri*
button, and the exact months, the accounts and one category open behind that
button, so five fields no longer push the donut below the fold. The metric tiles of
section 5.6 are compact — label and figure — and what each one means waits behind a
single *Come si calcolano*. The period moves the charts; the accounts restrict
everything that is an account fact (spending by the account that paid it,
liquidity, savings, net worth); the category restricts the spending alone, because
a category says nothing about the money coming in. The cards keep the 6- and
24-month windows that define them — they follow accounts and categories, not the
period, and each card says which window it used. **Da confermare** is the
review queue — proposals and transfer candidates to decide, then the
uncategorized backlog with a filter and an amber flag on the movements that no
rule, proposal or transfer pairing claimed. Each proposal card carries what the
decision is about, because a proposal covers a merchant and not one movement: how
much is waiting, over how many movements, and when they ran. The proposed category
is a starting point: it is editable, accepting writes the rule with the category
you chose, and choosing none is what rejecting the proposal means — **Movimenti** the
filterable
transaction list, each transfer row marked with the account its other half sits
on and narrowable to the transfers alone, where opening a row confirms, undoes or
makes a pairing by hand, writes **the note** — the only field of a movement a
person may write, and the one the sync never touches — and **deletes it** into the
account's trash, **Conti** the management section — every real account with its
balance, its opening figure and the 5.4 outcome, where you declare a balance read
off the bank, align the opening so the invariant holds again, add an account by
hand (the broker, or a bank that is not connected here), set a category's monthly
budget, empty the trash one movement at a time and decide, per account, whether the
next sync brings back the movements deleted from it — and **Categorie e regole**,
where a category is
defined and what falls into it is decided. A rule is a text the description
contains, plus the category that follows from it, and the two are one list: each
category is an entry, with the two flags the metrics read and how many rules and
how many movements it holds, the texts that assign it opening underneath and the
row that writes a new one inside the group — a rule assigns the category it sits
under, so there is nothing to choose. A new category is created here too, because
what a category is and what falls into it are the same decision: thirty patterns
are thirty decisions while eight categories are a budget. One rule covers a family of
movements (`addebito sdd`, `ipercoop`, `amazon prime`) instead of one merchant
name, and each row shows how many movements the rule holds right now, so a rule
that reaches nothing shows itself. A pattern written between slashes is a regular
expression instead — `/amazon (eu|payments)/`, one rule for a family the bank
spells in too many ways to list — and it matches the same text the plain rules
see: spaces collapsed, case ignored. Where two patterns match, the longer one
decides — it is the narrower claim, whether it is written as a text or as an
expression — and a movement holding a category no matching rule would give it is
left alone: that one is a person's decision.
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
app shows the outcome per account in the **Conti** section — `verificato al …`,
`d'accordo salvo N movimenti cancellati a mano` when the difference is exactly
what was deleted here (the fourth outcome, §5.4), `non torna sui sospesi`,
`non torna sul contabile`, `discrepanza …`, or `saldo non verificato` when no
balance was ever declared, which is not the same as verified: an assertion nobody
can see is not one you can lean on.

CSV profiles: `revolut`, `fineco`, `actual` for the command line. Missing one? Map it in the app's
**Importa** section rather than transforming the file by hand, or add an adapter when the layout has
to be a named profile.

The top bar carries one control that is not a section: **Sincronizza** asks Enable
Banking for the accounts now, inside the request, and answers with what it wrote —
per account, the movements inserted and updated, the transfers linked, the rules
applied, what a deletion kept out, and whether each account still agrees with the
bank. Waiting for the scheduled pass is not a way to look at a movement that just
happened.

## Connecting a bank

The app does this itself, in the **Configurazione** wizard (desiderata 5.10),
which is what a fresh install opens on. Five steps, in order:

1. **Credenziali** — the Enable Banking application id, the private key pasted as
   PEM, the redirect URL and the holder's name — which the sync reads so it does
   not record you as your own counterparty — saved with
   `PUT /api/setup/credentials`, which writes `accounts.json` and the key beside
   it. The redirect URL is prefilled with the address the browser is on
   (`<origin>/callback`) — the one that reaches the app, so the one the bank has
   to call back — and a value already in the file that disagrees is shown under
   the field instead of being kept as the answer. After saving, the step shows
   the saved value as a line to copy: the
   app cannot register it in the Enable Banking dashboard, so that one line stays
   manual and has to match character for character. A key that does not load as a
   private key, an application id that is empty and a redirect URL that is not
   http(s) or does not end in `/callback` are all refused before anything is
   written, with an English `detail`. The key is never read back: `/api/setup`
   answers `key_loads` — whether the file on disk loads as a private key — and
   nothing else.
2. **Banca** — the country (Italy by default) and the banks Enable Banking knows
   in it (`GET /api/setup/banks?country=IT`, already filtered and sorted by name,
   with a filter box over the list). Choosing one posts
   `POST /api/setup/connect` and sends the browser to the bank: the login happens
   there, never here. Without credentials yet that step answers 409, and a wrong
   ASPSP name comes back as the bank's own refusal (502).
3. **Conti** — every account the authorization wrote, with its name and start date
   editable (`PATCH /api/setup/accounts/{account_uid}`), a *Togli* to drop one
   (`DELETE /api/setup/accounts/{account_uid}`) and what the last authorization did
   to it — `added` or `refreshed` — from `last_connect`. The name is how the ledger
   knows the account (it is the `notes` the sync matches by), so two entries under
   one name are one account and their movements land in it together. This step is
   what replaced hand-editing the file to keep the accounts you want.
4. **Primo sync** — `POST /api/sync`, answered per account: what was fetched and
   written (`actions`), the error it hit, and its 5.4 state (`verification`), plus
   the run's `transfers_linked` and `rules_applied`. There is no toast; the
   outcome is the content of the step.
5. **Saldi e verifica** — per real account, its verification state, the form that
   declares a balance read off the bank (`PUT /api/accounts/{id}/declaration`) and
   — while the account is not verified — *Allinea il saldo iniziale*
   (`PUT /api/accounts/{id}/opening`). Closing returns to the dashboard and drops
   `?setup=1` from the address with `history.replaceState`.

Registering the callback is the one thing this side cannot do for you, and it has
to make three places agree character for character — scheme, host, port, path: the
address the browser reaches, the redirect URL the wizard derived from it, and the
callback registered in the Enable Banking dashboard. Behind Tailscale the cleanest
address is the tailnet name with the HTTPS that Tailscale provisions:

```bash
tailscale serve --bg localhost:8000   # https://<node>.<tailnet>.ts.net
```

so `redirect_url` is `https://<node>.<tailnet>.ts.net/callback` and that is what
gets registered. `http://<host>:8000/callback` works too, but Enable Banking
rejects a non-HTTPS redirect that is not localhost, and that address only resolves
on the machine running the app. The `:3000/callback` of earlier versions belongs
to the Flask app this one replaced: nothing listens there, so the bank's redirect
never arrives — which is what an expired consent looks like when you try to renew
it.

The bank sends the browser back to `/callback`, which writes the authorized session
into `accounts.json` and answers **303 to `/?setup=1`** instead of the JSON it used
to return, so the browser always lands in the app, on the accounts step. An account
the file already lists, by uid, is **refreshed in place**: the new session replaces
the old one and the name and start date a person curated are kept, so the ledger
account and the history already imported stay where they are. An account the file
does not know is added. A bank that returns several accounts writes all of them
(Fineco answers with four), and `last_connect` says which of them were added and
which refreshed.

`GET /connect?bank=FinecoBank&country=IT` does the same thing at the URL level —
the bank name must match an Enable Banking ASPSP exactly, no guessing; for Fineco
it is `FinecoBank` — so a script or a bookmark can start an authorization without
the app. It answers 302 to the bank itself, and it forwards the bank's own refusal
verbatim when something is wrong: `Enable Banking refused the request: 400 Redirect
URI not allowed` means the registered URL and `accounts.json` disagree.

Then import it:

```bash
uv run python -m amonhen sync
```

`session_expiry` in the entry is when the Enable Banking **session** stops being
valid, not when the bank's consent ends — the consent can end first, and months
earlier (Fineco's did). The symptom is `consent expired` in the sync and a 401/403
on the account, and renewing it is the same wizard again: **Configurazione** in the
drawer starts at the accounts step, so adding a bank or renewing a consent is one
tap back.

## Configuration

`accounts.json` (gitignored) holds the Enable Banking credentials and the
connected accounts. The app writes it: `PUT /api/setup/credentials` writes the
credentials, the redirect URL and the key path (and the key itself, beside the
file, since `pem_path` resolves relative to it and defaults to `./private.pem`),
the OAuth callback appends and refreshes the account entries, and the setup screen
renames and drops them. Both writers go through the same document helpers, so a
key the app knows nothing about — the `passthrough` declarations below, for one —
survives every write, and hand-editing the file stays possible: each command reads
it at startup. Every runtime path and tunable reads a `AMONHEN_<NAME>`
environment variable: `AMONHEN_DB_PATH`, `AMONHEN_CONFIG_FILE`,
`AMONHEN_EB_API`, `AMONHEN_SYNC_INTERVAL_HOURS`, `AMONHEN_UNCATEGORIZED`,
`AMONHEN_HOST`, `AMONHEN_PORT`.

The holder's name the wizard asks for is `account_holder_name`, read as
`own_names`: a movement whose counterparty is the holder's own name is relabelled
with the remittance text instead, because money coming back to you is not a payment
to yourself, and a counterparty of your own name tells the ledger nothing.

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

`.env` is read at startup, by a plain `uv run` and by docker compose alike, so a
secret lives in that one file instead of in every shell; a variable already in the
environment wins, which is what compose does with one the shell exports. The
`.vscode/launch.json` entry *monitor llm-suggest* sets the URL and the model and
takes the key from the same file. The request is a chat
completion with `temperature: 0` and `response_format: {"type": "json_object"}`,
which DeepSeek and OpenAI honour only when the prompt contains the word *json* —
the system prompt does — and the answer is accepted only for the merchants that
were asked about and the categories that already exist. Without a URL the feature
is off and the API answers 503 with an explanation; nothing else depends on it,
and it is never part of a sync.

**Nothing reaches the model by itself.** Every call is one a person asked for:
the *Chiedi al modello* button in the queue, *Chiedi* in **Assistente**, the
`llm-suggest` command, and the question a budget row composes when it opens the
section — that one arrives ready and waits for its own press. No effect, timer or
background loop asks in someone else's place, and in **Assistente** the button
names the model while the request is in flight, so a call to a third party is
always something you did and something you saw.

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

Where the question is composed, the section is reachable from there: **Regge?** on
a budget row opens it with *that* budget as the context, and the question it
composes — *Questo budget regge?* — arrives in a panel that names the model and
carries the button that asks it and one that drops it. Opening the section asks
nothing: the panel waits. Without `AMONHEN_LLM_URL` the section says it is off,
and nothing else in the app depends on it.

## On the NAS

The NAS does not need this repository. The image is built by CI and published to
GHCR when a `v*` tag is pushed (`.github/workflows/image.yml`, `linux/amd64`,
after `pytest` and the bundle build pass); the NAS pulls it and runs it. What the
NAS carries is two small files, the configuration folder and the ledger.

```bash
# Once, on the NAS, in a directory of its own (e.g. /volume1/docker/amonhen):
ssh nas mkdir -p /volume1/docker/amonhen
scp docker-compose.yaml nas:/volume1/docker/amonhen/
scp .env.example        nas:/volume1/docker/amonhen/.env    # then edit it
ssh nas 'cd /volume1/docker/amonhen && mkdir -p config backups && chown 10001:10001 config backups'

# A deployment from before the config folder existed carries the two files in the
# compose directory instead: move them in, and let the container write there.
ssh nas 'cd /volume1/docker/amonhen && mkdir -p config && mv accounts.json private.pem config/ && chown 10001:10001 config'

# At every deploy, on the NAS:
cd /volume1/docker/amonhen
docker compose pull
docker compose up -d
docker compose logs -f amonhen
```

`docker compose up -d` no longer needs `accounts.json` and `private.pem` to exist
first: compose mounts the folder, and the wizard writes both files into it. Docker
creates a missing bind-mount target as the host's root, so a fresh install on a
Linux NAS still wants `mkdir -p config backups && chown 10001:10001 config backups`
before the first `up -d`, or the setup screen cannot write its own configuration
and the nightly snapshot cannot be written either.

`AMONHEN_TAG` in `.env` decides which image runs: a version tag pins a deploy,
`latest` follows the newest one. Rolling back is editing that line and pulling
again.

Two things the pull needs to know. The image is published under the lower-case
name in `.github/workflows/image.yml` and `docker-compose.yaml` — the two must
agree, or the pull finds nothing. And the package is **public**, so the NAS needs
no credentials; the image carries code and the bundle, never a ledger, a key or a
configuration. Should it ever be private, one login on the NAS is enough:

```bash
echo "$PAT" | docker login ghcr.io -u <your-github-user> --password-stdin
```

Without compose, the same container by hand:

```bash
docker run -d --name amonhen --restart unless-stopped \
  -e AMONHEN_HOST=0.0.0.0 -e AMONHEN_DB_PATH=/data/amonhen.db \
  -e AMONHEN_CONFIG_FILE=/config/accounts.json \
  -v amonhen-data:/data \
  -v "$PWD/config:/config" \
  -v "$PWD/backups:/backups" \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/lucapaganin/amonhen:${AMONHEN_TAG:-latest}
```

What it mounts, and why:

- `./config` → `/config`, **writable**: the whole folder rather than the two
  files, because on a first start neither exists yet and the app writes its own
  `accounts.json` and `private.pem` there — the setup wizard writes the
  credentials and the key, the OAuth callback writes the authorization.
  `pem_path` is resolved relative to the configuration file, so the key is found
  beside it, and the same file works in the checkout and behind the mount.
- the volume `amonhen-data` → `/data`, where `AMONHEN_DB_PATH` points. That
  variable is also what keeps the ledger somewhere the `amonhen` user can write:
  a bare `docker run` without it defaults the database inside `/app`.
- `./backups` → `/backups`, **writable**: where `amonhen backup` writes its dated
  snapshots. A bind mount and not a volume, because the point of a snapshot is
  that something outside this container reads it — the NAS backup job that
  carries it off the machine sees a folder on the host.
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
image, so a code change means a new image, a `docker compose pull` and an `up -d`.

Three mounts carry state: `/data` holds the ledger, `/config` holds
`accounts.json` and the key beside it, and `/backups` holds the snapshots. The
container's user (uid 10001) must be able to **write in the last two** — the setup
wizard writes both files and the OAuth callback rewrites the configuration, and the
backup command writes a folder per run. The image creates all three directories
owned by that user, but a bind mount keeps the host's own ownership and mode: on a
Linux NAS make those folders writable by 10001 (`chown 10001:10001 config backups`,
or `chmod 775` with the container's group), or the wizard's save will fail with a
permission error while everything else works.

### Backup and restore

`amonhen backup` copies the ledger and the configuration into a folder named after
the moment it ran:

```bash
# Inside the container, from the compose directory on the NAS:
docker compose exec -T amonhen python -m amonhen backup --dest /backups --keep 14
# /volume1/docker/amonhen/backups/2026-09-26T101500Z/
#   amonhen.db  accounts.json  private.pem  manifest.json
```

The copy of `amonhen.db` is made with SQLite's own backup API, not by reading the
file: the app may be writing when the snapshot runs, and a file copy taken then can
be torn — a backup that looks like one and holds half a transaction is worse than
no backup. `manifest.json` records when it was taken, where the database came from,
its sha256, the row counts and which configuration files it carries; `--keep` is
what stops the folder from growing forever, and `--keep 0` prunes nothing. The
command refuses to snapshot a ledger with no accounts in it, because a wrong `--db`
would otherwise produce a successful-looking backup of an empty database that
`sqlite3.connect` had just created.

On the NAS it is a cron entry, which is also the whole of what "nightly backup"
means here:

```cron
15 3 * * *  cd /volume1/docker/amonhen && docker compose exec -T amonhen python -m amonhen backup --dest /backups --keep 14
```

**A snapshot on the NAS is not yet a backup**: it is on the same disks as the
ledger. Getting it off the machine is the NAS's own job — point its backup tool at
`/volume1/docker/amonhen/backups` — or, by hand:

```bash
docker compose cp amonhen:/backups/2026-09-26T101500Z .
```

To go back to one, stop the app first: stopping is what closes the database, so
nothing is being written while the copy lands.

```bash
cd /volume1/docker/amonhen
docker compose stop amonhen
docker compose run --rm --no-deps --user root --entrypoint sh amonhen \
  -c 'cp /backups/2026-09-26T101500Z/amonhen.db /data/amonhen.db && chown 10001:10001 /data/amonhen.db'
docker compose up -d amonhen
```

The configuration is restored the same way, into `/config`, and its files have to
end up owned by 10001 again.

The image defaults the two state paths (`/data/amonhen.db`, `/config/accounts.json`),
so a bare `docker run` with nothing but the config mount comes up instead of dying on
a root-owned `/app`. It does **not** default the bind address: `settings.py` keeps
`127.0.0.1` because the API has no authentication, and a published port is a
decision. compose sets `AMONHEN_HOST=0.0.0.0` for you; a bare run needs it too, or
the port answers nothing.

### Building the image by hand

`docker-compose.yaml` runs the published image and knows nothing about the
source; `docker-compose.build.yaml` adds the build for a machine that has the
checkout:

```bash
docker compose -f docker-compose.yaml -f docker-compose.build.yaml up -d --build
```

The two files leave the same container behind, under the same image name, so a
locally built image and a pulled one are interchangeable.

### Trying the first start before the NAS

The first start is the one thing the NAS cannot rehearse for you: the wizard writes
into a mounted folder, and a folder whose ownership is wrong fails there and only
there. `tools/rehearse_local.sh` reproduces that shape on a development machine —
the image built from the checkout, a configuration folder the host owns, the ledger
volume, the wizard — and answers Enable Banking's routes from the anonymized
fixtures in `tests/fixtures/enable_banking`, so no real consent is spent and the
bank's dashboard is not touched.

```bash
# Inside WSL, with Docker Desktop running and WSL integration on for the distro:
tools/rehearse_local.sh                 # --target DIR, --port 8000, --force
```

The port has to be free, and that is not a formality: on Docker Desktop a container
publishing `127.0.0.1:8000` does not fail while something else holds `0.0.0.0:8000`,
and the browser's loopback then answers from the container — a fresh wizard drawn
over a running, configured app, which reads as lost data. The script asks Windows
(`netstat.exe`) and refuses a port that is already listening; rehearsing next to a
local `serve` therefore means `--port 8124`.

It runs inside WSL on purpose: only there does a bind mount carry the POSIX
ownership the NAS has, which is what the first check reads — writing into `/config`
must be **refused** before the `chown 10001:10001` and allowed after. On a Windows
path Docker Desktop makes that ownership up, the write succeeds, and the script
says so instead of pretending the check passed.

It leaves the working tree alone: the checkout is copied to `$HOME/amonhen-rehearsal`
(on Linux filesystem, not the Windows one), and that folder is the whole footprint.
Walking it is done when the wizard, the sync, the snapshot and the restore have been
through once; the script prints the teardown at the end, and it has one step that is
easy to miss — the configuration and the snapshots belong to the container's user, so
they have to be emptied from inside the image before the folder can go:

```bash
cd $HOME/amonhen-rehearsal/deploy
docker compose run --rm --no-deps --user root --entrypoint sh amonhen -c 'rm -rf /config/* /backups/*'
docker compose down -v
rm -rf $HOME/amonhen-rehearsal
```

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
|`amonhen/backup.py`|Dated, consistent snapshots of the ledger and its configuration|
|`amonhen/cli.py`|`python -m amonhen`|
|`web/`|React PWA source (built to `web/dist`, served by the API)|
|`tools/`|Raw dump probe, the fixture anonymizer, the fake Enable Banking API and the Docker rehearsal|
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
|5|Assistant (§5.9): a prose reading of the computed series, with proposals to confirm|done|
|6|Sync button, a local note on a movement, deletion with tombstone and trash, per-account reimport flag|done|
|7|First setup guided by the app (§5.10), backup and restore (§5.11), the local Docker rehearsal|done|
