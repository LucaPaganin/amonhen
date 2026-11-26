// Keeps the app openable without a network: the built assets, and the last
// document the network gave.
//
// The assets are cache-first. A name under /assets/ comes from the file's
// content, so what is stored for it can never be stale.
//
// The document is network-first, never cache-first. It names the hashed assets,
// so a cached document served while the network is up would point at files a
// deploy has already replaced: the page loads a 404 script and comes up blank,
// which is also the one way an update can look like it never happened. The
// stored copy is only the fallback for a network that fails or does not answer
// within DOCUMENT_WAIT_MS — on a train the connection mostly hangs instead of
// refusing, and a fallback that waited for the browser's own timeout would not
// help. That copy and the assets it names were fetched together, so they agree.
//
// The ledger is never cached: /api/ is left alone. What the app shows offline
// comes from the package a person downloaded (desiderata 5.18), which lives in
// IndexedDB, not here. /connect and /callback are server routes that redirect
// to the bank and back, so they are left alone too.
//
// Bump CACHE to drop everything on the next activation.
const CACHE = "amonhen-shell-v3";
const DOCUMENT_KEY = "/";
const DOCUMENT_WAIT_MS = 4000;
const SERVER_ROUTES = ["/api/", "/connect", "/callback"];

self.addEventListener("install", (event) => {
  // La prima visita deve bastare: chi installa l'app e la riapre in treno senza
  // averla ricaricata non deve trovare il nulla. Il documento e gli asset che
  // nomina si scaricano qui, una volta, e da lì la shell si apre anche senza rete.
  event.waitUntil(precache().then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  // Every cache but this one belongs to an older worker: they hold files whose
  // names will never be requested again.
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(assetFor(request));
    return;
  }
  if (request.mode === "navigate" && !SERVER_ROUTES.some((route) => url.pathname.startsWith(route))) {
    event.respondWith(documentFor(request, event));
  }
  // Everything else — the manifest, the icons, the API — goes to the network.
});

// Il documento e gli asset che nomina, presi insieme: una shell senza i suoi
// script sarebbe una pagina bianca. Se qui la rete manca non è un problema —
// la prima navigazione che riesce riempie la cache come sempre.
async function precache() {
  try {
    const response = await fetch(new Request(DOCUMENT_KEY, { cache: "reload" }));
    if (!response.ok) return;
    const cache = await caches.open(CACHE);
    const copy = response.clone();
    const html = await response.text();
    await cache.put(DOCUMENT_KEY, copy);
    const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(([, path]) => path);
    await Promise.all(assets.map((path) => cache.add(path)));
  } catch {
    // Installata senza rete: la shell arriverà alla prima navigazione che riesce.
  }
}

function assetFor(request) {
  return caches.match(request).then(
    (cached) =>
      cached ??
      fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          void caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      }),
  );
}

// Every address of the app is the same document (the API answers any path with
// index.html), so one stored copy serves them all.
async function documentFor(request, event) {
  const fromNetwork = fetch(request).then((response) => {
    if (response.ok) {
      const copy = response.clone();
      // Written even when the timeout has already served the old copy, so the
      // next open starts from the newest document the network managed to give.
      event.waitUntil(caches.open(CACHE).then((cache) => cache.put(DOCUMENT_KEY, copy)));
    }
    return response;
  });

  const stored = await caches.match(DOCUMENT_KEY);
  if (!stored) return fromNetwork;

  const timeout = new Promise((resolve) => setTimeout(() => resolve(stored), DOCUMENT_WAIT_MS));
  // A refused connection falls back at once; a hanging one at the timeout.
  return Promise.race([fromNetwork.catch(() => stored), timeout]);
}
