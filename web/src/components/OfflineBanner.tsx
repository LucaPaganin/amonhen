import { formatMoment } from "../format";
import { isOffline, useOfflineState } from "../offline/session";

/**
 * Says what the screens below are reading: the copy on the phone, from when, and how
 * many changes wait to be sent. Silent online with nothing waiting.
 */
export function OfflineBanner({ onOpen }: { onOpen: () => void }) {
  const state = useOfflineState();
  const working = isOffline();
  const waiting = state.queue.length;
  if (!working && waiting === 0) return null;

  return (
    <p className="banner banner--warning offline-banner" role="status">
      {working
        ? state.bundle
          ? `Senza rete: leggi la copia scaricata il ${formatMoment(state.bundle.created_at)}.`
          : "Senza rete e nessuna copia scaricata: le schermate non hanno dati."
        : null}
      {waiting > 0 ? ` ${waiting === 1 ? "Una modifica" : `${waiting} modifiche`} da inviare.` : null}{" "}
      <button type="button" className="offline-banner__link" onClick={onOpen}>
        Apri Offline
      </button>
    </p>
  );
}
