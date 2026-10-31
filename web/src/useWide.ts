import { useEffect, useState } from "react";

/** The width above which the desktop layer of `styles.css` starts. */
const WIDE = "(min-width: 1024px)";

/** Whether the window is wide: what only a PC shows is not even fetched below. */
export function useWide(): boolean {
  const [wide, setWide] = useState(() => window.matchMedia(WIDE).matches);

  useEffect(() => {
    const query = window.matchMedia(WIDE);
    const changed = () => setWide(query.matches);
    query.addEventListener("change", changed);
    return () => query.removeEventListener("change", changed);
  }, []);

  return wide;
}
