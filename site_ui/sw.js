const CACHE_NAME = 'cbb-stats-v8';
const BASE_URL = '/College-Basketball-Stats';
const ASSETS = [
  BASE_URL + '/',
  BASE_URL + '/styles.css',
  BASE_URL + '/helpers.js',
  BASE_URL + '/common.js',
  BASE_URL + '/manifest.json',
  'https://www.gstatic.com/firebasejs/9.6.1/firebase-app-compat.js',
  'https://www.gstatic.com/firebasejs/9.6.1/firebase-auth-compat.js',
  'https://www.gstatic.com/firebasejs/9.6.1/firebase-firestore-compat.js'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(ASSETS))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Only handle GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  let url;
  try {
    url = new URL(event.request.url);
  } catch (e) {
    return;
  }

  // Never intercept cross-origin API/Firestore/Auth requests (critical for iOS Safari WebKit streaming & CORS)
  if (url.origin !== self.location.origin && !url.hostname.endsWith('gstatic.com')) {
    return;
  }

  // Network-first strategy for HTML navigation requests so page updates and hashes work reliably on iOS Safari
  if (event.request.mode === 'navigate' || event.request.destination === 'document') {
    event.respondWith(
      fetch(event.request)
        .catch(() => caches.match(event.request, { ignoreSearch: true }))
    );
    return;
  }

  // Network-first strategy for local scripts/styles so updates take effect immediately
  if (url.pathname.endsWith('/helpers.js') || url.pathname.endsWith('/styles.css') || url.pathname.includes('/common')) {
    event.respondWith(
      fetch(event.request, { cache: 'no-cache' })
        .then((response) => {
          if (response && response.ok) {
            const resClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, resClone));
          }
          return response;
        })
        .catch(() => caches.match(event.request, { ignoreSearch: true }))
    );
    return;
  }

  // Cache-first strategy for other static assets
  event.respondWith(
    caches.match(event.request, { ignoreSearch: true })
      .then((response) => {
        return response || fetch(event.request);
      })
  );
});