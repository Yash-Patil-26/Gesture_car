// Service Worker — caches all app assets permanently
// After first load with internet, app runs offline
// model.onnx cached on first fetch — loads instantly after

const CACHE_NAME = 'gesture-car-v3';

// Assets to pre-cache on install
const PRECACHE = [
  '/Gesture_Car/',
  '/Gesture_Car/index.html',
  '/Gesture_Car/manifest.json',
];

// Install — pre-cache critical assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.allSettled(
        PRECACHE.map(url =>
          cache.add(url).catch(err =>
            console.warn('[SW] Pre-cache failed for:', url, err)
          )
        )
      )
    ).then(() => self.skipWaiting())
  );
});

// Activate — remove old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch — cache-first strategy
// Serve from cache if available, else fetch and cache
self.addEventListener('fetch', event => {
  // Skip non-GET and chrome-extension requests
  if (event.request.method !== 'GET') return;
  if (event.request.url.startsWith('chrome-extension')) return;

  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) {
        // Serve from cache — also update in background
        // for model.onnx and labels.json (large files, fetch only once)
        return cached;
      }

      // Not cached — fetch from network
      return fetch(event.request)
        .then(response => {
          // Only cache successful responses
          if (!response || !response.ok) return response;

          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, clone);
          });
          return response;
        })
        .catch(() => {
          // Network failed — return index.html for navigation requests
          if (event.request.destination === 'document') {
            return caches.match('/Gesture_Car/index.html');
          }
        });
    })
  );
});