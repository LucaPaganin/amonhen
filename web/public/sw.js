// Caches the built assets and nothing else.
//
// The document is deliberately not cached: it names the hashed assets, so a
// cached document points at files a deploy has already replaced — the page then
// loads a 404 script and comes up blank. A cached document is also the only way
// an update can look like it never happened.
//
// An offline shell would be pointless anyway: the ledger is never cached (it
// lives under /api/, which this worker leaves alone), so an app loaded from the
// cache would have nothing to show.
//
// Bump CACHE to drop everything on the next activation.
const CACHE = "amonhen-assets-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
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
  // A name under /assets/ comes from the file's content, so what is stored for
  // it can never be stale. Everything else — the document, the manifest, the
  // icons, the API — goes to the network like any other request.
  if (!url.pathname.startsWith("/assets/")) return;

  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ??
        fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            void caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        }),
    ),
  );
});
