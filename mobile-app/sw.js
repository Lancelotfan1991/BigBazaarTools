const CACHE_NAME = 'bazaardb-v57';
const ASSETS = [
  './',
  './index.html',
  './data/heroes.json',
  './data/All.json',
  './data/Common.json',
  './data/Vanessa.json',
  './data/Karnok.json',
  './data/Dooley.json',
  './data/Pygmalien.json',
  './data/Mak.json',
  './data/Stelle.json',
  './data/Jules.json',
  './data/events.json',
  './data/monsters.json',
  './data/trainers.json',
  './data/merchants.json',
  './avatars/Vanessa.webp',
  './avatars/Karnok.webp',
  './avatars/Dooley.webp',
  './avatars/Pygmalien.webp',
  './avatars/Mak.webp',
  './avatars/Stelle.webp',
  './avatars/Jules.webp',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = event.request.url;

  // HTML: Network First
  if (event.request.destination === 'document' || url.endsWith('.html')) {
    event.respondWith(
      fetch(event.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => {
        return caches.match(event.request).then(cached =>
          cached || caches.match('./index.html')
        );
      })
    );
    return;
  }

  // Data JSON: Network First (ensure fresh data)
  if ((url.includes('/data/') || url.includes('/data-s')) && url.endsWith('.json')) {
    event.respondWith(
      fetch(event.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => {
        return caches.match(event.request);
      })
    );
    return;
  }

  // Other assets: Cache First + Network
  event.respondWith(
    caches.match(event.request).then(cached => {
      const fetchPromise = fetch(event.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);
      return cached || fetchPromise;
    })
  );
});
