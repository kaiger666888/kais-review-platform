// Service Worker for Kai's Review Platform PWA
// Caches Shot Card data for offline review

const CACHE_NAME = 'shot-cards-v1';
const DATA_CACHE = 'shot-card-data';
const MAX_CACHED_CARDS = 20;

// Install: pre-cache the mobile page shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(['/mobile']);
    })
  );
  self.skipWaiting();
});

// Activate: claim clients and clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME && name !== DATA_CACHE)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: strategy based on request type
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Mobile cards API: network-first with cache fallback
  if (url.pathname.startsWith('/api/v1/mobile/cards')) {
    event.respondWith(networkFirstWithCache(event.request));
    return;
  }

  // Mobile page navigation: cache-first
  if (url.pathname === '/mobile') {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  // All other requests: pass through (no caching)
  return;
});

/**
 * Network-first strategy for Shot Card API responses.
 * On success, cache the response and prune old entries.
 * On failure, serve from cache if available.
 */
async function networkFirstWithCache(request) {
  try {
    const response = await fetch(request);

    if (response.ok) {
      // Clone the response before consuming it
      const responseClone = response.clone();

      // Cache the full API response
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, responseClone);

      // Also extract and cache individual cards for offline access
      try {
        const data = await response.clone().json();
        if (data && data.data && data.data.items) {
          await cacheCardItems(data.data.items);
        }
      } catch (e) {
        // JSON parsing failed for non-list responses, that is fine
      }
    }

    return response;
  } catch (error) {
    // Network failed, try cache
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    // Try to serve from card data cache
    const cardId = extractCardId(request.url);
    if (cardId) {
      const dataCache = await caches.open(DATA_CACHE);
      const cardResponse = await dataCache.match('card-' + cardId);
      if (cardResponse) {
        // Wrap in API response format
        const cardData = await cardResponse.json();
        return new Response(
          JSON.stringify({ status: 'ok', data: cardData }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      }
    }

    return new Response(
      JSON.stringify({ status: 'error', message: 'Offline - no cached data' }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }
}

/**
 * Cache-first strategy for the mobile page shell.
 */
async function cacheFirst(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    // Update cache in background (stale-while-revalidate)
    fetch(request).then((response) => {
      if (response.ok) {
        caches.open(CACHE_NAME).then((cache) => cache.put(request, response));
      }
    }).catch(() => {});
    return cachedResponse;
  }

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Cache individual card items and enforce LRU limit.
 */
async function cacheCardItems(items) {
  if (!items || items.length === 0) return;

  const dataCache = await caches.open(DATA_CACHE);

  for (const item of items) {
    const key = 'card-' + item.id;
    await dataCache.put(key, new Response(JSON.stringify(item)));
  }

  // Prune: keep only MAX_CACHED_CARDS most recent
  const keys = await dataCache.keys();
  const cardKeys = keys
    .filter((k) => k.url.includes('card-') || k.url.startsWith('card-'))
    .map((k) => {
      const urlStr = typeof k === 'string' ? k : k.url;
      return urlStr;
    });

  // Extract numeric IDs and sort by card ID (higher = more recent)
  const sortedKeys = cardKeys.sort((a, b) => {
    const idA = parseInt(a.replace(/^.*card-/, ''), 10) || 0;
    const idB = parseInt(b.replace(/^.*card-/, ''), 10) || 0;
    return idB - idA; // newest first
  });

  // Delete oldest entries beyond limit
  if (sortedKeys.length > MAX_CACHED_CARDS) {
    const toDelete = sortedKeys.slice(MAX_CACHED_CARDS);
    for (const key of toDelete) {
      await dataCache.delete(key);
    }
  }
}

/**
 * Extract card ID from a URL like /api/v1/mobile/cards/123/audio
 */
function extractCardId(url) {
  const match = url.match(/\/api\/v1\/mobile\/cards\/(\d+)/);
  return match ? match[1] : null;
}
