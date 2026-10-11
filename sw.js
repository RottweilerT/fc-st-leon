// Mode hors ligne : la page et ses ressources sont gardées sur l'appareil.
// La page est toujours redemandée au réseau d'abord (pour avoir la dernière version),
// et la copie locale ne sert que sans connexion. Les données Firebase ne passent pas par ici.
const CACHE = 'fcsl-v5';
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
    e.respondWith(fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req.mode === 'navigate' ? './index.html' : req, copy)); }
      return res;
    }).catch(() => req.mode === 'navigate' ? caches.match('./index.html').then(r => r || caches.match('./')) : caches.match(req)));
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
