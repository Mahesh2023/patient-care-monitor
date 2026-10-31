// CARE-MM service worker: installable PWA + offline app shell + alert notifications.
// Never caches API responses or WebSocket traffic (patient data stays network-only).
const VERSION = "care-mm-v3.1.0";
const SHELL = [
  "/", "/static/css/app.css?v=3.1.0", "/static/js/app.js?v=3.1.0", "/static/js/api.js",
  "/static/js/audio.js", "/static/js/vision.js", "/static/js/audio-worklet.js", "/static/js/features.js",
  "/static/vendor/chart.umd.min.js", "/static/icons/icon-192.png", "/manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")
      || ["/health", "/ready", "/metrics"].includes(url.pathname)) return;  // network only
  if (url.pathname.startsWith("/static/vendor/") || url.pathname.startsWith("/static/icons/")) {
    // Immutable, large (WASM/model): cache-first.
    e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
      if (r.ok) { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(e.request, copy)); }
      return r;
    })));
    return;
  }
  // App shell: network-first so deploys are picked up, cache fallback offline.
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request).then((hit) => hit || caches.match("/"))));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) if ("focus" in c) return c.focus();
    return self.clients.openWindow("/");
  }));
});
