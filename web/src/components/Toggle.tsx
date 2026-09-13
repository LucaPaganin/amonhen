interface ToggleProps {
  checked: boolean;
  label: string;
  ariaLabel?: string;
  disabled?: boolean;
  onChange: (next: boolean) => void;
}

export function Toggle({ checked, label, ariaLabel, disabled = false, onChange }: ToggleProps) {
  return (
    <label className="toggle">
      <input
        className="visually-hidden"
        type="checkbox"
        role="switch"
        aria-label={ariaLabel}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle__track" aria-hidden="true">
        <span className="toggle__thumb" />
      </span>
      <span className="toggle__label">{label}</span>
    </label>
  );
}
