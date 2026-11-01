// Service worker for the Matatiele offline page: keeps the page and the last status so they open without a connection.
// The status is fetched from the network first (fresh information when there is signal) and falls back to the saved copy.
var CACHE = 'matatiele-offline-v2';
var PAGE = ['offline.html', 'manifest.webmanifest', 'icon.svg'];

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) { return cache.addAll(PAGE); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith('/status.json')) {
    // Network first: save each fresh status; offline, answer with the last saved one.
    event.respondWith(fetch(event.request).then(function (response) {
      var copy = response.clone();
      caches.open(CACHE).then(function (cache) { cache.put('status.json', copy); });
      return response;
    }).catch(function () {
      // Mark the saved copy, so the page says it is showing saved information, not live data.
      return caches.match('status.json').then(function (saved) {
        return saved ? saved.blob().then(function (body) {
          return new Response(body, {headers: {'Content-Type': 'application/json', 'X-Offline-Copy': '1'}});
        }) : Response.error();
      });
    }));
    return;
  }
  // The page itself: saved copy first, so it opens instantly and offline; refreshed in the background.
  event.respondWith(caches.match(event.request).then(function (saved) {
    var network = fetch(event.request).then(function (response) {
      if (response.ok) { var copy = response.clone(); caches.open(CACHE).then(function (cache) { cache.put(event.request, copy); }); }
      return response;
    }).catch(function () { return saved; });
    return saved || network;
  }));
});
