/* Service Worker for Tide predictions PWA.
 *
 * Three cache strategies:
 *   1. App shell        → cache-first, pre-cached on install
 *   2. Map tiles        → cache-first with LRU-style cap
 *   3. Pages & data     → network-first, fall back to cache, fall back to offline.html
 *
 * Bump CACHE_VERSION whenever the app shell list changes; old caches are
 * deleted on activate.
 */

const CACHE_VERSION   = 'v3';
const SHELL_CACHE     = `tides-shell-${CACHE_VERSION}`;
const PAGES_CACHE     = `tides-pages-${CACHE_VERSION}`;
const TILES_CACHE     = `tides-tiles-${CACHE_VERSION}`;
const TILES_MAX       = 1500;  // ~ a full session of pans and zooms
const TRIM_EVERY      = 50;    // run LRU trim once every N puts, not per-put
let   tilePutCounter  = 0;

const SHELL_ASSETS = [
  '/',
  '/static/css/styles.css',
  '/static/css/styles_suchbox.css',
  '/static/js/suche.js',
  '/static/js/pwa.js',
  '/static/manifest.webmanifest',
  '/static/favicon.ico',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-512-maskable.png',
  '/static/og-image.png',
  '/static/offline.html',
];

// External CDN assets (Leaflet etc.) are not pre-cached because they
// require opaque (no-cors) fetches; they get cached on first request.

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      // addAll fails atomically — use individual addRequest fallbacks so
      // one missing asset doesn't break the whole install.
      Promise.all(SHELL_ASSETS.map((url) =>
        cache.add(url).catch((err) => console.warn('[SW] pre-cache skipped:', url, err))
      ))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('tides-') && !k.endsWith(CACHE_VERSION))
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ---------- Helpers ----------

function isTileRequest(url) {
  return (
    url.hostname.endsWith('.tile.openstreetmap.org') ||
    url.hostname.endsWith('.basemaps.cartocdn.com') ||
    url.hostname.includes('gibs.earthdata.nasa.gov') ||
    url.hostname.includes('tile.rainviewer.com') ||
    url.hostname.includes('opendata.dwd.de') ||
    (url.pathname.startsWith('/static/') &&
      (url.pathname.endsWith('.png') ||
       url.pathname.endsWith('.jpg') ||
       url.pathname.endsWith('.webp')))
  );
}

function isAppShellAsset(url) {
  if (url.origin !== self.location.origin) return false;
  // Data files (e.g. leaflet_markers_data.json) update with every harmonics
  // release; stale-while-revalidate would show users yesterday's station list
  // and break search → marker lookups for fresh entries.
  if (url.pathname.endsWith('.json')) return false;
  return (
    url.pathname.startsWith('/static/css/') ||
    url.pathname.startsWith('/static/js/')  ||
    url.pathname === '/static/manifest.webmanifest'
  );
}

function isPredictionPage(url) {
  return url.origin === self.location.origin && (
    url.pathname === '/' ||
    url.pathname.startsWith('/prediction/') ||
    url.pathname.startsWith('/learn/') ||
    url.pathname.startsWith('/stations/') ||
    url.pathname.startsWith('/static/predictions/')
  );
}

// LRU-trim a cache: when it grows past `max`, drop the oldest entries.
// Since Cache API doesn't expose insertion order natively, we use keys()
// which returns insertion order on all major browsers.
async function trimCache(cacheName, max) {
  const cache = await caches.open(cacheName);
  const keys  = await cache.keys();
  if (keys.length > max) {
    const drop = keys.length - max;
    for (let i = 0; i < drop; i++) await cache.delete(keys[i]);
  }
}

// ---------- Fetch handler ----------

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // POST/PUT to our app endpoints (update_*, delete_*) — never intercept
  if (url.origin === self.location.origin && (
      url.pathname.startsWith('/update_') ||
      url.pathname.startsWith('/delete_') ||
      url.pathname.startsWith('/generate/'))) {
    return;
  }

  // Map tiles: pure cache-first. Tiles are immutable for our purposes
  // (OSM/Carto/etc. update them rarely and we don't care about sub-yearly
  // freshness). Only hit the network on cache miss. LRU-trim batched
  // every TRIM_EVERY puts to avoid quadratic main-thread work during pans.
  if (isTileRequest(url)) {
    event.respondWith(
      caches.open(TILES_CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        if (cached) return cached;
        try {
          const resp = await fetch(req);
          if (resp && (resp.ok || resp.type === 'opaque')) {
            await cache.put(req, resp.clone());
            tilePutCounter++;
            if (tilePutCounter % TRIM_EVERY === 0) {
              trimCache(TILES_CACHE, TILES_MAX);  // fire-and-forget
            }
          }
          return resp;
        } catch (_) {
          return new Response('', { status: 504, statusText: 'Tile offline' });
        }
      })
    );
    return;
  }

  // App shell CSS/JS: stale-while-revalidate
  if (isAppShellAsset(url)) {
    event.respondWith(
      caches.open(SHELL_CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        const networkFetch = fetch(req).then((resp) => {
          if (resp && resp.ok) cache.put(req, resp.clone());
          return resp;
        }).catch(() => cached);
        return cached || networkFetch;
      })
    );
    return;
  }

  // Pages & SVG predictions: network-first, cache-fallback, offline-fallback
  if (isPredictionPage(url)) {
    event.respondWith(
      fetch(req).then((resp) => {
        if (resp && resp.ok) {
          const copy = resp.clone();
          caches.open(PAGES_CACHE).then((cache) => cache.put(req, copy));
        }
        return resp;
      }).catch(async () => {
        const cached = await caches.match(req);
        if (cached) return cached;
        // Last resort: offline page (only for navigations)
        if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
          return caches.match('/static/offline.html');
        }
        return new Response('', { status: 503, statusText: 'Offline' });
      })
    );
    return;
  }

  // Default: try network, fall back to cache if we happen to have it
  event.respondWith(
    fetch(req).catch(() => caches.match(req))
  );
});
