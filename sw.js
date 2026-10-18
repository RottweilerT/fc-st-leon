// Mode hors ligne : la page et ses ressources sont gardées sur l'appareil.
// La page est redemandée au réseau d'abord (pour avoir la dernière version) ; si le réseau ne répond pas
// en 2,5 s (4G faible) ou s'il n'y a pas de connexion, la copie gardée sur l'appareil s'ouvre tout de suite. Les données Firebase ne passent pas par ici.
const CACHE = 'fcsl-v7';
const CORE = ['./', './index.html', './manifest.webmanifest', './icon-192-v5.png', './icon-512-v5.png', './crest-96-v5.png', './crest-512-v5.png', './icon-round-192-v5.png', './icon-round-512-v5.png', './icon-maskable-512-v5.png', './crest-mono-256-v5.png', './favicon-32-v5.png'];
const EXTERNAL = ['fonts.googleapis.com', 'fonts.gstatic.com'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE.map(u => new Request(u, { cache: 'reload' })))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (req.mode === 'navigate' || url.pathname.endsWith('.webmanifest')) {
    // network first, but never wait more than 2.5 s: on weak mobile data the saved copy opens at once
    // and the fresh version is saved in the background for the next opening
    const key = req.mode === 'navigate' ? './index.html' : req;
    const net = fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(key, copy)); }
      return res;
    });
    e.waitUntil(net.then(() => {}, () => {}));
    e.respondWith((async () => {
      const cached = (await caches.match(key)) || (req.mode === 'navigate' ? await caches.match('./') : null);
      if (!cached) return net;
      const late = new Promise(r => setTimeout(() => r(null), 2500));
      return (await Promise.race([net.catch(() => null), late])) || cached;
    })());
    return;
  }
  const static_ = url.origin === location.origin || EXTERNAL.includes(url.hostname)
    || (url.hostname === 'www.gstatic.com' && url.pathname.startsWith('/firebasejs/'));
  if (!static_) return;
  e.respondWith(caches.open(CACHE).then(async c => {
    const cached = await c.match(req);
    const fresh = fetch(req).then(res => {
      if (res.ok || res.type === 'opaque') c.put(req, res.clone());
      return res;
    }).catch(() => cached);
    return cached || fresh;
  }));
});

// Notifications (envoyées par la GitHub Action « Notifications » via Firebase Cloud Messaging).
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { data: { body: e.data ? e.data.text() : '' } }; }
  const x = Object.assign({}, d.notification || {}, d.data || {});
  e.waitUntil(self.registration.showNotification(x.title || 'FC St Léon', {
    body: x.body || '', icon: 'icon-round-192-v5.png', badge: 'icon-round-192-v5.png', tag: x.tag || undefined, renotify: !!x.tag,
    data: { url: x.url || './' }
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || './', self.registration.scope).href;
  e.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(ws => {
    for (const w of ws) if (w.url.startsWith(self.registration.scope)) { w.focus(); return w.navigate ? w.navigate(url).catch(() => {}) : null; }
    return clients.openWindow(url);
  }));
});
