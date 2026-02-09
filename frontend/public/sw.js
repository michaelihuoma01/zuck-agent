// ZURK Service Worker — hand-written, no Workbox dependency
const SHELL_CACHE = 'zurk-shell-v1'
const ASSETS_CACHE = 'zurk-assets-v1'

// App shell files to pre-cache on install
const SHELL_FILES = [
  '/',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
]

// --- Install: pre-cache app shell ---
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_FILES))
  )
  self.skipWaiting()
})

// --- Activate: clean old caches ---
self.addEventListener('activate', (event) => {
  const keep = new Set([SHELL_CACHE, ASSETS_CACHE])
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names.filter((n) => !keep.has(n)).map((n) => caches.delete(n))
      )
    )
  )
  self.clients.claim()
})

// --- Fetch strategies ---
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Network-only: API and WebSocket — data must always be fresh
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) {
    return // Let the browser handle it normally (network-only)
  }

  // Cache-first: Vite hashed static assets (JS, CSS)
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.open(ASSETS_CACHE).then((cache) =>
        cache.match(request).then(
          (cached) =>
            cached ||
            fetch(request).then((response) => {
              cache.put(request, response.clone())
              return response
            })
        )
      )
    )
    return
  }

  // Network-first with cache fallback: navigation and other requests
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone()
          caches.open(SHELL_CACHE).then((cache) => cache.put(request, clone))
          return response
        })
        .catch(() => caches.match('/') || caches.match(request))
    )
    return
  }

  // Default: network-first for everything else (icons, fonts, etc.)
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  )
})

// --- Notify clients of online/offline changes ---
self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') {
    self.skipWaiting()
  }
})
