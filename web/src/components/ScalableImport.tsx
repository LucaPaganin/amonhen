import { useEffect, useState } from "react";

import { api, errorMessage } from "../api";
import { formatAmount, formatDateWithYear } from "../format";
import type { Account, ScalableFlow, ScalableReading } from "../types";

interface ScalableImportProps {
  accounts: Account[];
  onImported: () => void;
}

/** A file as base64, the only way a PDF travels in the API's JSON. */
function base64Of(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error ?? new Error("file non leggibile"));
    reader.readAsDataURL(file);
  });
}

function flowLine(flow: ScalableFlow): string {
  return `${formatDateWithYear(flow.date)} · ${flow.description} · ${formatAmount(flow.amount)} (conto …${flow.account})`;
}

/**
 * Scalable's monthly statements, read for what a hand-added investment account
 * cannot learn from its own movements: what it was worth on each quarter's last
 * day. The cash statements and the securities statements together give the
 * value; the difference from the ledger's balance is booked as a return. The
 * transfers the statements list are checked against the ledger, and only
 * reported: each one is a movement of the bank on the other side.
 */
export function ScalableImport({ accounts, onImported }: ScalableImportProps) {
  const candidates = accounts.filter((account) => account.investment && !account.connected);
  const [account, setAccount] = useState("");
  const [files, setFiles] = useState<{ name: string; content: string }[]>([]);
  const [reading, setReading] = useState<ScalableReading | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (account === "" && candidates.length > 0) setAccount(candidates[0].name);
  }, [candidates, account]);

  if (candidates.length === 0) return null;

  async function choose(list: FileList | null) {
    if (list === null || list.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const chosen = await Promise.all(
        Array.from(list).map(async (file) => ({ name: file.name, content: await base64Of(file) })),
      );
      setFiles(chosen);
      setReading(await api.scalablePreview({ account, files: chosen }));
    } catch (caught) {
      setError(errorMessage(caught));
      setReading(null);
    } finally {
      setBusy(false);
    }
  }

  async function write() {
    setBusy(true);
    setError(null);
    try {
      setReading(await api.scalableImport({ account, files }));
      onImported();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2 className="section-title">Estratti Scalable (PDF)</h2>
      <p className="hint">
        Gli estratti conto mensili dei conti di liquidità e gli estratti conto titoli, tutti insieme:
        dicono quanto valeva il conto alla fine di ogni trimestre, e la differenza dal saldo dei
        movimenti diventa rendimento. Servono gli estratti di ogni conto di liquidità: uno che manca del tutto non si vede. I bonifici che elencano si confrontano con il ledger.
      </p>
      <div className="field">
        <label htmlFor="scalable-account">Conto</label>
        <select
          id="scalable-account"
          className="input"
          value={account}
          onChange={(event) => {
            setAccount(event.target.value);
            setReading(null);
          }}
        >
          {candidates.map((item) => (
            <option key={item.id} value={item.name}>
              {item.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field file-field">
        <label htmlFor="scalable-files">File PDF</label>
        <input
          id="scalable-files"
          type="file"
          accept="application/pdf,.pdf"
          multiple
          disabled={busy}
          onChange={(event) => void choose(event.target.files)}
        />
      </div>
      {error === null ? null : (
        <p className="state state--error" role="alert">
          {error}
        </p>
      )}
      {reading === null ? null : (
        <>
          <p className="chart-note">
            {`${reading.statements.cash} estratti di liquidità e ${reading.statements.holdings} estratti titoli letti.`}
            {reading.unreadable.length === 0 ? "" : ` Non letti: ${reading.unreadable.join(", ")}.`}
          </p>
          {reading.valuations.length === 0 ? (
            <p className="state">Nessuna data da valutare dopo il saldo iniziale del conto.</p>
          ) : (
            <ul className="flag-list">
              {reading.valuations.map((valuation) => (
                <li className="flag-row" key={valuation.date}>
                  <span className="flag-row__name">
                    {formatDateWithYear(valuation.date)}: {formatAmount(valuation.value)}
                    <span className="flag-row__balance">
                      {`titoli ${formatAmount(valuation.securities)} · liquidità ${formatAmount(
                        Object.values(valuation.cash).reduce((sum, amount) => sum + Number(amount), 0),
                      )} · dai movimenti ${formatAmount(valuation.balance)} · rendimento ${formatAmount(
                        valuation.difference,
                      )}`}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {reading.unvalued.map((line) => (
            <p className="hint" key={line}>
              Non valutabile — {line}
            </p>
          ))}
          {reading.unmatched.length === 0 ? (
            <p className="hint">Ogni bonifico degli estratti ha il suo movimento nel ledger.</p>
          ) : (
            <>
              <p className="hint">
                Bonifici negli estratti senza un movimento nel ledger: vanno importati dalla banca
                dall'altra parte, non da qui.
              </p>
              <ul className="trash-list">
                {reading.unmatched.map((flow) => (
                  <li className="trash-row" key={`${flow.account}:${flow.date}:${flow.amount}`}>
                    <span className="trash-row__text">{flowLine(flow)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {reading.written === undefined ? (
            reading.valuations.length === 0 ? null : (
              <div className="account-row__actions">
                <button type="button" className="button button--primary" disabled={busy} onClick={() => void write()}>
                  Registra {reading.valuations.length === 1 ? "la valutazione" : `le ${reading.valuations.length} valutazioni`}
                </button>
              </div>
            )
          ) : (
            <p className="chart-note">
              {`Registrate ${reading.written.length} valutazioni. Il saldo di ${account} ora è ${formatAmount(
                reading.account?.balance ?? "0",
              )}.`}
            </p>
          )}
        </>
      )}
    </div>
  );
}
