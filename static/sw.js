// Service worker for the hosted Matatiele offline page (self-hosted or local deployments, where /app/static/ is a normal
// page address). It keeps the page and the last valid status so they reopen without a connection.
// Safety: a response is stored only if it really is this page or a valid status file, so a hosting platform's own page,
// an error page or a "waking up" screen can never replace the saved copy. The previous copy stays until a valid one arrives.
var CACHE = 'matatiele-offline-v4';
var PAGE = ['offline.html', 'manifest.webmanifest', 'icon.svg'];

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) { return cache.addAll(PAGE); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function savedStatus(networkResponse) {
  // The last valid status, marked so the page says it is saved information, not live data. With nothing saved, the
  // server's own reply (or a network error when offline) is passed on, so the page can tell the two situations apart.
  return caches.match('status.json').then(function (saved) {
    if (!saved) return networkResponse || Response.error();
    return saved.blob().then(function (body) {
      return new Response(body, {headers: {'Content-Type': 'application/json', 'X-Offline-Copy': '1'}});
    });
  });
}

self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith('/status.json')) {
    // Network first; store only a valid status; otherwise answer with the last saved one.
    event.respondWith(fetch(event.request).then(function (response) {
      return response.clone().json().then(function (data) {
        if (!response.ok || !data || typeof data.generated_utc !== 'string') return savedStatus(response);
        var copy = response.clone();
        return caches.open(CACHE).then(function (cache) { return cache.put('status.json', copy); }).then(function () { return response; });
      }, function () { return savedStatus(response); });
    }, function () { return savedStatus(); }));
    return;
  }
  // The page: saved copy first (opens instantly and offline); refreshed in the background only with the real page.
  event.respondWith(caches.match(event.request).then(function (saved) {
    var network = fetch(event.request).then(function (response) {
      if (!response.ok) return saved || response;
      return response.clone().text().then(function (text) {
        var ours = url.pathname.endsWith('.html') ? text.indexOf('data-matatiele-offline') !== -1 : true;
        if (ours) { var copy = response.clone(); caches.open(CACHE).then(function (cache) { cache.put(event.request, copy); }); }
        return ours ? response : (saved || response);
      });
    }).catch(function () { return saved; });
    return saved || network;
  }));
});
