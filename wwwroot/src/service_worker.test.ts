// Sections G and H: the push and notification click handling of public/service_worker.js.
// The file is plain JavaScript that Vite serves unbundled, so it runs here with a fake self.
import { expect, test, vi } from 'vitest';
import serviceWorkerCode from '../public/service_worker.js?raw';
import { deferred } from './test/api_mock';

const ICON = '/fuxi_192.png';
const TITLE = 'apple, river';
const WORD_IDS = 'id-1,id-2';
const FLASHCARD_URL = '/flashcard?wordIds=id-1%2Cid-2';

type Listener = (event: unknown) => void;

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

/** Runs the service worker file with a fake self and returns its listeners and fakes. */
const loadServiceWorker = (openWindows: FakeWindow[] = []) => {
  const listeners = new Map<string, Listener>();
  const self = {
    addEventListener: (type: string, listener: Listener) => listeners.set(type, listener),
    skipWaiting: vi.fn(),
    registration: { showNotification: vi.fn(async () => undefined) },
    clients: {
      claim: vi.fn(async () => undefined),
      matchAll: vi.fn(async () => openWindows),
      openWindow: vi.fn(async () => null),
    },
  };
  new Function('self', serviceWorkerCode)(self);

  /** Dispatches an event and returns the promises it gave to waitUntil. */
  const dispatch = (type: string, event: object) => {
    const kept: Promise<unknown>[] = [];
    const waitUntil = vi.fn((promise: Promise<unknown>) => kept.push(promise));
    listeners.get(type)?.({ ...event, waitUntil });

    return { kept, waitUntil };
  };

  return { self, dispatch };
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

  expect(self.registration.showNotification).toHaveBeenCalledWith(TITLE, {
    data: { wordIds: WORD_IDS },
    icon: ICON,
  });
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

test('a click on a notification without wordIds opens /flashcard and throws nothing', async () => {
  const { self, dispatch } = loadServiceWorker();
  const notification = { data: null, close: vi.fn() };

  const { kept } = dispatch('notificationclick', { notification });
  await Promise.all(kept);

  expect(self.clients.openWindow).toHaveBeenCalledWith('/flashcard');
});
