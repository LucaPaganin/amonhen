import { useEffect, useState } from "react";

import { api, errorMessage } from "../api";
import type { CsvImportRequest, CsvMapping } from "../api";
import { Toast } from "../components/Toast";
import { formatAmount } from "../format";
import { importSummary } from "../notices";
import type { CsvImportOutcome, CsvPreview } from "../types";
import { useAccounts } from "../useAccounts";

/** The date shapes a bank export is written in, as strptime formats. */
const DATE_FORMATS = [
  { value: "%Y-%m-%d", label: "2026-09-27" },
  { value: "%d/%m/%Y", label: "27/09/2026" },
  { value: "%d/%m/%y", label: "27/09/26" },
  { value: "%m/%d/%Y", label: "09/27/2026" },
  { value: "%Y-%m-%d %H:%M:%S", label: "2026-09-27 14:30:00" },
  { value: "%d/%m/%Y %H:%M:%S", label: "27/09/2026 14:30:00" },
  { value: "%Y-%m-%dT%H:%M:%S", label: "2026-09-27T14:30:00" },
];

const DELIMITERS = [
  { value: ",", label: "virgola  ," },
  { value: ";", label: "punto e virgola  ;" },
  { value: "\t", label: "tabulazione" },
  { value: "|", label: "barra verticale  |" },
];

const ENCODINGS = [
  { value: "utf-8", label: "UTF-8" },
  { value: "windows-1252", label: "Windows-1252 / Latin-1" },
];

const EMPTY_MAPPING: CsvMapping = {
  delimiter: ",",
  skip_rows: 0,
  date_column: "",
  date_format: "%Y-%m-%d",
  amount_column: "",
  debit_column: "",
  credit_column: "",
  decimal_separator: ".",
  description_columns: [],
  external_id_column: "",
  invert_sign: false,
};

/** Le scelte di forma di una mappatura, senza i nomi di colonna del file di prima. */
function prune(next: CsvMapping, columns: string[]): CsvMapping {
  const keep = (name: string) => (name !== "" && columns.includes(name) ? name : "");
  return {
    ...next,
    date_column: keep(next.date_column),
    amount_column: keep(next.amount_column),
    debit_column: keep(next.debit_column),
    credit_column: keep(next.credit_column),
    external_id_column: keep(next.external_id_column),
    description_columns: next.description_columns.map(keep),
  };
}

interface ImportScreenProps {
  /** Movements and categories changed, so the screens that count them refetch. */
  onImported: () => void;
}

/**
 * A bank export in CSV, brought into the ledger by hand.
 *
 * The formats differ per bank — columns, sign of the amount, date shape, decimal
 * separator — and the plan's answer was one adapter per format. This is that
 * adapter, chosen on the file itself: the columns are named on the screen, the
 * preview shows what the mapping reads before anything is written, and the rows
 * that do not read are listed with their line instead of stopping the import.
 */
export function ImportScreen({ onImported }: ImportScreenProps) {
  const { accounts, error: accountsError } = useAccounts();
  const [file, setFile] = useState<File | null>(null);
  const [encoding, setEncoding] = useState("utf-8");
  const [filename, setFilename] = useState("");
  const [content, setContent] = useState("");
  const [account, setAccount] = useState("");
  const [mapping, setMapping] = useState<CsvMapping>(EMPTY_MAPPING);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<CsvImportOutcome | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Un file non dice a quale conto appartiene: la scelta è di chi importa, e il
  // primo conto è quello che si importa quasi sempre.
  useEffect(() => {
    if (account === "" && accounts.length > 0) setAccount(accounts[0].name);
  }, [accounts, account]);

  // L'anteprima è anche il modo in cui si leggono i nomi delle colonne: il file
  // li porta, e senza quelli i menù non hanno niente da offrire.
  async function askPreview(next: CsvMapping, text: string, name: string, owner: string) {
    if (text === "" || owner === "") return;
    try {
      const answer = await api.csvPreview({
        filename: name,
        content: text,
        account: owner,
        mapping: next,
      });
      setPreview(answer);
      setProblem(answer.problem);
      setOutcome(null);
    } catch (error) {
      setProblem(errorMessage(error));
      setPreview(null);
    }
  }

  function change(patch: Partial<CsvMapping>) {
    const next = { ...mapping, ...patch };
    setMapping(next);
    void askPreview(next, content, filename, account);
  }

  function changeDescription(index: number, column: string) {
    // Le due parti restano due posti anche quando una è vuota: il server scarta
    // quelle vuote, e filtrare qui faceva saltare la seconda al primo posto.
    const columns = [descriptions[0], descriptions[1]];
    columns[index] = column;
    change({ description_columns: columns });
  }

  async function readFile(source: File, charset: string) {
    setNotice(null);
    setOutcome(null);
    // Il file si decodifica qui: quello che il server riceve è già testo, e la
    // codifica è una scelta della banca, non della mappatura. `windows-1252`
    // copre anche latin-1, che è quello che stampano gli estratti italiani.
    const bytes = await source.arrayBuffer();
    const text = new TextDecoder(charset).decode(bytes);
    setFilename(source.name);
    setContent(text);
    // Le colonne le porta il file, e questo può averne di diverse: si chiede
    // prima la sola intestazione — una mappatura vuota non può essere rifiutata
    // per un nome che non c'è — e si tengono le scelte di forma, lasciando
    // cadere i nomi che in questo file non esistono.
    let next = mapping;
    try {
      const header = await api.csvPreview({
        filename: source.name,
        content: text,
        account,
        mapping: EMPTY_MAPPING,
      });
      next = prune(mapping, header.columns);
      setMapping(next);
    } catch {
      // L'intestazione non si legge: l'anteprima dirà perché.
    }
    await askPreview(next, text, source.name, account);
  }

  async function run() {
    setBusy(true);
    setNotice(null);
    try {
      const body: CsvImportRequest = { filename, content, account, mapping };
      const answer = await api.csvImport(body);
      setOutcome(answer);
      setNotice(importSummary(answer));
      onImported();
    } catch (error) {
      setNotice(`Import non riuscito: ${errorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  const columns = preview?.columns ?? [];
  const descriptions = [mapping.description_columns[0] ?? "", mapping.description_columns[1] ?? ""];
  const ready = preview?.ready === true && content !== "" && account !== "";

  const columnField = (
    id: string,
    label: string,
    value: string,
    onPick: (column: string) => void,
    empty: string,
  ) => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} className="input" value={value} onChange={(event) => onPick(event.target.value)}>
        <option value="">{empty}</option>
        {columns.map((column) => (
          <option key={column} value={column}>
            {column}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Importa</h1>
          <p className="screen__subtitle">
            Un estratto conto in CSV: si dicono quali colonne sono cosa, si guarda cosa diventa, e
            poi entra nel ledger.
          </p>
        </div>
      </header>

      <div className="panel">
        <h2 className="section-title">Il file</h2>
        <div className="field file-field">
          <label htmlFor="csv-file">File CSV</label>
          <input
            id="csv-file"
            type="file"
            accept=".csv,text/csv,text/plain"
            onChange={(event) => {
              const chosen = event.target.files?.[0] ?? null;
              setFile(chosen);
              if (chosen !== null) void readFile(chosen, encoding);
            }}
          />
        </div>
        <div className="field">
          <label htmlFor="csv-encoding">Codifica del file</label>
          <select
            id="csv-encoding"
            className="input"
            value={encoding}
            onChange={(event) => {
              setEncoding(event.target.value);
              if (file !== null) void readFile(file, event.target.value);
            }}
          >
            {ENCODINGS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="csv-account">Conto</label>
          <select
            id="csv-account"
            className="input"
            value={account}
            onChange={(event) => {
              setAccount(event.target.value);
              void askPreview(mapping, content, filename, event.target.value);
            }}
          >
            <option value="">Scegli il conto</option>
            {accounts.map((item) => (
              <option key={item.id} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>
          {accountsError === null ? null : <p className="hint">{accountsError}</p>}
        </div>
        {filename === "" ? null : (
          <p className="hint">
            {filename}: {columns.length} {columns.length === 1 ? "colonna" : "colonne"},{" "}
            {preview?.parsed ?? 0} righe da importare.
          </p>
        )}
      </div>

      <div className="panel">
        <h2 className="section-title">Le colonne</h2>
        <div className="import-map">
          <div className="field">
            <label htmlFor="csv-delimiter">Separatore</label>
            <select
              id="csv-delimiter"
              className="input"
              value={mapping.delimiter}
              onChange={(event) => change({ delimiter: event.target.value })}
            >
              {DELIMITERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="csv-skip">Righe di intestazione da saltare</label>
            <input
              id="csv-skip"
              className="input"
              type="number"
              min={0}
              max={20}
              value={mapping.skip_rows}
              onChange={(event) => change({ skip_rows: Number(event.target.value) })}
            />
          </div>
          {columnField("csv-date", "Data", mapping.date_column, (column) => change({ date_column: column }), "Scegli la colonna")}
          <div className="field">
            <label htmlFor="csv-date-format">Formato della data</label>
            <select
              id="csv-date-format"
              className="input"
              value={mapping.date_format}
              onChange={(event) => change({ date_format: event.target.value })}
            >
              {DATE_FORMATS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          {columnField(
            "csv-amount",
            "Importo (già con il segno)",
            mapping.amount_column,
            (column) => change({ amount_column: column }),
            "Nessuna colonna: uso Dare e Avere",
          )}
          {columnField("csv-debit", "Dare (uscite)", mapping.debit_column, (column) => change({ debit_column: column }), "Non usata")}
          {columnField("csv-credit", "Avere (entrate)", mapping.credit_column, (column) => change({ credit_column: column }), "Non usata")}
          <div className="field">
            <label htmlFor="csv-decimals">Separatore dei decimali</label>
            <select
              id="csv-decimals"
              className="input"
              value={mapping.decimal_separator}
              onChange={(event) => change({ decimal_separator: event.target.value })}
            >
              <option value=".">punto  1,234.56</option>
              <option value=",">virgola  1.234,56</option>
            </select>
          </div>
          {columnField("csv-description", "Descrizione", descriptions[0], (column) => changeDescription(0, column), "Scegli la colonna")}
          {columnField(
            "csv-description-2",
            "Seconda parte della descrizione",
            descriptions[1],
            (column) => changeDescription(1, column),
            "Non usata",
          )}
          {columnField(
            "csv-external-id",
            "Identificativo della banca",
            mapping.external_id_column,
            (column) => change({ external_id_column: column }),
            "Non usato",
          )}
          <div className="field field--wide">
            <label htmlFor="csv-invert">Segno</label>
            <label className="import-check" htmlFor="csv-invert">
              <input
                id="csv-invert"
                type="checkbox"
                checked={mapping.invert_sign}
                onChange={(event) => change({ invert_sign: event.target.checked })}
              />
              <span>Cambia il segno: nell&apos;estratto le uscite sono positive</span>
            </label>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2 className="section-title">
          Anteprima <span className="count">{preview?.parsed ?? 0}</span>
        </h2>
        {problem === null ? null : <p className="hint">{problem}</p>}
        {preview === null || preview.rows.length === 0 ? (
          <p className="state">{content === "" ? "Scegli un file." : "Nessuna riga da mostrare."}</p>
        ) : (
          <ul className="csv-rows">
            {preview.rows.map((row) => (
              <li className="csv-row" key={row.line}>
                <span className="csv-row__line">{row.line}</span>
                <span>{row.date}</span>
                <span className="amount">{formatAmount(row.amount)}</span>
                <span className="csv-row__text">{row.description}</span>
              </li>
            ))}
          </ul>
        )}
        {preview !== null && preview.rejected.length > 0 ? (
          <>
            <p className="hint">Righe che non si leggono:</p>
            <ul className="csv-rejected">
              {preview.rejected.map((row) => (
                <li key={row.line}>
                  riga {row.line}: {row.reason}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        <div className="account-form__actions">
          <button type="button" className="button button--primary" disabled={!ready || busy} onClick={() => void run()}>
            {busy ? "Importo…" : "Importa"}
          </button>
        </div>
      </div>

      {outcome === null ? null : (
        <div className="panel">
          <h2 className="section-title">Esito</h2>
          <p className="chart-note">{importSummary(outcome)}</p>
          <ul className="flag-list">
            <li className="flag-row">
              <span className="flag-row__name">
                Movimenti entrati
                <span className="flag-row__balance">
                  {(outcome.actions.inserted ?? 0) +
                    (outcome.actions.promoted ?? 0) +
                    (outcome.actions.reimported ?? 0)}
                </span>
              </span>
            </li>
            <li className="flag-row">
              <span className="flag-row__name">
                Riportati dal cestino
                <span className="flag-row__balance">{outcome.actions.reimported ?? 0}</span>
              </span>
            </li>
            <li className="flag-row">
              <span className="flag-row__name">
                Già presenti
                <span className="flag-row__balance">{outcome.actions.duplicate ?? 0}</span>
              </span>
            </li>
            <li className="flag-row">
              <span className="flag-row__name">
                Cancellati a mano, lasciati fuori
                <span className="flag-row__balance">{outcome.actions.suppressed ?? 0}</span>
              </span>
            </li>
            <li className="flag-row">
              <span className="flag-row__name">
                Categorizzati dalle regole
                <span className="flag-row__balance">{outcome.rules}</span>
              </span>
            </li>
          </ul>
        </div>
      )}

      {notice === null ? null : <Toast message={notice} onDismiss={() => setNotice(null)} />}
    </section>
  );
}
