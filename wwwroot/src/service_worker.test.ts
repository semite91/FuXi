// Sections G and H: the push and notification click handling of public/service_worker.js.
// The file is plain JavaScript that Vite serves unbundled, so it runs here with a fake self.
import { expect, test, vi } from 'vitest';
import serviceWorkerCode from '../public/service_worker.js?raw';
import { fillFontList } from './service_worker_font_list';
import { deferred } from './test/api_mock';

const ICON = '/fuxi_192.png';
const NOTIFICATION_TAG = 'fuxi-due-words';
const TITLE = 'apple, river';
const WORD_IDS = 'id-1,id-2';
const FLASHCARD_URL = '/flashcard?wordIds=id-1%2Cid-2';

type Listener = (event: unknown) => void;

const APP_ORIGIN = 'https://fuxi.example';
const FONT_PATH = '/assets/nunito-latin-500-normal-EugFkASW.woff2';
const OTHER_FONT_PATH = '/assets/baloo-2-latin-800-normal-BbF3Etk1.woff2';
const FONT_URL = `${APP_ORIGIN}${FONT_PATH}`;
const BUILD_FONT_CACHE = 'fuxi-fonts-1a2b3c4d';

interface FakeResponse {
  ok: boolean;
  clone: () => FakeResponse;
}

const fakeResponse = (ok = true): FakeResponse => {
  const response: FakeResponse = { ok, clone: () => response };

  return response;
};

interface FakeWindow {
  focus: ReturnType<typeof vi.fn>;
  navigate?: ReturnType<typeof vi.fn>;
  postMessage: ReturnType<typeof vi.fn>;
}

const fakeWindow = (canNavigate = true): FakeWindow => {
  const window: FakeWindow = {
    focus: vi.fn(async () => window),
    postMessage: vi.fn(),
  };

  if (canNavigate) {
    window.navigate = vi.fn(async () => window);
  }

  return window;
};

interface FontBuild {
  cacheName: string;
  files: string[];
}

/** The worker as the build writes it: with the font list and cache name of that build. */
const builtCode = (build?: FontBuild) =>
  build === undefined ? serviceWorkerCode : fillFontList(serviceWorkerCode, build.cacheName, build.files);

/** Runs the service worker file with a fake self and returns its listeners and fakes. */
const loadServiceWorker = (openWindows: FakeWindow[] = [], cacheNames: string[] = [], build?: FontBuild) => {
  const listeners = new Map<string, Listener>();
  const cache = {
    match: vi.fn(async (_request: unknown): Promise<unknown> => undefined),
    put: vi.fn(async (_request: unknown, _response: unknown): Promise<undefined> => undefined),
    addAll: vi.fn(async (_urls: string[]): Promise<undefined> => undefined),
  };
  const self = {
    addEventListener: (type: string, listener: Listener) => listeners.set(type, listener),
    skipWaiting: vi.fn(),
    location: { origin: APP_ORIGIN },
    fetch: vi.fn(async (_request: unknown): Promise<unknown> => fakeResponse()),
    caches: {
      open: vi.fn(async (_name: string) => cache),
      keys: vi.fn(async () => cacheNames),
      delete: vi.fn(async (_name: string) => true),
    },
    registration: { showNotification: vi.fn(async () => undefined) },
    clients: {
      claim: vi.fn(async () => undefined),
      matchAll: vi.fn(async () => openWindows),
      openWindow: vi.fn(async () => null),
    },
  };
  new Function('self', builtCode(build))(self);

  /** Dispatches an event and returns the promises it gave to waitUntil. */
  const dispatch = (type: string, event: object) => {
    const kept: Promise<unknown>[] = [];
    const waitUntil = vi.fn((promise: Promise<unknown>) => kept.push(promise));
    listeners.get(type)?.({ ...event, waitUntil });

    return { kept, waitUntil };
  };

  return { self, cache, dispatch };
};
const pushData = (payload: unknown) => ({ json: () => payload });

const invalidJson = {
  json: () => {
    throw new SyntaxError('Unexpected token');
  },
};

const clickEvent = (wordIds = WORD_IDS) => {
  const notification = { data: { wordIds }, close: vi.fn() };

  return { notification };
};

test('G1 a push shows a notification with the payload title', async () => {
  const { self, dispatch } = loadServiceWorker();

  const { kept } = dispatch('push', { data: pushData({ title: TITLE, wordIds: WORD_IDS }) });
  await Promise.all(kept);

  expect(self.registration.showNotification).toHaveBeenCalledTimes(1);
  expect(self.registration.showNotification).toHaveBeenCalledWith(TITLE, expect.anything());
});

test('G2 the notification data holds the wordIds and its icon is the FuXi icon', async () => {
  const { self, dispatch } = loadServiceWorker();

  const { kept } = dispatch('push', { data: pushData({ title: TITLE, wordIds: WORD_IDS }) });
  await Promise.all(kept);

  expect(self.registration.showNotification).toHaveBeenCalledWith(
    TITLE,
    expect.objectContaining({ data: { wordIds: WORD_IDS }, icon: ICON }),
  );
});

test('G5 Given a push, when the notification is shown, then it has the FuXi tag and renotify true', async () => {
  const { self, dispatch } = loadServiceWorker();

  const { kept } = dispatch('push', { data: pushData({ title: TITLE, wordIds: WORD_IDS }) });
  await Promise.all(kept);

  expect(self.registration.showNotification).toHaveBeenCalledWith(
    TITLE,
    expect.objectContaining({ tag: NOTIFICATION_TAG, renotify: true }),
  );
});

test('G3 the push work is kept inside event.waitUntil', async () => {
  const { self, dispatch } = loadServiceWorker();
  const shown = deferred<undefined>();
  self.registration.showNotification.mockImplementation(() => shown.promise);

  const { kept, waitUntil } = dispatch('push', { data: pushData({ title: TITLE, wordIds: WORD_IDS }) });
  let isKeptDone = false;
  void kept[0].then(() => {
    isKeptDone = true;
  });
  await Promise.resolve();
  await Promise.resolve();

  expect(waitUntil).toHaveBeenCalledTimes(1);
  expect(isKeptDone).toBe(false);
  shown.resolve(undefined);
  await kept[0];
  expect(isKeptDone).toBe(true);
});

test.each([
  ['no data', null],
  ['invalid JSON', invalidJson],
  ['no title', pushData({ wordIds: WORD_IDS })],
  ['no wordIds', pushData({ title: TITLE })],
  ['a non-object payload', pushData('apple')],
  ['a null payload', pushData(null)],
])('G4 a push with %s shows nothing and throws nothing', async (_, data) => {
  const { self, dispatch } = loadServiceWorker();

  const { kept } = dispatch('push', { data });

  await expect(Promise.all(kept)).resolves.toBeDefined();
  expect(self.registration.showNotification).not.toHaveBeenCalled();
});

test('H1 a notification click closes the notification', async () => {
  const { dispatch } = loadServiceWorker();
  const event = clickEvent();

  const { kept } = dispatch('notificationclick', event);
  await Promise.all(kept);

  expect(event.notification.close).toHaveBeenCalledTimes(1);
});

test('H2 with no open FuXi tab a click opens a new window at /flashcard?wordIds', async () => {
  const { self, dispatch } = loadServiceWorker();

  const { kept, waitUntil } = dispatch('notificationclick', clickEvent());
  await Promise.all(kept);

  expect(waitUntil).toHaveBeenCalledTimes(1);
  expect(self.clients.matchAll).toHaveBeenCalledWith({ type: 'window', includeUncontrolled: true });
  expect(self.clients.openWindow).toHaveBeenCalledWith(FLASHCARD_URL);
});

test('H3 with an open FuXi tab a click focuses it, moves it to /flashcard?wordIds and opens no window', async () => {
  const tab = fakeWindow();
  const { self, dispatch } = loadServiceWorker([tab]);

  const { kept } = dispatch('notificationclick', clickEvent());
  await Promise.all(kept);

  expect(tab.focus).toHaveBeenCalledTimes(1);
  expect(tab.navigate).toHaveBeenCalledWith(FLASHCARD_URL);
  expect(self.clients.openWindow).not.toHaveBeenCalled();
});

test.each([
  ['has no navigate', fakeWindow(false)],
  [
    'cannot navigate',
    Object.assign(fakeWindow(), { navigate: vi.fn(async () => Promise.reject(new TypeError('Not controlled'))) }),
  ],
])('H3 a tab that %s is focused and told to move with a message, and no window opens', async (_, tab) => {
  const { self, dispatch } = loadServiceWorker([tab]);

  const { kept } = dispatch('notificationclick', clickEvent());
  await Promise.all(kept);

  expect(tab.focus).toHaveBeenCalledTimes(1);
  expect(tab.postMessage).toHaveBeenCalledWith({ type: 'fuxi-navigate', url: FLASHCARD_URL });
  expect(self.clients.openWindow).not.toHaveBeenCalled();
});

test('H4 the word ids in the address are URL-encoded', async () => {
  const { self, dispatch } = loadServiceWorker();

  const { kept } = dispatch('notificationclick', clickEvent('a b,c&d=e'));
  await Promise.all(kept);

  expect(self.clients.openWindow).toHaveBeenCalledWith(`/flashcard?wordIds=${encodeURIComponent('a b,c&d=e')}`);
});

test('install and activate are kept', async () => {
  const { self, dispatch } = loadServiceWorker();

  dispatch('install', {});
  const { kept } = dispatch('activate', {});
  await Promise.all(kept);

  expect(self.skipWaiting).toHaveBeenCalledTimes(1);
  expect(self.clients.claim).toHaveBeenCalledTimes(1);
});

// Phase 6a B5 and B10: the fonts of the build are cached on install and answered from the cache.
const BUILD: FontBuild = { cacheName: BUILD_FONT_CACHE, files: [FONT_PATH, OTHER_FONT_PATH] };

const fetchEvent = (url: string, method = 'GET') => {
  const respondWith = vi.fn();

  return { request: { url, method }, respondWith };
};

/** Dispatches a fetch and returns the response given to respondWith, or undefined when the worker left it alone. */
const dispatchFetch = async (dispatch: ReturnType<typeof loadServiceWorker>['dispatch'], url: string, method = 'GET') => {
  const event = fetchEvent(url, method);
  const { kept } = dispatch('fetch', event);
  const response = event.respondWith.mock.calls.length === 0 ? undefined : await event.respondWith.mock.calls[0][0];

  return { response, kept };
};

test('6a B5 install caches every font of the build under the cache name of that build', async () => {
  const { self, cache, dispatch } = loadServiceWorker([], [], BUILD);

  const { kept } = dispatch('install', {});
  await Promise.all(kept);

  expect(self.caches.open).toHaveBeenCalledWith(BUILD_FONT_CACHE);
  expect(cache.addAll).toHaveBeenCalledWith([FONT_PATH, OTHER_FONT_PATH]);
  expect(self.skipWaiting).toHaveBeenCalledTimes(1);
});

test('6a B14 the worker of the dev server (no font list) installs without opening a font cache', async () => {
  const { self, dispatch } = loadServiceWorker();

  const { kept } = dispatch('install', {});
  await Promise.all(kept);

  expect(self.caches.open).not.toHaveBeenCalled();
  expect(self.skipWaiting).toHaveBeenCalledTimes(1);
});

test('6a B14 the worker of the dev server leaves font requests to the browser and caches nothing', async () => {
  const { self, cache, dispatch } = loadServiceWorker();

  const event = fetchEvent(FONT_URL);
  const { kept } = dispatch('fetch', event);
  await Promise.all(kept);

  expect(event.respondWith).not.toHaveBeenCalled();
  expect(self.caches.open).not.toHaveBeenCalled();
  expect(cache.put).not.toHaveBeenCalled();
});

// The worker's own limit, read from its code, so the test follows the constant.
const PRECACHE_LIMIT_MS = Number(/const FONT_PRECACHE_LIMIT_MS = ([\d_]+);/.exec(serviceWorkerCode)?.[1].replaceAll('_', ''));
// push_service.ts waits 10 s for the worker to be ready.
const PUSH_READY_TIMEOUT_MS = 10_000;

test('6a B13 the precache time limit is a few seconds, well under the push ready timeout', () => {
  expect(PRECACHE_LIMIT_MS).toBeGreaterThan(0);
  expect(PRECACHE_LIMIT_MS).toBeLessThanOrEqual(PUSH_READY_TIMEOUT_MS / 2);
});

test('6a B13 a precache slower than its limit ends the install at the limit', async () => {
  vi.useFakeTimers();
  const { cache, dispatch } = loadServiceWorker([], [], BUILD);
  cache.addAll.mockImplementation(() => new Promise<undefined>(() => undefined));
  let isInstalled = false;

  const { kept } = dispatch('install', {});
  void Promise.all(kept).then(() => {
    isInstalled = true;
  });
  await vi.advanceTimersByTimeAsync(PRECACHE_LIMIT_MS - 1);
  expect(isInstalled).toBe(false);
  await vi.advanceTimersByTimeAsync(1);

  expect(isInstalled).toBe(true);
  vi.useRealTimers();
});

test('6a B13 a precache that ends in time clears its time limit', async () => {
  vi.useFakeTimers();
  const { dispatch } = loadServiceWorker([], [], BUILD);

  const { kept } = dispatch('install', {});
  await Promise.all(kept);

  expect(vi.getTimerCount()).toBe(0);
  vi.useRealTimers();
});

test('6a B5 a failed font precache does not fail the install, so push keeps working', async () => {
  const { cache, dispatch } = loadServiceWorker([], [], BUILD);
  cache.addAll.mockRejectedValue(new TypeError('Failed to fetch'));

  const { kept } = dispatch('install', {});

  await expect(Promise.all(kept)).resolves.toBeDefined();
});

test('6a B5 activate deletes the older font caches and keeps the current one and other caches', async () => {
  const { self, dispatch } = loadServiceWorker([], ['fuxi-fonts-0f0f0f0f', BUILD_FONT_CACHE, 'other-cache'], BUILD);

  const { kept } = dispatch('activate', {});
  await Promise.all(kept);

  expect(self.caches.delete).toHaveBeenCalledTimes(1);
  expect(self.caches.delete).toHaveBeenCalledWith('fuxi-fonts-0f0f0f0f');
  expect(self.clients.claim).toHaveBeenCalledTimes(1);
});

test('6a B5 a cached font is answered from the cache without the network', async () => {
  const { self, cache, dispatch } = loadServiceWorker([], [], BUILD);
  const cached = fakeResponse();
  cache.match.mockResolvedValue(cached);

  const { response } = await dispatchFetch(dispatch, FONT_URL);

  expect(self.caches.open).toHaveBeenCalledWith(BUILD_FONT_CACHE);
  expect(response).toBe(cached);
  expect(self.fetch).not.toHaveBeenCalled();
});

test('6a B5 a font missed by the cache is fetched, returned and stored in the cache of this build', async () => {
  const { self, cache, dispatch } = loadServiceWorker([], [], BUILD);

  const { response, kept } = await dispatchFetch(dispatch, FONT_URL);
  await Promise.all(kept);

  const downloaded = await self.fetch.mock.results[0].value;
  expect(response).toBe(downloaded);
  expect(self.caches.open).toHaveBeenCalledWith(BUILD_FONT_CACHE);
  expect(cache.put).toHaveBeenCalledTimes(1);
  expect(cache.put.mock.calls[0][0]).toEqual({ url: FONT_URL, method: 'GET' });
});

test('6a B5 the fetch rule calls waitUntil at once, before any await', () => {
  const { dispatch } = loadServiceWorker([], [], BUILD);

  const { waitUntil } = dispatch('fetch', fetchEvent(FONT_URL));

  expect(waitUntil).toHaveBeenCalledTimes(1);
});

test('6a B5 the downloaded font is returned while it is still being stored', async () => {
  const { cache, dispatch } = loadServiceWorker([], [], BUILD);
  const storing = deferred<undefined>();
  cache.put.mockImplementation(() => storing.promise);

  const { response, kept } = await dispatchFetch(dispatch, FONT_URL);

  expect(response).toBeDefined();
  storing.resolve(undefined);
  await Promise.all(kept);
});

test('6a B5 a failed store still answers the font and fails nothing', async () => {
  const { self, cache, dispatch } = loadServiceWorker([], [], BUILD);
  cache.put.mockRejectedValue(new DOMException('Quota exceeded', 'QuotaExceededError'));

  const { response, kept } = await dispatchFetch(dispatch, FONT_URL);

  expect(response).toBe(await self.fetch.mock.results[0].value);
  await expect(Promise.all(kept)).resolves.toBeDefined();
});

test('6a B5 a failed font answer is returned but not stored', async () => {
  const { self, cache, dispatch } = loadServiceWorker([], [], BUILD);
  self.fetch.mockResolvedValue(fakeResponse(false));

  const { kept } = await dispatchFetch(dispatch, FONT_URL);
  await Promise.all(kept);

  expect(cache.put).not.toHaveBeenCalled();
});

test('6a B5 a network failure fails the font as the browser would and leaves no failed background work', async () => {
  const { self, dispatch } = loadServiceWorker([], [], BUILD);
  self.fetch.mockRejectedValue(new TypeError('Failed to fetch'));

  const event = fetchEvent(FONT_URL);
  const { kept } = dispatch('fetch', event);

  await expect(event.respondWith.mock.calls[0][0]).rejects.toThrow('Failed to fetch');
  await expect(Promise.all(kept)).resolves.toBeDefined();
});
test.each([
  ['open', (fakes: ReturnType<typeof loadServiceWorker>) => fakes.self.caches.open.mockRejectedValue(new Error('No cache'))],
  ['match', (fakes: ReturnType<typeof loadServiceWorker>) => fakes.cache.match.mockRejectedValue(new Error('No match'))],
])('6a B5 a failing cache %s falls back to the network', async (_, breakCache) => {
  const fakes = loadServiceWorker([], [], BUILD);
  breakCache(fakes);

  const { response } = await dispatchFetch(fakes.dispatch, FONT_URL);

  expect(fakes.self.fetch).toHaveBeenCalledTimes(1);
  expect(response).toBe(await fakes.self.fetch.mock.results[0].value);
});

test.each([
  ['a font of another site', 'https://fonts.example/nunito.woff2', 'GET'],
  ['a request that is not a font', `${APP_ORIGIN}/assets/index.js`, 'GET'],
  ['a font request that is not GET', FONT_URL, 'POST'],
])('6a B5 %s is left to the browser', async (_, url, method) => {
  const { self, dispatch } = loadServiceWorker([], [], BUILD);

  const { response } = await dispatchFetch(dispatch, url, method);

  expect(response).toBeUndefined();
  expect(self.caches.open).not.toHaveBeenCalled();
});

const FONT_CONDITION = { urlPattern: '/*.woff2', requestMethod: 'GET' };

test('6a B10 with Static Routing, install sends only the font requests to the worker and the rest to the network', async () => {
  const { dispatch } = loadServiceWorker([], [], BUILD);
  const addRoutes = vi.fn(async (_rules: unknown) => undefined);

  const { kept } = dispatch('install', { addRoutes });
  await Promise.all(kept);

  expect(addRoutes).toHaveBeenCalledTimes(1);
  expect(addRoutes).toHaveBeenCalledWith([
    { condition: FONT_CONDITION, source: 'fetch-event' },
    { condition: { not: FONT_CONDITION }, source: 'network' },
  ]);
});

test.each([
  ['throws', () => {
    throw new TypeError('Unsupported rule');
  }],
  ['rejects', async () => Promise.reject(new TypeError('Unsupported rule'))],
])('6a B10 an addRoutes that %s does not break the install', async (_, failure) => {
  const { cache, dispatch } = loadServiceWorker([], [], BUILD);

  const { kept } = dispatch('install', { addRoutes: vi.fn(failure) });

  await expect(Promise.all(kept)).resolves.toBeDefined();
  expect(cache.addAll).toHaveBeenCalledTimes(1);
});
test('a click on a notification without wordIds opens /flashcard and throws nothing', async () => {
  const { self, dispatch } = loadServiceWorker();
  const notification = { data: null, close: vi.fn() };

  const { kept } = dispatch('notificationclick', { notification });
  await Promise.all(kept);

  expect(self.clients.openWindow).toHaveBeenCalledWith('/flashcard');
});
