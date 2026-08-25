// Service worker minimal : rend l'app installable + garde la coquille hors-ligne.
const CACHE = "immo-v3";
const ASSETS = ["./", "./index.html", "./style.css", "./app.js", "./manifest.webmanifest", "./icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // L'API (Supabase) passe toujours par le réseau ; le reste peut venir du cache.
  if (url.hostname.endsWith("supabase.co")) return;
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
