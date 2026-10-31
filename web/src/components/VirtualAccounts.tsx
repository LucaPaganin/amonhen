import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { formatAmount, formatDateWithYear } from "../format";
import type { Transaction, VirtualAccount } from "../types";

interface VirtualAccountsProps {
  /** Bumped by a sync: what it recorded may have moved money onto these accounts. */
  refreshToken: number;
}

/**
 * Where the money that is neither spending nor income went.
 *
 * A movement recorded as an own transfer posts its other side to a virtual
 * account — the house cheques on one, a mistaken payment and its return on
 * another — and nothing on screen said so: what had left the burn could not be
 * found again. Each account shows what it holds, and its movements on request,
 * read from the server like every other list.
 */
export function VirtualAccounts({ refreshToken }: VirtualAccountsProps) {
  const [accounts, setAccounts] = useState<VirtualAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [movements, setMovements] = useState<Transaction[] | null>(null);
  const [movementsError, setMovementsError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setAccounts(await api.virtualAccounts(signal));
      setError(null);
    } catch (caught) {
      if (isAbortError(caught)) return;
      setError(errorMessage(caught));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshToken]);

  useEffect(() => {
    if (openId === null) return;
    const controller = new AbortController();
    setMovements(null);
    setMovementsError(null);
    api
      .transactions({ virtualAccountId: openId, limit: 200 }, controller.signal)
      .then((page) => setMovements(page.items))
      .catch((caught: unknown) => {
        if (isAbortError(caught)) return;
        setMovementsError(errorMessage(caught));
      });
    return () => controller.abort();
  }, [openId, refreshToken]);

  if (error === null && accounts.length === 0) return null;

  return (
    <section className="panel">
      <h2 className="section-title">
        Conti virtuali <span className="count">{accounts.length}</span>
      </h2>
      {error !== null ? (
        <div className="state state--error" role="alert">
          <p>Impossibile caricare i conti virtuali: {error}</p>
          <button type="button" className="button" onClick={() => void load()}>
            Riprova
          </button>
        </div>
      ) : (
        <ul className="flag-list">
          {accounts.map((account) => {
            const open = openId === account.id;
            return (
              <li className="flag-row" key={account.id}>
                <span className="flag-row__name">
                  {account.name}
                  <span className="flag-row__balance">
                    {formatAmount(account.balance)}
                    {account.first_date === null
                      ? " · nessun movimento"
                      : ` · ${account.movements} ${account.movements === 1 ? "movimento" : "movimenti"} dal ${formatDateWithYear(
                          account.first_date,
                        )}`}
                  </span>
                </span>
                {account.movements === 0 ? null : (
                  <div className="account-row__actions">
                    <button
                      type="button"
                      className="button"
                      aria-expanded={open}
                      onClick={() => setOpenId(open ? null : account.id)}
                    >
                      {open ? "Nascondi i movimenti" : "Mostra i movimenti"}
                    </button>
                  </div>
                )}
                {!open ? null : movementsError !== null ? (
                  <p className="state state--error" role="alert">
                    Movimenti non leggibili: {movementsError}
                  </p>
                ) : movements === null ? (
                  <p className="state" aria-busy="true">
                    Caricamento…
                  </p>
                ) : (
                  <ul className="trash-list">
                    {movements.map((movement) => (
                      <li className="trash-row" key={movement.id}>
                        <span className="trash-row__text">
                          <span className="txn__title">{movement.merchant ?? movement.description}</span>
                          {movement.notes === null ? null : <span className="txn__note">{movement.notes}</span>}
                          <span className="txn__meta">
                            <span>{formatDateWithYear(movement.date)}</span>
                            <span>{movement.account.name}</span>
                            <span>{formatAmount(movement.amount)}</span>
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
