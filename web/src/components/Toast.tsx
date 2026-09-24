import { useEffect } from "react";

interface ToastProps {
  message: string;
  onDismiss: () => void;
}

export function Toast({ message, onDismiss }: ToastProps) {
  useEffect(() => {
    // A sync answers with one line per account, and a message nobody can finish
    // reading is a message that was not shown: the time grows with the text.
    const timer = window.setTimeout(
      onDismiss,
      Math.min(18000, Math.max(6000, message.length * 60)),
    );
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
