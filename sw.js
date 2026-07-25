// IMPORTANT: bump this string on every deploy (v2, v3, v4...). The browser only
// detects an update when this file's bytes change, and the old cache is only
// purged/refetched when the cache name itself changes. Changing index.html
// alone is NOT enough to trigger the in-app "Check for updates" button — this
// line has to change too. Keep it in step with APP_VERSION in index.html.
const CACHE_NAME = "solar-advisor-v5";
const SHELL_FILES = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-first for weather API calls (needs fresh data), cache-first for the app shell.
self.addEventListener("fetch", (event) => {
  const url = event.request.url;

  if (url.includes("api.open-meteo.com")) {
    event.respondWith(
      fetch(event.request).catch(() => new Response(JSON.stringify({ error: "offline" }), {
        headers: { "Content-Type": "application/json" }
      }))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});