// docs/sw.js
// Service worker — caches all app assets permanently
// After first load with internet, app works completely offline

const CACHE = 'gesture-car-v1';

// Everything to cache on install
const ASSETS = [
  '/Gesture_Car/',
  '/Gesture_Car/index.html',
  '/Gesture_Car/model.onnx',
  '/Gesture_Car/labels.json',
  // MediaPipe from CDN
  'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js',
  'https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js',
  'https://cdn.jsdelivr.net/npm/onnxruntime-web/dist/ort.min.js',
  // MediaPipe WASM files
  'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands_solution_packed_assets_loader.js',
  'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands_solution_simd_wasm_bin.js',
];

// Install — cache all assets
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => {
      console.log('[SW] Caching all assets');
      // Cache what we can — skip failures (CDN assets)
      return Promise.allSettled(
        ASSETS.map(url => cache.add(url).catch(err =>
          console.warn('[SW] Failed to cache:', url, err)
        ))
      );
    }).then(() => self.skipWaiting())
  );
});

// Activate — clean old caches
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys
        .filter(k => k !== CACHE)
        .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch — serve from cache, fall back to network
self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      // Not in cache — fetch from network and cache for next time
      return fetch(e.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE).then(cache => cache.put(e.request, clone));
        }
        return response;
      }).catch(() => {
        // Completely offline and not cached — return offline page
        if (e.request.destination === 'document') {
          return caches.match('/Gesture_Car/index.html');
        }
      });
    })
  );
});