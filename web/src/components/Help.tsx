import { createContext, useContext } from "react";

import type { GuideTopic } from "../screens/Guide";

/** Opens the Guide on a topic; provided once, by the app. */
export const HelpContext = createContext<(topic: GuideTopic) => void>(() => undefined);

/** The "?" beside a concept: the explanation lives in the Guide, not on the page. */
export function Help({ topic, label }: { topic: GuideTopic; label: string }) {
  const open = useContext(HelpContext);
  return (
    <button
      type="button"
      className="help"
      aria-label={`Cos'è: ${label}`}
      title={`Cos'è: ${label}`}
      onClick={() => open(topic)}
    >
      ?
    </button>
  );
}
