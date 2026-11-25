import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { Help } from "../components/Help";
import { formatAmount, formatDateWithYear, formatMonth } from "../format";
import type { Portfolio, PortfolioPosition } from "../types";

const KINDS: Record<string, string> = {
  etf: "ETF",
  btp: "BTP",
  fondo_pensione: "Fondo pensione",
  immobile: "Casa",
};

/** A percent as an Italian reads it: "32,00%", or a dash when it cannot be read. */
function rate(value: string | null): string {
  return value === null ? "—" : `${value.replace(".", ",")}%`;
}

/** Units as an Italian reads them: "81,288", trailing zeros dropped. */
function units(value: string): string {
  return Number(value).toLocaleString("it-IT", { maximumFractionDigits: 6 });
}

/** A figure of a reconciliation in its own unit, euros or units of an instrument. */
function figure(value: string | null, unit: string): string {
  if (value === null) return "—";
  return unit === "€" ? formatAmount(value) : units(value);
}

/** The dates in a note as people read them, not as the server wrote them. */
function dated(note: string): string {
  return note.replace(/\d{4}-\d{2}-\d{2}/g, (iso) => formatDateWithYear(iso));
}

/** One month without a unit value: the page did not give it, and a person reads it elsewhere. */
function NavRow({ month, onSaved }: { month: string; onSaved: (portfolio: Portfolio) => void }) {
  const [value, setValue] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const id = `nav-${month}`;
  return (
    <li className="field">
      <label htmlFor={id}>{formatMonth(month)}</label>
      <input id={id} className="input" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
      {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}
      <button
        type="button"
        className="button"
        onClick={async () => {
          try {
            onSaved(await api.setNav(month, value.replace(",", ".")));
            setProblem(null);
          } catch (err) {
            setProblem(errorMessage(err));
          }
        }}
      >
        Salva
      </button>
    </li>
  );
}

function Row({ position }: { position: PortfolioPosition }) {
  return (
    <tr>
      <th scope="row">
        {position.name}
        {position.name.toLowerCase().includes(KINDS[position.kind].split(" ")[0].toLowerCase()) ? null : (
          <span className="hint"> {KINDS[position.kind]}</span>
        )}
      </th>
      <td>{position.value === null ? (position.note ?? "—") : formatAmount(position.value)}</td>
      <td>{position.paid === null ? "—" : formatAmount(position.paid)}</td>
      <td>{rate(position.twr)}</td>
      <td>{rate(position.mwr)}</td>
    </tr>
  );
}

/** Desiderata 5.16: what is held, what the fund still has in transit, what does not add up. */
export function PortfolioScreen({ refreshToken }: { refreshToken: number }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setPortfolio(await api.portfolio(signal));
      setError(null);
    } catch (err) {
      if (!isAbortError(err)) setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshToken]);

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Portafoglio</h1>
          <p className="screen__subtitle">Cosa possiedi e come rende, fuori dal conto della spesa.</p>
        </div>
      </header>

      {error !== null ? (
        <div className="state state--error" role="alert">
          <p>Impossibile caricare il portafoglio: {error}</p>
          <button type="button" className="button" onClick={() => void load()}>
            Riprova
          </button>
        </div>
      ) : null}
      {portfolio === null && error === null ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : null}
      {portfolio !== null && portfolio.positions.length === 0 ? (
        <p className="state">Nessuno strumento ancora: arrivano dalle fonti, non si scrivono a mano.</p>
      ) : null}

      {portfolio === null || portfolio.positions.length === 0 ? null : (
        <>
          <section className="panel">
            <h2 className="section-title">Quanto vale oggi</h2>
            <p className="headline">{formatAmount(portfolio.total.value)}</p>
            <p className="chart-note">
              Rendimento dei tuoi versamenti (MWR) {rate(portfolio.total.mwr)} all'anno, rendimento dello
              strumento (TWR) {rate(portfolio.total.twr)} <Help topic="mwr" label="MWR" />
            </p>
            {portfolio.missing.map((line) => (
              <p className="account-form__error" role="alert" key={line}>{line}</p>
            ))}
            <div className="plan-scroll">
              <table className="plan-table">
                <thead>
                  <tr>
                    <th scope="col"></th>
                    <th scope="col">Valore</th>
                    <th scope="col">Versato netto</th>
                    <th scope="col">TWR <Help topic="twr" label="TWR" /></th>
                    <th scope="col">MWR</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.positions.map((position) => (
                    <Row key={position.name} position={position} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {portfolio.nav_missing.length === 0 ? null : (
            <section className="panel">
              <h2 className="section-title">
                Valore quota da scrivere <Help topic="withheld" label="trattenuto e investito" />
              </h2>
              <p className="hint">
                La pagina della classe non ha dato il valore di questi mesi: scrivilo dal prospetto o dal sito
                del fondo. Un mese non prende mai il valore di un altro.
              </p>
              <ul className="trash-list">
                {portfolio.nav_missing.map((month) => (
                  <NavRow key={month} month={month} onSaved={setPortfolio} />
                ))}
              </ul>
            </section>
          )}

          {portfolio.fund === null ? null : (
            <section className="panel">
              <h2 className="section-title">
                Il fondo pensione <Help topic="withheld" label="trattenuto e investito" />
              </h2>
              <p className="headline">{formatAmount(portfolio.fund.in_transit)}</p>
              <p className="chart-note">
                in transito: trattenuto {formatAmount(portfolio.fund.withheld)}, investito{" "}
                {formatAmount(portfolio.fund.invested)}
              </p>
            </section>
          )}

          <section className="panel">
            <h2 className="section-title">Cosa non torna</h2>
            <p className="hint">
              Due cifre e lo scarto: nessuna si corregge da sola. <Help topic="opening" label="apertura" />
            </p>
            <div className="plan-scroll">
              <table className="plan-table">
                <thead>
                  <tr>
                    <th scope="col"></th>
                    <th scope="col">Atteso</th>
                    <th scope="col">Riportato</th>
                    <th scope="col">Scarto</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.reconciliations.map((item) => (
                    <tr key={item.label}>
                      <th scope="row">
                        {item.label}
                        {item.note !== null ? <span className="hint"> {dated(item.note)}</span> : null}
                      </th>
                      <td>{figure(item.expected, item.unit)}</td>
                      <td>{figure(item.actual, item.unit)}</td>
                      <td>{figure(item.difference, item.unit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {portfolio.series.length === 0 ? null : (
            <section className="panel">
              <h2 className="section-title">Patrimonio a fine mese</h2>
              <div className="plan-scroll">
                <table className="plan-table">
                  <thead>
                    <tr>
                      <th scope="col"></th>
                      <th scope="col">Liquidità</th>
                      <th scope="col">Portafoglio</th>
                      <th scope="col">Totale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...portfolio.series].reverse().map((point) => (
                      <tr key={point.month}>
                        <th scope="row">{formatMonth(point.month)}</th>
                        <td>{formatAmount(point.liquidity)}</td>
                        <td>{formatAmount(point.portfolio)}</td>
                        <td>{formatAmount(point.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="chart-note">
                La liquidità è la sola cifra dei mesi di autonomia: il portafoglio non entra nel conto della spesa.
              </p>
            </section>
          )}
        </>
      )}
    </section>
  );
}
