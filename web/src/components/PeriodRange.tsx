import { useState } from "react";

export interface Period {
  from: string;
  to: string;
}

interface PeriodRangeProps {
  /** Tells the two pairs of fields apart when a screen has more than one. */
  id: string;
  period: Period;
  onChange: (period: Period) => void;
}

/** A period of two dates. It reaches the screen only when it is one: a field half
    typed or a start after the end stays here, and the screen keeps what it shows. */
export function PeriodRange({ id, period, onChange }: PeriodRangeProps) {
  const [from, setFrom] = useState(period.from);
  const [to, setTo] = useState(period.to);

  const change = (nextFrom: string, nextTo: string) => {
    setFrom(nextFrom);
    setTo(nextTo);
    if (nextFrom !== "" && nextTo !== "" && nextFrom <= nextTo) {
      onChange({ from: nextFrom, to: nextTo });
    }
  };

  return (
    <div className="period-range">
      <div className="field">
        <label htmlFor={`${id}-from`}>Dal</label>
        <input
          id={`${id}-from`}
          type="date"
          value={from}
          onChange={(event) => change(event.target.value, to)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-to`}>Al</label>
        <input
          id={`${id}-to`}
          type="date"
          value={to}
          onChange={(event) => change(from, event.target.value)}
        />
      </div>
      {from !== "" && to !== "" && from > to ? (
        <p className="period-range__error" role="alert">
          La prima data viene dopo la seconda.
        </p>
      ) : null}
    </div>
  );
}
