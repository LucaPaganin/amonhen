import { useEffect } from "react";

interface ToastProps {
  message: string;
  onDismiss: () => void;
}

export function Toast({ message, onDismiss }: ToastProps) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 6000);
    return () => window.clearTimeout(timer);
  }, [message, onDismiss]);

  return (
    <div className="toast" role="status">
      <p className="toast__message">{message}</p>
      <button type="button" className="button button--ghost" onClick={onDismiss} aria-label="Chiudi avviso">
        ✕
      </button>
    </div>
  );
}
