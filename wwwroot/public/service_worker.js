// FuXi service worker: shows the push notifications, opens the Flashcard page on a click, and keeps the
// app's fonts offline (cached on install, answered cache first, a missed font stored when it is loaded).
// It is plain JavaScript, served unbundled at /service_worker.js, so it cannot import app code.

const NOTIFICATION_ICON = '/fuxi_192.png';
// One tag for every push, so the newest notification replaces the older one; renotify still alerts.
const NOTIFICATION_TAG = 'fuxi-due-words';
const FLASHCARD_PATH = '/flashcard';
const WORD_IDS_QUERY = 'wordIds';
const WINDOW_CLIENT_TYPE = 'window';
// The same message type is read by src/services/service_worker_message_service.ts.
const NAVIGATE_MESSAGE_TYPE = 'fuxi-navigate';

// The fonts of the build are cached on install and answered from that cache, so they work offline.
// The build (fontPrecache in src/service_worker_font_list.ts) writes the font files of that build and a cache
// name made from their list after the two markers below; the markers stay, so every build fills them again.
// The dev server keeps the values below: the list is empty, so no font is cached and fonts are left to the browser.
const FONT_CACHE = /* fuxi:font-cache */ 'fuxi-fonts-dev';
const FONT_FILES = /* fuxi:font-files */ [];
const FONT_CACHE_PREFIX = 'fuxi-fonts-';
const FONT_EXTENSION = '.woff2';
const GET_METHOD = 'GET';
// Without a font list (the dev server) the worker caches no font.
const HAS_FONT_LIST = FONT_FILES.length > 0;
// The install waits this long for the precache at most, well under the 10 s that push_service.ts waits
// for the worker to be ready. Fonts not stored by then are stored by the fetch rule when they are loaded.
const FONT_PRECACHE_LIMIT_MS = 4_000;
// Static Routing: only the app's font requests reach this worker; every other request goes to the network.
const FONT_ROUTE_CONDITION = { urlPattern: `/*${FONT_EXTENSION}`, requestMethod: GET_METHOD };
const ROUTES = [
  { condition: FONT_ROUTE_CONDITION, source: 'fetch-event' },
  { condition: { not: FONT_ROUTE_CONDITION }, source: 'network' },
];

/**
 * Caches one font, unless it is cached already. A failure leaves only this font to the fetch rule,
 * which stores it when it is first loaded; the other fonts are not affected.
 */
const precacheFont = async (cache, url) => {
  try {
    if (await cache.match(url)) {
      return;
    }

    const response = await self.fetch(url);
    if (response.ok) {
      await cache.put(url, response);
    }
  } catch {
    // Push still works; the fetch rule stores this font when it is first loaded.
  }
};

/**
 * Caches the fonts of the build one by one, so each stored font stays stored even when another fails
 * or the install stops waiting at its time limit. A failure never fails the install.
 */
const precacheFonts = async () => {
  let cache;
  try {
    cache = await self.caches.open(FONT_CACHE);
  } catch {
    return;
  }

  await Promise.all(FONT_FILES.map((url) => precacheFont(cache, url)));
};

/** Waits for the precache, or for its time limit when that comes first; the timer is cleared either way. */
const precacheFontsInTime = async () => {
  if (!HAS_FONT_LIST) {
    return;
  }

  let timer;
  const limit = new Promise((resolve) => {
    timer = setTimeout(resolve, FONT_PRECACHE_LIMIT_MS);
  });

  try {
    await Promise.race([precacheFonts(), limit]);
  } finally {
    clearTimeout(timer);
  }
};

/** Adds the static routes where the browser has them. An unsupported rule never fails the install. */
const addFontRoutes = async (event) => {
  if (typeof event.addRoutes !== 'function') {
    return;
  }

  try {
    await event.addRoutes(ROUTES);
  } catch {
    // Without routes every request still reaches the fetch handler, which leaves non-fonts alone.
  }
};

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(Promise.all([precacheFontsInTime(), addFontRoutes(event)]));
});

/**
 * Deletes the font caches of older builds except the newest of them: a tab opened on the build before
 * may still load its own font files, which this build's server no longer has. Other caches are left alone.
 */
const deleteOldFontCaches = async () => {
  const names = await self.caches.keys();
  const olderNames = names.filter((name) => name.startsWith(FONT_CACHE_PREFIX) && name !== FONT_CACHE);
  // caches.keys() lists the caches in the order they were made, so the last one is the build before.
  const staleNames = olderNames.slice(0, -1);

  await Promise.all(staleNames.map((name) => self.caches.delete(name)));
};

self.addEventListener('activate', (event) => {
  event.waitUntil(Promise.all([self.clients.claim(), deleteOldFontCaches()]));
});

const isOwnFont = (request) => {
  const url = new URL(request.url);

  return HAS_FONT_LIST && request.method === GET_METHOD && url.origin === self.location.origin && url.pathname.endsWith(FONT_EXTENSION);
};

const NOTHING_TO_STORE = Promise.resolve();

/** Stores a downloaded font in the cache of this build. A failure is ignored: the font was already answered. */
const storeFont = async (cache, request, response) => {
  try {
    await cache.put(request, response);
  } catch {
    // The font is stored on a later load.
  }
};

/** The font cache of this build, or null when it cannot be opened. */
const openFontCache = async () => {
  try {
    return await self.caches.open(FONT_CACHE);
  } catch {
    return null;
  }
};

/**
 * A cached copy of the request, or undefined when there is none or the caches cannot be read.
 * The cache of this build comes first; a font of the build before (an open old tab) is found in its kept cache.
 */
const matchFont = async (cache, request) => {
  try {
    const cached = cache === null ? undefined : await cache.match(request);

    return cached ?? (await self.caches.match(request));
  } catch {
    return undefined;
  }
};

/**
 * Answers a font from the cache of this build. A missed font (also one a failed precache left out) is
 * downloaded and answered at once, and its storing is handed back as a separate promise.
 */
const answerFont = async (request) => {
  const cache = await openFontCache();
  const cached = await matchFont(cache, request);

  if (cached) {
    return { response: cached, stored: NOTHING_TO_STORE };
  }

  const response = await self.fetch(request);
  const stored = response.ok && cache !== null ? storeFont(cache, request, response.clone()) : NOTHING_TO_STORE;

  return { response, stored };
};

self.addEventListener('fetch', (event) => {
  if (!isOwnFont(event.request)) {
    return;
  }

  const answer = answerFont(event.request);
  event.respondWith(answer.then(({ response }) => response));
  // Called at once, while the event is still dispatching, so the store outlives the response.
  // A failed download fails the response only; the background work then has nothing left to do.
  event.waitUntil(answer.then(({ stored }) => stored, () => undefined));
});
const isFilledText = (value) => typeof value === 'string' && value !== '';

/** The payload {title, wordIds} of a push, or null when it is missing or not valid. */
const readPayload = (data) => {
  if (!data) {
    return null;
  }

  try {
    const payload = data.json();

    return payload && isFilledText(payload.title) && isFilledText(payload.wordIds) ? payload : null;
  } catch {
    return null;
  }
};

const showWordsNotification = async (data) => {
  const payload = readPayload(data);

  if (payload === null) {
    return;
  }

  await self.registration.showNotification(payload.title, {
    data: { wordIds: payload.wordIds },
    icon: NOTIFICATION_ICON,
    tag: NOTIFICATION_TAG,
    renotify: true,
  });
};

self.addEventListener('push', (event) => {
  event.waitUntil(showWordsNotification(event.data));
});

const flashcardUrl = (wordIds) =>
  isFilledText(wordIds) ? `${FLASHCARD_PATH}?${WORD_IDS_QUERY}=${encodeURIComponent(wordIds)}` : FLASHCARD_PATH;

/**
 * Moves an open tab to the url. navigate() fails on a tab that this worker does not control,
 * so the tab is then asked by a message to move itself.
 */
const moveTab = async (tab, url) => {
  try {
    if (typeof tab.navigate === 'function') {
      await tab.navigate(url);
      return;
    }
  } catch {
    // Falls back to the message below.
  }

  tab.postMessage({ type: NAVIGATE_MESSAGE_TYPE, url });
};

/** Focuses an open FuXi tab and moves it to the url. Only when none is open, a new window opens. */
const openFlashcard = async (url) => {
  const tabs = await self.clients.matchAll({ type: WINDOW_CLIENT_TYPE, includeUncontrolled: true });
  const tab = tabs[0];

  if (tab === undefined) {
    await self.clients.openWindow(url);
    return;
  }

  await tab.focus();
  await moveTab(tab, url);
};

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(openFlashcard(flashcardUrl(event.notification.data?.wordIds)));
});
