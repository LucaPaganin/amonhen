import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { Help } from "../components/Help";
import { formatAmount, formatDateWithYear } from "../format";
import type { AllocationOutcome, Comparison, Goal, GoalDraft, GoalProjection, Plan, Projection } from "../types";

/** How reachable a goal's money must stay, in words. */
const LIQUIDITY: Record<string, string> = {
  liquida: "Liquida, in ogni momento",
  alla_data: "Disponibile alla data",
  vincolabile: "Può restare vincolata",
};

/** A rate as an Italian reads it: "1,2%". */
function percent(value: string): string {
  return `${value.replace(".", ",")}%`;
}

function emptyGoal(today: string): GoalDraft {
  return { series: null, name: "", amount: "", target_date: "", liquidity: "alla_data", valid_from: today };
}

/** Desiderata 5.16: goals, the profile, the tax years, the margin, and fund against PAC. */
export function PlanScreen() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setPlan(await api.plan(signal));
      setError(null);
    } catch (err) {
      if (!isAbortError(err)) setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  /** Every write answers with the whole plan. */
  const write = useCallback(async (call: Promise<Plan>): Promise<string | null> => {
    try {
      setPlan(await call);
      return null;
    } catch (err) {
      return errorMessage(err);
    }
  }, []);

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Piano</h1>
          <p className="screen__subtitle">Dove vuoi arrivare, e cosa cambia fra fondo pensione e PAC.</p>
        </div>
      </header>

      {error !== null ? (
        <div className="state state--error" role="alert">
          <p>Impossibile caricare il piano: {error}</p>
          <button type="button" className="button" onClick={() => void load()}>
            Riprova
          </button>
        </div>
      ) : null}
      {plan === null && error === null ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : null}

      {plan === null ? null : (
        <>
          <Goals plan={plan} write={write} />
          <Margin plan={plan} />
          <Scenarios plan={plan} write={write} />
          <ProjectionPanel plan={plan} />
          <ComparisonPanel plan={plan} />
          <Profile plan={plan} write={write} />
          <TaxYears plan={plan} write={write} />
        </>
      )}
    </section>
  );
}

type Write = (call: Promise<Plan>) => Promise<string | null>;

function Goals({ plan, write }: { plan: Plan; write: Write }) {
  const [draft, setDraft] = useState<GoalDraft>(emptyGoal(plan.today));
  const [problem, setProblem] = useState<string | null>(null);

  const edit = (goal: Goal) => setDraft({ ...goal, valid_from: plan.today });
  const save = async () => {
    const failed = await write(api.saveGoal(draft));
    setProblem(failed);
    if (failed === null) setDraft(emptyGoal(plan.today));
  };

  return (
    <section className="panel">
      <h2 className="section-title">
        Obiettivi <Help topic="goal" label="obiettivo" />
      </h2>
      {plan.goals.length === 0 ? <p className="hint">Nessun obiettivo scritto.</p> : null}
      <ul className="trash-list">
        {plan.goals.map((goal) => (
          <li className="trash-row" key={goal.series}>
            <span className="trash-row__text">
              <strong>{goal.name}</strong> · {formatAmount(goal.amount)} entro il{" "}
              {formatDateWithYear(goal.target_date)} · {LIQUIDITY[goal.liquidity]} · vale dal{" "}
              {formatDateWithYear(goal.valid_from)}
            </span>
            <button type="button" className="button button--ghost" onClick={() => edit(goal)}>
              Cambia
            </button>
            <button
              type="button"
              className="button button--danger"
              onClick={() => void write(api.endGoal(goal.series))}
            >
              Togli
            </button>
          </li>
        ))}
      </ul>

      <h3 className="budget-voices__title">{draft.series === null ? "Nuovo obiettivo" : `Cambia ${draft.name}`}</h3>
      <div className="field">
        <label htmlFor="goal-name">Nome</label>
        <input id="goal-name" className="input" value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </div>
      <div className="field">
        <label htmlFor="goal-amount">Cifra in euro di oggi</label>
        <input id="goal-amount" className="input" inputMode="decimal" value={draft.amount}
          onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
      </div>
      <div className="field">
        <label htmlFor="goal-date">Data</label>
        <input id="goal-date" className="input" type="date" value={draft.target_date}
          onChange={(e) => setDraft({ ...draft, target_date: e.target.value })} />
      </div>
      <div className="field">
        <label htmlFor="goal-liquidity">Liquidità richiesta</label>
        <select id="goal-liquidity" className="input" value={draft.liquidity}
          onChange={(e) => setDraft({ ...draft, liquidity: e.target.value })}>
          {plan.liquidity_kinds.map((kind) => (
            <option key={kind} value={kind}>{LIQUIDITY[kind]}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="goal-from">Vale dal</label>
        <input id="goal-from" className="input" type="date" value={draft.valid_from}
          onChange={(e) => setDraft({ ...draft, valid_from: e.target.value })} />
      </div>
      {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}
      <button type="button" className="button button--primary" onClick={() => void save()}>
        Salva
      </button>
      {draft.series !== null ? (
        <button type="button" className="button button--ghost" onClick={() => setDraft(emptyGoal(plan.today))}>
          Annulla
        </button>
      ) : null}
    </section>
  );
}

function Margin({ plan }: { plan: Plan }) {
  const margin = plan.margin;
  if (margin.yearly === null) return null;
  return (
    <section className="panel">
      <h2 className="section-title">Quanto resta in un anno</h2>
      <p className="headline">{formatAmount(margin.yearly)}</p>
      <p className="chart-note">
        Entrate meno spese a tuo carico sugli ultimi {margin.months} mesi completi. In un mese ordinario
        restano {formatAmount(margin.ordinary_monthly ?? "0")}: la mediana, che le mensilità in più non spostano.
      </p>
      {margin.partial ? (
        <p className="chart-note">Il ledger ha {margin.months} mesi completi su 12: la cifra annua è al loro ritmo.</p>
      ) : null}
    </section>
  );
}

function ComparisonPanel({ plan }: { plan: Plan }) {
  const [series, setSeries] = useState<number | null>(plan.goals[0]?.series ?? null);
  const [rate, setRate] = useState("");
  const [allocations, setAllocations] = useState([{ fund: "", pac: "" }, { fund: "", pac: "" }]);
  const [result, setResult] = useState<Comparison | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  if (plan.goals.length === 0) return null;
  // A goal taken away since it was chosen falls back to the first one.
  const chosen = plan.goals.some((goal) => goal.series === series) ? (series as number) : plan.goals[0].series;
  const run = async () => {
    try {
      setResult(await api.compare(chosen, rate, allocations));
      setProblem(null);
    } catch (err) {
      setResult(null);
      setProblem(errorMessage(err));
    }
  };
  const setAllocation = (index: number, field: "fund" | "pac", value: string) =>
    setAllocations(allocations.map((item, i) => (i === index ? { ...item, [field]: value } : item)));

  return (
    <section className="panel">
      <h2 className="section-title">
        Fondo pensione contro PAC <Help topic="deduction-cap" label="tetto di deducibilità" />
      </h2>
      <div className="field">
        <label htmlFor="compare-goal">Obiettivo</label>
        <select id="compare-goal" className="input" value={chosen}
          onChange={(e) => setSeries(Number(e.target.value))}>
          {plan.goals.map((goal) => (
            <option key={goal.series} value={goal.series}>{goal.name}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="compare-rate">Rendimento annuo ipotizzato, %</label>
        <input id="compare-rate" className="input" inputMode="decimal" value={rate}
          onChange={(e) => setRate(e.target.value)} />
      </div>
      {allocations.map((item, index) => (
        <fieldset className="field plan-allocation" key={index}>
          <legend>Ripartizione {index === 0 ? "A" : "B"}, all'anno</legend>
          <label htmlFor={`fund-${index}`}>Al fondo, di tasca tua</label>
          <input id={`fund-${index}`} className="input" inputMode="decimal" value={item.fund}
            onChange={(e) => setAllocation(index, "fund", e.target.value)} />
          <label htmlFor={`pac-${index}`}>Al PAC</label>
          <input id={`pac-${index}`} className="input" inputMode="decimal" value={item.pac}
            onChange={(e) => setAllocation(index, "pac", e.target.value)} />
        </fieldset>
      ))}
      <button type="button" className="button button--primary" onClick={() => void run()}>
        Confronta
      </button>
      {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}
      {result === null ? null : <ComparisonTable result={result} />}
    </section>
  );
}

const ROWS: { label: string; value: (a: AllocationOutcome) => string }[] = [
  { label: "All'anno, in tutto", value: (a) => formatAmount(a.yearly) },
  { label: "Al fondo, di tasca tua", value: (a) => formatAmount(a.fund) },
  { label: "Al PAC", value: (a) => formatAmount(a.pac) },
  {
    label: "Contributo del datore",
    value: (a) => (a.employer_lost ? "perso: versi meno della tua percentuale" : formatAmount(a.employer)),
  },
  { label: "Dedotto", value: (a) => formatAmount(a.deductible) },
  {
    label: "Spazio sotto il tetto",
    value: (a) => (a.cap_room.startsWith("-") ? `oltre di ${formatAmount(a.cap_room.slice(1))}` : formatAmount(a.cap_room)),
  },
  { label: "Risparmio d'imposta, al PAC", value: (a) => formatAmount(a.tax_saving) },
  { label: "Aliquota all'uscita dal fondo", value: (a) => percent(a.exit_rate) },
  { label: "Fondo, netto a scadenza", value: (a) => formatAmount(a.fund_net) },
  { label: "PAC, netto a scadenza", value: (a) => formatAmount(a.pac_net) },
  {
    label: "Raggiungibile alla data dell'obiettivo",
    value: (a) => formatAmount(a.reachable) + (a.fund_reachable ? "" : " (il fondo resta vincolato)"),
  },
];

function ComparisonTable({ result }: { result: Comparison }) {
  return (
    <>
      <p className="chart-note">
        {result.goal.name}: {result.years} anni, rendimento {percent(result.return_rate)} l'anno, parametri fiscali{" "}
        {result.tax_year}.
        {result.margin_yearly !== null ? ` Il margine di un anno è ${formatAmount(result.margin_yearly)}.` : ""}
      </p>
      {result.tax_missing_year !== null ? (
        <p className="account-form__error" role="alert">
          Mancano i parametri del {result.tax_missing_year}: le cifre usano il {result.tax_year}.
        </p>
      ) : null}
      <div className="plan-scroll">
<table className="plan-table">
        <thead>
          <tr>
            <th scope="col"></th>
            <th scope="col">A</th>
            <th scope="col">B</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              {result.allocations.map((allocation, index) => (
                <td key={index}>{row.value(allocation)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
</div>
    </>
  );
}

function Profile({ plan, write }: { plan: Plan; write: Write }) {
  const [key, setKey] = useState(plan.profile[0].key);
  const [value, setValue] = useState("");
  const [from, setFrom] = useState(plan.today);
  const [problem, setProblem] = useState<string | null>(null);
  const kind = plan.profile.find((fact) => fact.key === key)?.kind;

  return (
    <section className="panel">
      <h2 className="section-title">
        Profilo <Help topic="contribution-base" label="base del versamento" />
      </h2>
      <ul className="trash-list">
        {plan.profile.map((fact) => (
          <li className="trash-row" key={fact.key}>
            <span className="trash-row__text">
              {fact.label}:{" "}
              {fact.value === null
                ? "manca"
                : `${fact.kind === "euro" ? formatAmount(fact.value) : fact.kind === "percent" ? percent(fact.value) : fact.kind === "date" ? formatDateWithYear(fact.value) : fact.value} dal ${formatDateWithYear(fact.valid_from ?? "")}`}
            </span>
          </li>
        ))}
      </ul>
      <div className="field">
        <label htmlFor="profile-key">Fatto</label>
        <select id="profile-key" className="input" value={key} onChange={(e) => setKey(e.target.value)}>
          {plan.profile.map((fact) => (
            <option key={fact.key} value={fact.key}>{fact.label}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="profile-value">Valore</label>
        <input id="profile-value" className="input" type={kind === "date" ? "date" : "text"}
          inputMode={kind === "date" ? undefined : "decimal"} value={value}
          onChange={(e) => setValue(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="profile-from">Vale dal</label>
        <input id="profile-from" className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
      </div>
      {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}
      <button
        type="button"
        className="button button--primary"
        onClick={async () => {
          const failed = await write(api.setProfileFact(key, value, from));
          setProblem(failed);
          if (failed === null) setValue("");
        }}
      >
        Salva
      </button>
    </section>
  );
}

function TaxYears({ plan, write }: { plan: Plan; write: Write }) {
  const tax = plan.tax;
  const [year, setYear] = useState(tax.current_year);
  const written = tax.years.find((item) => item.year === year)?.values ?? [];

  return (
    <section className="panel">
      <h2 className="section-title">Parametri fiscali</h2>
      {tax.current_missing.length > 0 ? (
        <p className="account-form__error" role="alert">
          {tax.used_year === null
            ? `Nessun anno ha tutti i parametri: il confronto non si calcola.`
            : `Il ${tax.current_year} ha ${tax.keys.length - tax.current_missing.length} parametri su ${tax.keys.length}: le cifre usano il ${tax.used_year}.`}
        </p>
      ) : (
        <p className="hint">Le cifre usano il {tax.used_year}.</p>
      )}
      <div className="field">
        <label htmlFor="tax-year">Anno</label>
        <input id="tax-year" className="input" type="number" value={year}
          onChange={(e) => setYear(Number(e.target.value))} />
      </div>
      <ul className="trash-list">
        {tax.keys.map((item) => {
          const current = written.find((value) => value.key === item.key);
          return (
            <TaxRow
              key={`${year}-${item.key}`}
              label={item.label}
              hint={item.kind === "brackets" ? "limite:aliquota, … , :aliquota" : item.kind === "percent" ? "%" : item.kind === "euro" ? "€" : ""}
              value={current?.value ?? ""}
              source={current?.source ?? ""}
              onSave={(value, source) =>
                write(
                  value.trim() === ""
                    ? api.deleteTaxParameter(year, item.key)
                    : api.setTaxParameter(year, item.key, value, source),
                )
              }
            />
          );
        })}
      </ul>
    </section>
  );
}

function TaxRow(props: {
  label: string;
  hint: string;
  value: string;
  source: string;
  onSave: (value: string, source: string) => Promise<string | null>;
}) {
  const [value, setValue] = useState(props.value);
  const [source, setSource] = useState(props.source);
  const [problem, setProblem] = useState<string | null>(null);
  const id = props.label.replace(/\W+/g, "-");
  return (
    <li className="field">
      <label htmlFor={`${id}-value`}>
        {props.label} {props.hint ? <span className="hint">({props.hint})</span> : null}
      </label>
      <input id={`${id}-value`} className="input" value={value} onChange={(e) => setValue(e.target.value)} />
      <label htmlFor={`${id}-source`} className="visually-hidden">Fonte di {props.label}</label>
      <input id={`${id}-source`} className="input" placeholder="Fonte" value={source}
        onChange={(e) => setSource(e.target.value)} />
      {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}
      <button type="button" className="button" onClick={async () => setProblem(await props.onSave(value, source))}>
        Salva
      </button>
    </li>
  );
}

const SCENARIO_NAMES: Record<string, string> = { prudente: "Prudente", centrale: "Centrale", favorevole: "Favorevole" };

function Scenarios({ plan, write }: { plan: Plan; write: Write }) {
  return (
    <section className="panel">
      <h2 className="section-title">
        Scenari <Help topic="scenario" label="scenario" />
      </h2>
      <p className="hint">Rendimento reale e inflazione all'anno, in percentuale, scritti da te.</p>
      <ul className="trash-list">
        {plan.scenarios.map((item) => (
          <ScenarioRow
            key={`${item.name}-${item.real_return}-${item.inflation}`}
            name={item.name}
            realReturn={item.real_return ?? ""}
            inflation={item.inflation ?? ""}
            onSave={(realReturn, inflation) => write(api.setScenario(item.name, realReturn, inflation))}
          />
        ))}
      </ul>
    </section>
  );
}

function ScenarioRow(props: {
  name: string;
  realReturn: string;
  inflation: string;
  onSave: (realReturn: string, inflation: string) => Promise<string | null>;
}) {
  const [realReturn, setRealReturn] = useState(props.realReturn);
  const [inflation, setInflation] = useState(props.inflation);
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <li className="field">
      <label htmlFor={`scenario-${props.name}-return`}>{SCENARIO_NAMES[props.name]}: rendimento reale</label>
      <input id={`scenario-${props.name}-return`} className="input" inputMode="decimal" value={realReturn}
        onChange={(e) => setRealReturn(e.target.value)} />
      <label htmlFor={`scenario-${props.name}-inflation`}>{SCENARIO_NAMES[props.name]}: inflazione</label>
      <input id={`scenario-${props.name}-inflation`} className="input" inputMode="decimal" value={inflation}
        onChange={(e) => setInflation(e.target.value)} />
      {props.realReturn === "" ? <p className="hint">Non scritto.</p> : null}
      {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}
      <button type="button" className="button"
        onClick={async () => setProblem(await props.onSave(realReturn, inflation))}>
        Salva
      </button>
    </li>
  );
}

function ProjectionPanel({ plan }: { plan: Plan }) {
  const [start, setStart] = useState("0");
  const [monthly, setMonthly] = useState("");
  const [scenario, setScenario] = useState("centrale");
  const [result, setResult] = useState<Projection | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  if (plan.goals.length === 0) return null;
  const run = async () => {
    try {
      setResult(await api.project(start, monthly.trim() === "" ? null : monthly, scenario));
      setProblem(null);
    } catch (err) {
      setResult(null);
      setProblem(errorMessage(err));
    }
  };

  return (
    <section className="panel">
      <h2 className="section-title">Dove si arriva</h2>
      <div className="field">
        <label htmlFor="projection-start">Capitale già messo da parte, €</label>
        <input id="projection-start" className="input" inputMode="decimal" value={start}
          onChange={(e) => setStart(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="projection-monthly">Versamento al mese, €</label>
        <input id="projection-monthly" className="input" inputMode="decimal" value={monthly}
          placeholder={plan.observed.monthly === null ? "" : `${plan.observed.monthly} (quello che il ledger mostra)`}
          onChange={(e) => setMonthly(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="projection-scenario">Scenario per Coast FI</label>
        <select id="projection-scenario" className="input" value={scenario}
          onChange={(e) => setScenario(e.target.value)}>
          {plan.scenarios.map((item) => (
            <option key={item.name} value={item.name}>{SCENARIO_NAMES[item.name]}</option>
          ))}
        </select>
      </div>
      <button type="button" className="button button--primary" onClick={() => void run()}>
        Proietta
      </button>
      {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}
      {result === null ? null : (
        <>
          <p className="chart-note">
            Con {formatAmount(result.start)} già messi da parte e {formatAmount(result.monthly)} al mese
            {result.monthly_observed ? " (quello che il ledger mostra)" : ""}, in euro di oggi.
          </p>
          {result.goals.map((item) => (
            <GoalProjectionTable key={item.goal.series} item={item} />
          ))}
        </>
      )}
    </section>
  );
}

function GoalProjectionTable({ item }: { item: GoalProjection }) {
  return (
    <>
      <h3 className="budget-voices__title">
        {item.goal.name}: {formatAmount(item.goal.amount)} entro il {formatDateWithYear(item.goal.target_date)}
      </h3>
      {item.note !== undefined ? <p className="hint">{item.note[0].toUpperCase() + item.note.slice(1)}.</p> : null}
      {item.projections.length === 0 ? null : (
        <div className="plan-scroll">
<table className="plan-table">
          <thead>
            <tr>
              <th scope="col"></th>
              {item.projections.map((p) => (
                <th scope="col" key={p.scenario}>{SCENARIO_NAMES[p.scenario]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Rendimento reale, inflazione</th>
              {item.projections.map((p) => (
                <td key={p.scenario}>{percent(p.real_return)}, {percent(p.inflation)}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Alla data</th>
              {item.projections.map((p) => <td key={p.scenario}>{formatAmount(p.value)}</td>)}
            </tr>
            <tr>
              <th scope="row">Si raggiunge</th>
              {item.projections.map((p) => (
                <td key={p.scenario}>{p.reaches ? "sì" : "no"}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Manca alla data</th>
              {item.projections.map((p) => (
                <td key={p.scenario}>{p.reaches ? "—" : formatAmount(p.shortfall)}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Servirebbe al mese</th>
              {item.projections.map((p) => <td key={p.scenario}>{formatAmount(p.needed_monthly)}</td>)}
            </tr>
            <tr>
              <th scope="row">La cifra in euro di quella data</th>
              {item.projections.map((p) => <td key={p.scenario}>{formatAmount(p.goal_nominal)}</td>)}
            </tr>
          </tbody>
        </table>
</div>
      )}
      {item.coast === null ? null : (
        <p className="chart-note">
          Coast FI <Help topic="coast-fi" label="Coast FI" />, scenario{" "}
          {SCENARIO_NAMES[item.coast.scenario].toLowerCase()}: {formatAmount(item.coast.capital)}.{" "}
          {item.coast.reached
            ? "Il capitale c'è già: da qui l'obiettivo cresce da solo e il resto del risparmio è libero."
            : "Il capitale non c'è ancora."}
        </p>
      )}
    </>
  );
}
