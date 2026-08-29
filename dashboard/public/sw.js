/* Phase 59 PWA Service Worker — offline queue + push */
const CACHE_NAME = "noctra-v1";
const OFFLINE_URLS = ["/", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(OFFLINE_URLS)).catch(()=>{})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter(k=>k!==CACHE_NAME).map(k=>caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  event.respondWith(
    fetch(req).then((res)=>{
      const clone = res.clone();
      caches.open(CACHE_NAME).then(c=>c.put(req, clone)).catch(()=>{});
      return res;
    }).catch(()=> caches.match(req).then(cached=> cached || caches.match("/")))
  );
});

self.addEventListener("push", (event) => {
  const data = event.data ? event.data.text() : "NOCTRA alert";
  const title = "NOCTRA";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data,
      icon: "/favicon.svg",
      badge: "/favicon.svg",
      data: { url: "/" }
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data?.url || "/")
  );
});

// Offline queue sync (Phase 59)
self.addEventListener("sync", (event) => {
  if (event.tag === "noctra-offline-queue") {
    event.waitUntil(
      // In real impl, read IndexedDB queue and POST to /api/v1/sync/offline-queue
      Promise.resolve()
    );
  }
});
