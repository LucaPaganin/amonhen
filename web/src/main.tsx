import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";

const container = document.getElementById("root");
if (!container) throw new Error("elemento #root mancante");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// The service worker caches the shell for offline use; it is pointless against the Vite dev server.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js");
  });
}
