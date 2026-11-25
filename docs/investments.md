# The portfolio: sources, states, reconciliations, valuation

Part of what `CLAUDE.md` says before changing code. The product rules are section 5.16 of
the spec; this page says how they are meant to be built. Slices 1, 3, 5 and 4 (but the
broker's documents) are built, with the opening that stands in for the documents not read
yet; the historical distribution (slice 6) is not. A rule that
changes changes here and in the spec, in the same change as the code.

- **The real sources, but the broker.** `adapters/paperless.py` implements `DocumentSource`
  over Paperless's REST API (`list_new` by document type and `modified__gt`, `read`
  downloading `?original=true`, `report` with the tag and the `amonhen_*` custom fields,
  created on first use). `adapters/payslips.py` is the one place `payslip_parser` is
  imported: it calls `parse` and turns `Payslip` / `PensionStatement` into
  `PayslipContribution` / `ReadStatement`, keeping only the operations that contribute
  (own + employer + TFR > 0, the figure a payslip withholds). `adapters/borsa_italiana.py`
  implements `NavSource`: the page's *Ultima … Data* table and its *Classe*, refused when
  the class or the month is not the one asked. `composition.document_source()` builds
  Paperless from `AMONHEN_PAPERLESS_*` (None without a URL), `nav_source()` the NAV page.
  `services.portfolio.read_documents` lists, skips what `documents` already holds, reads,
  applies, records, then writes back; a write-back that fails is reported and does not undo
  the reading. The cursor per kind is in `settings` (`paperless:modified_after:<kind>`), the
  page code of the fund in its `terms` (`nav_page`). The tests use objects of the parser's
  own model with invented figures and an HTTP stub: no document and no figure of one enters
  this repository.

- **The portfolio is built on fake sources, behind the ports the real ones will fill.**
  `core/portfolio.py` (the BTP's coupons and accrued, the contribution's two states and its
  conservation, the reconciliations' arithmetic), `core/returns.py` (TWR, MWR),
  `ledger/portfolio.py` (`PortfolioMixin`, the five tables, no posting),
  `ports/portfolio.py` (`BrokerSource`, `DocumentSource`, `NavSource` and their errors) and
  `services/portfolio.py` (`sync_broker`, `read_documents`, `fetch_nav`, `take_snapshot`,
  `snapshot_through`, `reconciliations`, `overview`). `tests/memory_portfolio.py` implements
  the three ports in memory. `GET /api/portfolio` reads and writes nothing: a figure enters
  only through a use case, and the screen has no form. What the sources reported (the
  broker's position, the statement's closing units) is kept in `settings` under
  `portfolio:reported_units:<instrument id>`, so a reconciliation can show both figures
  later without calling the source.
- **An opening bridges the documents that are not there yet (spec 1.52).** An ETF or the
  fund can carry one opening, declared with `position-open` and kept in `settings` under
  `portfolio:opening:<instrument id>` as `core.portfolio.Opening` (date, units, the price or
  unit value of that day, paid in by then); its price is written as that day's price
  (source `apertura`) unless one is there, and stays when the opening retires. `holding` adds to it only what follows its date:
  an ETF's trades dated after it; for the fund, the money withheld (or paid straight) after
  it, and the units of every row invested after it — a payslip withheld before the opening
  and invested after it was in transit then, so its units were not in the opening, while
  its money stays out of `paid`. Before its date the instrument holds nothing, because the
  documents may be incomplete there. The documents dated up to the opening are reconciled
  against it (*Apertura di X contro i documenti*: units explained against units declared);
  when the gap is zero the note says so, and `position-open --retire` hands the instrument
  back to the documents alone. The returns start from the opening: its value that day is the
  first flow, the TWR starts at its price, and the whole-portfolio TWR skips the month the
  latest opening enters in, which would otherwise count as a return what grew before it.
  The opening never touches the ledger: it is the portfolio's, like the reported units.
- **A snapshot never borrows a price.** `holding(..., exact=True)` asks for the price of the
  month end itself; a held instrument without one is named and not written, and the series
  skips that month for it. A reading of today takes the latest price up to today instead.
- **`paid` is net of what came back.** A BTP's is the nominal less the coupons received, so
  the month's change in `paid` is the flow the whole-portfolio TWR subtracts. The fund's
  counts the money withheld (it is valued at cost while in transit), and a payment made
  straight to the fund. The house has no `paid`: it is in the net worth and out of every
  return.

- **The first slice is built, and it is the shape the rest follows.** Goals, the profile
  and the tax years are `ledger/planning.py` (`PlanningMixin`, no repository in front);
  the arithmetic of fund against PAC is `core/planning.py`, the first module of `core/`,
  pure; `services/planning.py` reads the margin through `metrics.period_summary` and puts
  the two together; `/api/plan` and the **Piano** section call that and nothing else.
  A goal is one row per version in a `series`, closed by `valid_to`, so a plan reopened on
  a past day reads `goals_at(that day)`; a profile fact and a budget default share the
  rule "from a day on, replacing what was written for later". The profile and tax keys are
  closed lists in `core/planning.py`, each with its kind (`euro` stored to the cent, a
  rate kept with the digits it was written with). A tax year counts only when every key
  is written (`complete_year`), and nothing ever falls back to the year before: the answer
  says which year it used and what the current one lacks. No tax value lives in code.

- **The portfolio is outside the ledger, and the ledger does not move.** Instruments,
  trades, contributions, prices and snapshots live in their own tables (section 6 of the
  spec). The ledger keeps holding only cash: the broker's liquidity, realigned by
  `Ledger.record_valuation` (`docs/ledger.md`), and `Investimenti` as the net amount paid
  in. Nothing in these tables writes a posting, so spending, runway and the 5.4 check
  cannot see market noise — the reason the two were separated in the first place
  (section 5.8).

- **The shape follows `docs/architettura.md`: functional core, use cases, ports only at
  the real edges.**
  - *Core, pure* (`core/`, or beside today's pure modules until that move happens):
    the BTP's coupon schedule and accrual, valuation per instrument, the contribution
    state machine and its conservation check, the reconciliations as functions from two
    lists to differences, TWR, MWR, Coast FI, the scenario projection and the bootstrap
    (the generator handed in, seeded). They take values and return values: no `sqlite3`,
    no `requests`, no `date.today()` — the date comes from `ports.clock.Clock`.
  - *Persistence*: the new tables are a sub-domain of the ledger, a table data gateway
    with its SQL beside it, like `ledger/balances.py`. No repository interface in front
    of it (section 5.2 of `docs/architettura.md`): one implementation, forever.
  - *Use cases* (`services/`): "read new documents", "sync the broker", "take the month's
    snapshot", "recompute the reconciliations" — the only place that orchestrates sources,
    core and persistence. Routes and CLI commands call these and nothing else.
  - *Ports*: one per external thing that changes or must be faked in a test — the
    document store (Paperless), the broker's documents, the public price pages. Each
    port speaks domain types and domain errors, never the provider's, exactly as
    `BankProvider` does after the lesson in section 5 of `docs/architettura.md`.
  - *The parser is a library, not a port.* `payslip_parser.parse` is pure (bytes in,
    value out), so the Paperless adapter calls it directly and translates its `Payslip` /
    `PensionStatement` into AmonHen's own types at the edge: no `payslip_parser` type
    crosses into the core or the ledger.

- **One source per instrument, and the source is a port.** Each source is an adapter
  behind a small port, like `ports.bank.BankProvider` for the banks, so slice 3 runs on
  fakes and slice 4 swaps in the real ones:
  - the broker: no session at all (spec 1.51). Its contract notes and its periodic
    securities statement are documents like the payslips — Paperless, then
    `payslip-parser` with a template per layout — and they fill `BrokerSource`'s trades and
    reported positions through the document adapter. The ETF's month-end close is read from
    its public page on Borsa Italiana, like the fund's unit value. The official CLI (`sc`)
    was dropped: its login is interactive and lasts 7 days at most, its transaction history
    has no documented filters or depth, and the platform has no read-only permission.
  - documents: Paperless's REST API, pulled — documents of a type modified after the
    last read, downloaded as the **original** (`/api/documents/{id}/download/?original=true`):
    the archived copy is a PDF/A regenerated by OCR and can move the text the parser
    reads by coordinates. The bytes go to `payslip_parser.parse` (private repository,
    a dependency); the outcome goes back as a tag (`amonhen:importato`, `amonhen:errore`)
    and custom fields. A document already read is skipped by its Paperless id.
  - the pension fund's NAV: the public page of the class on Borsa Italiana, once a
    month. A page that does not parse asks for the value by hand; it never reuses last
    month's.
  - the BTP: no source. Its cash flows are generated from ISIN, nominal and purchase
    date.

- **A pension contribution has two states, and a conservation law.** `trattenuto` is
  written from a payslip (own, employer, TFR — `payslip_parser.Payslip.pension`), valued
  at cost; `investito` is written from the annual statement (valuation date, NAV, units —
  `PensionStatement.operations`). The statement's rows do not map one to one onto
  payslips: the fund receives the money late and in irregular batches, sometimes months
  apart. Match by amounts in order, and keep the invariant
  `Σ trattenuto = Σ investito + in transito` true at every date; what is left in transit
  is a figure the plan shows. A contribution paid straight to the fund (a voluntary
  transfer, no payslip) is born `investito`.

- **Reconciliations report, they never correct.** Expected PAC buys against the
  broker's positions, the BTP's expected coupons against the credits on Fineco (net of
  the 12.5% tax), withheld against invested contributions, units against the statement.
  Fineco credits the gross coupon and debits the tax apart on the same day: the BTP's terms
  name that debit's text (`withholding_text`), and the credits are netted by day before
  they are matched. A BTP another bank held first is looked for from `credits_from`, the
  first day the account can show a coupon; the earlier ones went to the other bank.
  Each one is a pair of figures and their difference, shown like the 5.4 check. A
  difference is never absorbed into an opening, a balance or a price.

- **Valuation, per instrument, at month end.**
  - ETF: units × closing price of the month.
  - BTP Valore (IT0005565392): nominal plus the accrued coupon of the current quarter.
    The loyalty bonus (0.5% of nominal) counts only on the maturity date, because it is
    owed only to whoever gets there; the market price is not used.
  - Pension fund: units × NAV of **its class** (Azionario Globale C). Classes of the same
    sub-fund have different fees and NAVs.
  - The house: the ownership share, an attribute of the instrument. Where its value
    comes from is undecided.
  The canonical series is the month-end snapshot; today's figure is computed on request
  and never stored as a point of the series.

- **TWR and MWR.** TWR chains the growth factors between flows:
  `1 + R = Π (V_before_flow_i / V_after_flow_{i-1})`, with the value before a flow taken at
  the trade price, so no daily prices are needed. MWR is the rate `r` with
  `Σ CF_k (1 + r)^(−t_k) = 0`, the final value counted as a flow; solve it with a bracketed
  root finder, not Newton alone, because a sign change in the flows can give two roots.
  Both are computed per instrument and for the whole portfolio.

- **The deterministic projection is built** (`core/projection.py`, `services/projection.py`,
  the `scenarios` table). The three scenarios are written by hand and none is read as a
  default; `projection` refuses until all three exist. The monthly rate is
  `(1 + r)^(1/12) - 1`, the payment enters at each month's end, and the closed form is tested
  against the month-by-month equation. The starting capital is typed into the request until
  the portfolio exists; the pace defaults to `Ledger.invested_between` over the 12 complete
  months (net of the broker's own valuation movements). Coast FI is read only for a goal that
  may stay locked, and the goal's amount is the capital, with no withdrawal rate. What follows
  is the design of the rest:
- **Projections.** Deterministic first: `W(t+1) = W(t)·(1 + r) + c(t)` monthly, in today's
  euros, one run per scenario a person wrote. Coast FI is the capital that reaches the
  retirement goal with `c = 0` in the chosen scenario. The historical distribution
  comes after: block bootstrap of monthly real returns, blocks of 12 months, from a global
  equity index deflated by inflation, loaded once from a file; percentiles, not a mean.
  Its median has to sit near the central scenario, which is its first test. The random
  generator is seeded and the seed is shown with the result, so a figure can be
  reproduced.
