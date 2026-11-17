// Section P: the Settings page.
import { act, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { expect, onTestFinished, test, vi } from 'vitest';
import { moveTo } from '../services/page_location';
import { API_URL, deferred, mockApi, type ApiMock, networkFailure, problem } from '../test/api_mock';
import { LOCATION_TEST_ID, renderApp } from '../test/render_app';

// jsdom cannot leave the page; the Notion button's move is recorded instead.
vi.mock('../services/page_location', () => ({ moveTo: vi.fn() }));

const NOT_CONNECTED_ANSWER = { body: { isConnected: false, workspaceName: null } };

const openSettings = (route = {}, path = '/settings') => {
  const api = mockApi({
    'POST /Update_Collections': { status: 204 },
    'GET /api/GetNotionConnection': NOT_CONNECTED_ANSWER,
    ...route,
  });
  renderApp(path);

  return api;
};

const button = (name: string) => screen.getByRole('button', { name });

// Since 6b the page reads the Notion state when it opens (6b E3); "no call" means no other call.
const callsBesidesNotionState = (api: ApiMock) =>
  api.calls.filter((call) => !call.path.endsWith('/GetNotionConnection'));

const stubNotification = (permission: NotificationPermission, answer: NotificationPermission = permission) => {
  const requestPermission = vi.fn(async () => answer);
  vi.stubGlobal('Notification', { permission, requestPermission });

  return requestPermission;
};

const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/endpoint-1';
const P256DH = 'BP256dh-key';
const AUTH = 'auth-secret';
// Bytes that need "-" and "_" in URL-safe Base64, so the decoding is tested.
const KEY_BYTES = Uint8Array.from({ length: 65 }, (_, index) => (index === 0 ? 4 : 0xfb + (index % 5)));
const PUBLIC_KEY = btoa(String.fromCharCode(...KEY_BYTES)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

// The key of an older VAPID key pair, so an existing subscription made with it is stale.
const OTHER_KEY_BYTES = Uint8Array.from(KEY_BYTES, (byte, index) => (index === 0 ? byte : byte ^ 0xff));
const NEW_ENDPOINT = 'https://fcm.googleapis.com/fcm/send/endpoint-new';
const SERVICE_WORKER_READY_TIMEOUT_MS = 10_000;

/** A subscription made with the key bytes. By default the current key, as the browser keeps it: an ArrayBuffer. */
const fakeSubscription = (endpoint = ENDPOINT, key: Uint8Array | null = KEY_BYTES) => ({
  options: { applicationServerKey: key === null ? null : key.slice().buffer },
  toJSON: () => ({ endpoint, keys: { p256dh: P256DH, auth: AUTH } }),
  unsubscribe: vi.fn(async () => true),
});

type FakeSubscription = ReturnType<typeof fakeSubscription>;

const NEVER_READY = new Promise<never>(() => undefined);

/** A browser with a service worker and PushManager. jsdom has neither. */
const stubPush = (existing: FakeSubscription | null = null, isReady = true) => {
  const pushManager = {
    getSubscription: vi.fn(async () => existing),
    subscribe: vi.fn(async (_options: PushSubscriptionOptionsInit) => fakeSubscription(NEW_ENDPOINT)),
  };
  vi.stubGlobal('PushManager', class {});
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: { ready: isReady ? Promise.resolve({ pushManager }) : NEVER_READY },
  });
  onTestFinished(() => {
    delete (navigator as { serviceWorker?: unknown }).serviceWorker;
  });

  return pushManager;
};

const PUSH_ROUTES = {
  'GET /api/GetVapidPublicKey': { body: { publicKey: PUBLIC_KEY } },
  'POST /api/SavePushSubscription': { status: 204 },
};

const enableNotifications = async () => act(async () => fireEvent.click(button('Enable notifications')));


test('P1 the page shows its title and link without a call', () => {
  const api = openSettings();

  expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument();
  expect(button('Update embeddings')).toBeInTheDocument();
  expect(callsBesidesNotionState(api)).toHaveLength(0);
});

test('P2 the info button shows its tooltip on hover and focus', () => {
  openSettings();

  fireEvent.focus(button('About updating embeddings'));

  expect(screen.getByRole('tooltip')).toHaveTextContent('It will update to your current data.');
});

test('P3 the link asks "Are you sure?" without a call', () => {
  const api = openSettings();

  fireEvent.click(button('Update embeddings'));

  expect(screen.getByRole('dialog', { name: 'Are you sure?' })).toBeInTheDocument();
  expect(button('Yes')).toBeInTheDocument();
  expect(callsBesidesNotionState(api)).toHaveLength(0);
});

test('P4 Yes calls Update_Collections once, P6 even when clicked twice, P5 then shows the result', async () => {
  const pending = deferred();
  const api = openSettings({ 'POST /Update_Collections': () => pending.promise });
  fireEvent.click(button('Update embeddings'));

  fireEvent.click(button('Yes'));
  fireEvent.click(button('Yes'));
  await act(async () => pending.resolve({ status: 204 }));

  expect(api.callsTo('Update_Collections')).toHaveLength(1);
  expect(screen.getByRole('dialog', { name: 'Embeddings updated' })).toBeInTheDocument();
});

test('P7 a failed call shows "Embeddings could not be updated."', async () => {
  openSettings({ 'POST /Update_Collections': networkFailure });
  fireEvent.click(button('Update embeddings'));

  fireEvent.click(button('Yes'));

  expect(await screen.findByRole('dialog', { name: 'Embeddings could not be updated.' })).toBeInTheDocument();
});

test('P8 the backdrop and Escape close the dialogs', async () => {
  openSettings();
  fireEvent.click(button('Update embeddings'));
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

  fireEvent.click(button('Update embeddings'));
  await act(async () => fireEvent.click(button('Yes')));
  fireEvent.click(button('Close dialog'));

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

test('M0 "Enable notifications" is under the "Update embeddings" row', () => {
  stubNotification('default');
  stubPush();
  openSettings();

  const update = button('Update embeddings');
  const enable = button('Enable notifications');
  expect(update.compareDocumentPosition(enable) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test('M1 opening the Settings page does not ask and M2 "default" reads "not asked" with the button enabled', async () => {
  const requestPermission = stubNotification('default');
  stubPush();
  openSettings();

  expect(await screen.findByText('Notifications: not asked')).toBeInTheDocument();
  expect(button('Enable notifications')).toBeEnabled();
  expect(requestPermission).not.toHaveBeenCalled();
});

test.each([
  ['M3', 'granted', 'Notifications: allowed'],
  ['M4', 'denied', 'Notifications: blocked'],
] as const)('%s permission %s reads "%s"', async (_, permission, text) => {
  stubNotification(permission);
  stubPush();
  openSettings();

  expect(await screen.findByText(text)).toBeInTheDocument();
});

test('M5 a browser without notifications reads "not supported" and disables the button', async () => {
  vi.stubGlobal('Notification', undefined);
  delete (window as { Notification?: unknown }).Notification;
  openSettings();

  expect(await screen.findByText('Notifications: not supported')).toBeInTheDocument();
  expect(button('Enable notifications')).toBeDisabled();
});

test('M6 the button asks once and M7 the state follows the answer', async () => {
  const requestPermission = stubNotification('default', 'granted');
  stubPush();
  openSettings(PUSH_ROUTES);
  screen.getByText('Notifications: not asked');

  await enableNotifications();

  expect(requestPermission).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Notifications: allowed')).toBeInTheDocument();
});

test('I1 opening the Settings page asks nothing and calls no push API', async () => {
  const requestPermission = stubNotification('granted');
  const pushManager = stubPush(fakeSubscription());
  const api = openSettings(PUSH_ROUTES);

  await act(async () => Promise.resolve());

  expect(requestPermission).not.toHaveBeenCalled();
  expect(pushManager.getSubscription).not.toHaveBeenCalled();
  expect(pushManager.subscribe).not.toHaveBeenCalled();
  expect(callsBesidesNotionState(api)).toHaveLength(0);
});

test('I2 "Enable notifications" asks the browser for permission', async () => {
  const requestPermission = stubNotification('default', 'granted');
  stubPush();
  openSettings(PUSH_ROUTES);

  await enableNotifications();

  expect(requestPermission).toHaveBeenCalledTimes(1);
});

test('I3 permission "denied" calls no GetVapidPublicKey and shows "Notifications: blocked"', async () => {
  stubNotification('default', 'denied');
  const pushManager = stubPush();
  const api = openSettings(PUSH_ROUTES);

  await enableNotifications();

  expect(screen.getByText('Notifications: blocked')).toBeInTheDocument();
  expect(api.callsTo('GetVapidPublicKey')).toHaveLength(0);
  expect(api.callsTo('SavePushSubscription')).toHaveLength(0);
  expect(pushManager.subscribe).not.toHaveBeenCalled();
  expect(button('Enable notifications')).toBeDisabled();
});

test('I4 permission "granted" calls GetVapidPublicKey once', async () => {
  stubNotification('default', 'granted');
  stubPush();
  const api = openSettings(PUSH_ROUTES);

  await enableNotifications();

  expect(api.callsTo('GetVapidPublicKey')).toHaveLength(1);
  expect(api.callsTo('GetVapidPublicKey')[0].method).toBe('GET');
});

test('I5 subscribe gets userVisibleOnly true and the key decoded from URL-safe Base64', async () => {
  expect(PUBLIC_KEY).toMatch(/[-_]/);
  stubNotification('default', 'granted');
  const pushManager = stubPush();
  openSettings(PUSH_ROUTES);

  await enableNotifications();

  expect(pushManager.subscribe).toHaveBeenCalledTimes(1);
  const options = pushManager.subscribe.mock.calls[0][0];
  expect(options.userVisibleOnly).toBe(true);
  expect(options.applicationServerKey).toEqual(KEY_BYTES);
});

test('I6 SavePushSubscription gets endpoint, p256dh and auth of the subscription', async () => {
  stubNotification('default', 'granted');
  stubPush();
  const api = openSettings(PUSH_ROUTES);

  await enableNotifications();

  const saves = api.callsTo('SavePushSubscription');
  expect(saves).toHaveLength(1);
  expect(saves[0].method).toBe('POST');
  expect(saves[0].body).toEqual({ endpoint: NEW_ENDPOINT, p256dh: P256DH, auth: AUTH });
});

test('I7 a saved subscription shows "Notifications: allowed" and no error, not before the save ends', async () => {
  stubNotification('default', 'granted');
  stubPush();
  const saving = deferred();
  const api = openSettings({ ...PUSH_ROUTES, 'POST /api/SavePushSubscription': () => saving.promise });

  await enableNotifications();
  expect(api.callsTo('SavePushSubscription')).toHaveLength(1);
  expect(screen.getByText('Notifications: not asked')).toBeInTheDocument();
  expect(screen.queryByText('Notifications: allowed')).not.toBeInTheDocument();
  await act(async () => saving.resolve({ status: 204 }));

  expect(screen.getByText('Notifications: allowed')).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(button('Enable notifications')).toBeEnabled();
});

test.each([
  ['GetVapidPublicKey', { 'GET /api/GetVapidPublicKey': networkFailure }, false],
  ['GetVapidPublicKey with an empty key', { 'GET /api/GetVapidPublicKey': { body: { publicKey: '' } } }, false],
  ['subscribe', {}, true],
  ['SavePushSubscription', { 'POST /api/SavePushSubscription': problem(500, 'Server error') }, false],
])('I8 a failing %s shows "Notifications could not be enabled." with role alert', async (_, routes, failsSubscribe) => {
  stubNotification('default', 'granted');
  const pushManager = stubPush();

  if (failsSubscribe) {
    pushManager.subscribe.mockRejectedValue(new DOMException('Registration failed', 'AbortError'));
  }

  openSettings({ ...PUSH_ROUTES, ...routes });

  await enableNotifications();

  expect(screen.getByRole('alert')).toHaveTextContent('Notifications could not be enabled.');
  expect(button('Enable notifications')).toBeEnabled();
  expect(screen.queryByText('Notifications: allowed')).not.toBeInTheDocument();
  expect(screen.getByText('Notifications: not asked')).toBeInTheDocument();
});

test('I8 the error goes away when a later click succeeds', async () => {
  stubNotification('default', 'granted');
  stubPush();
  const api = openSettings({ ...PUSH_ROUTES, 'POST /api/SavePushSubscription': networkFailure });
  await enableNotifications();
  expect(screen.getByRole('alert')).toBeInTheDocument();

  api.set('POST /api/SavePushSubscription', { status: 204 });
  await enableNotifications();

  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('I9 a click while the subscription is pending sends no second request', async () => {
  const requestPermission = stubNotification('default', 'granted');
  const pushManager = stubPush();
  const pending = deferred();
  const api = openSettings({ ...PUSH_ROUTES, 'GET /api/GetVapidPublicKey': () => pending.promise });

  await enableNotifications();
  expect(button('Enable notifications')).toBeDisabled();
  await enableNotifications();
  await act(async () => pending.resolve({ body: { publicKey: PUBLIC_KEY } }));

  expect(requestPermission).toHaveBeenCalledTimes(1);
  expect(api.callsTo('GetVapidPublicKey')).toHaveLength(1);
  expect(pushManager.subscribe).toHaveBeenCalledTimes(1);
  expect(api.callsTo('SavePushSubscription')).toHaveLength(1);
  expect(button('Enable notifications')).toBeEnabled();
});

test('I10 with "granted" and a browser subscription of the current key, a click sends it again and creates no new one', async () => {
  const existing = fakeSubscription('https://updates.push.services.mozilla.com/wpush/v2/existing');
  stubNotification('granted');
  const pushManager = stubPush(existing);
  const api = openSettings(PUSH_ROUTES);
  expect(button('Enable notifications')).toBeEnabled();

  await enableNotifications();

  expect(pushManager.subscribe).not.toHaveBeenCalled();
  expect(existing.unsubscribe).not.toHaveBeenCalled();
  expect(api.callsTo('GetVapidPublicKey')).toHaveLength(1);
  expect(api.callsTo('SavePushSubscription')[0].body).toEqual({
    endpoint: 'https://updates.push.services.mozilla.com/wpush/v2/existing',
    p256dh: P256DH,
    auth: AUTH,
  });
  expect(screen.getByText('Notifications: allowed')).toBeInTheDocument();
});

test('I11 a browser without PushManager reads "not supported" and disables the button', async () => {
  const requestPermission = stubNotification('default');
  stubPush();
  delete (globalThis as { PushManager?: unknown }).PushManager;
  openSettings();

  expect(await screen.findByText('Notifications: not supported')).toBeInTheDocument();
  expect(button('Enable notifications')).toBeDisabled();
  expect(requestPermission).not.toHaveBeenCalled();
});

test('I11 a browser without service workers reads "not supported" and disables the button', async () => {
  stubNotification('default');
  vi.stubGlobal('PushManager', class {});
  openSettings();

  expect(await screen.findByText('Notifications: not supported')).toBeInTheDocument();
  expect(button('Enable notifications')).toBeDisabled();
});

test.each([
  ['another key', OTHER_KEY_BYTES],
  ['no key', null],
])(
  'I13 Given an existing subscription made with %s, when the button is clicked, then it is unsubscribed, a new one is made with the current key and the new one is saved',
  async (_, key) => {
    const existing = fakeSubscription(ENDPOINT, key);
    stubNotification('granted');
    const pushManager = stubPush(existing);
    const api = openSettings(PUSH_ROUTES);

    await enableNotifications();

    expect(existing.unsubscribe).toHaveBeenCalledTimes(1);
    expect(pushManager.subscribe).toHaveBeenCalledTimes(1);
    expect(existing.unsubscribe.mock.invocationCallOrder[0]).toBeLessThan(
      pushManager.subscribe.mock.invocationCallOrder[0],
    );
    expect(pushManager.subscribe.mock.calls[0][0].applicationServerKey).toEqual(KEY_BYTES);
    expect(api.callsTo('GetVapidPublicKey')).toHaveLength(1);
    const saves = api.callsTo('SavePushSubscription');
    expect(saves).toHaveLength(1);
    expect(saves[0].body).toEqual({ endpoint: NEW_ENDPOINT, p256dh: P256DH, auth: AUTH });
    expect(screen.getByText('Notifications: allowed')).toBeInTheDocument();
  },
);

test("I14 Given a service worker that is never ready, when 10 seconds pass, then 'Notifications could not be enabled.' is shown and the button is enabled again", async () => {
  vi.useFakeTimers();
  stubNotification('default', 'granted');
  stubPush(null, false);
  const api = openSettings(PUSH_ROUTES);

  await enableNotifications();
  await act(async () => vi.advanceTimersByTimeAsync(SERVICE_WORKER_READY_TIMEOUT_MS - 1));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(button('Enable notifications')).toBeDisabled();

  await act(async () => vi.advanceTimersByTimeAsync(1));

  expect(screen.getByRole('alert')).toHaveTextContent('Notifications could not be enabled.');
  expect(button('Enable notifications')).toBeEnabled();
  expect(screen.queryByText('Notifications: allowed')).not.toBeInTheDocument();
  expect(api.callsTo('SavePushSubscription')).toHaveLength(0);
});

test('I14 the timeout is cleared when the service worker is ready', async () => {
  vi.useFakeTimers();
  stubNotification('default', 'granted');
  stubPush();
  openSettings(PUSH_ROUTES);

  await enableNotifications();
  await act(async () => vi.advanceTimersByTimeAsync(0));

  expect(screen.getByText('Notifications: allowed')).toBeInTheDocument();
  expect(vi.getTimerCount()).toBe(0);
});

// Phase 6a section C and D: the Update Embeddings confirm pop-up and its result dialog.
const SYNC_TEXT = 'Your info will be synced';
const warningIcon = (dialog: HTMLElement) => dialog.querySelector('.embeddings-update__warning');

test('6a C9 the confirm and the result dialogs each show the close button', async () => {
  openSettings();
  fireEvent.click(button('Update embeddings'));
  const confirm = screen.getByRole('dialog', { name: 'Are you sure?' });
  expect(within(confirm).getByRole('button', { name: 'Close dialog' })).toHaveClass('dialog__close');

  await act(async () => fireEvent.click(button('Yes')));

  const result = screen.getByRole('dialog', { name: 'Embeddings updated' });
  expect(within(result).getByRole('button', { name: 'Close dialog' })).toHaveClass('dialog__close');
});

test('6a D2 the confirm pop-up shows a big round-bordered amber i icon above its title', () => {
  openSettings();
  fireEvent.click(button('Update embeddings'));

  const dialog = screen.getByRole('dialog', { name: 'Are you sure?' });
  const icon = warningIcon(dialog);
  expect(icon).not.toBeNull();
  expect(icon?.querySelector('svg')).not.toBeNull();
  const title = within(dialog).getByRole('heading', { name: 'Are you sure?' });
  expect((icon as Element).compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test('6a D3 the confirm pop-up shows "Your info will be synced"', () => {
  openSettings();
  fireEvent.click(button('Update embeddings'));

  expect(within(screen.getByRole('dialog')).getByText(SYNC_TEXT)).toBeInTheDocument();
});

test('6a D4 the confirm button keeps the primary button style', () => {
  openSettings();
  fireEvent.click(button('Update embeddings'));

  expect(button('Yes')).toHaveClass('embeddings-update__confirm');
});

test('6a D6 the confirm button still calls Update_Collections', async () => {
  const api = openSettings();
  fireEvent.click(button('Update embeddings'));

  await act(async () => fireEvent.click(button('Yes')));

  expect(api.callsTo('Update_Collections')).toHaveLength(1);
});

test.each([
  ['updated', { status: 204 }, 'Embeddings updated'],
  ['failed', networkFailure, 'Embeddings could not be updated.'],
] as const)('6a D7 the %s result dialog has no amber icon and no sync text', async (_, answer, title) => {
  openSettings({ 'POST /Update_Collections': answer });
  fireEvent.click(button('Update embeddings'));

  await act(async () => fireEvent.click(button('Yes')));

  const result = await screen.findByRole('dialog', { name: title });
  expect(warningIcon(result)).toBeNull();
  expect(within(result).queryByText(SYNC_TEXT)).not.toBeInTheDocument();
});

test('6a D8 the amber icon is hidden from screen readers and the dialog keeps its title as its name', () => {
  openSettings();
  fireEvent.click(button('Update embeddings'));

  const dialog = screen.getByRole('dialog', { name: 'Are you sure?' });
  expect(warningIcon(dialog)).toHaveAttribute('aria-hidden', 'true');
  expect(dialog).toHaveAccessibleName('Are you sure?');
});

test('6a C13 the confirm and the result dialog titles come from Dialog and they draw no title of their own', async () => {
  openSettings();
  fireEvent.click(button('Update embeddings'));
  const confirmTitles = screen.getByRole('dialog', { name: 'Are you sure?' }).querySelectorAll('h2');
  expect(confirmTitles).toHaveLength(1);
  expect(confirmTitles[0]).toHaveClass('dialog__title');

  await act(async () => fireEvent.click(button('Yes')));

  const result = screen.getByRole('dialog', { name: 'Embeddings updated' });
  const resultTitles = result.querySelectorAll('h2');
  expect(resultTitles).toHaveLength(1);
  expect(resultTitles[0]).toHaveClass('dialog__title');
  // The title keeps its heading role and is announced through the status block around it.
  expect(resultTitles[0]).not.toHaveAttribute('role');
  expect(resultTitles[0].closest('[role="status"]')).not.toBeNull();
});

// Phase 6a section E: the Requests toggle.
const requestsToggle = () => button('Requests');
// 6a's empty note; since 6b the toggle holds the Notion row (6b E1).
const NO_REQUESTS = 'No requests yet.';
const CONNECT_NOTION = 'Connect Notion';

test('6a E1 the Requests toggle is after "Enable notifications" and before the Credits block', () => {
  openSettings();

  const toggle = requestsToggle();
  expect(button('Enable notifications').compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const credits = screen.getByRole('heading', { level: 2, name: 'Credits' });
  expect(toggle.compareDocumentPosition(credits) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test('6a E2 the Requests toggle starts closed without its content', () => {
  openSettings();

  expect(requestsToggle()).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('button', { name: CONNECT_NOTION })).not.toBeInTheDocument();
});

test('6a E3 a click opens the toggle with its content and E4 a second click closes it', () => {
  openSettings();

  fireEvent.click(requestsToggle());
  expect(requestsToggle()).toHaveAttribute('aria-expanded', 'true');
  expect(button(CONNECT_NOTION)).toBeInTheDocument();

  fireEvent.click(requestsToggle());
  expect(requestsToggle()).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('button', { name: CONNECT_NOTION })).not.toBeInTheDocument();
});

test('6a E3 a click on the arrow opens the toggle', () => {
  openSettings();

  fireEvent.click(requestsToggle().querySelector('svg') as Element);

  expect(requestsToggle()).toHaveAttribute('aria-expanded', 'true');
});

test('6a E6 the Settings page opened again shows the toggle closed', () => {
  openSettings();
  fireEvent.click(requestsToggle());
  cleanup();

  openSettings();

  expect(requestsToggle()).toHaveAttribute('aria-expanded', 'false');
});

test('6a E7 the arrow turns when the toggle opens', () => {
  openSettings();
  const arrow = () => requestsToggle().querySelector('svg');
  expect(arrow()).toHaveClass('disclosure-toggle__icon');
  expect(arrow()).not.toHaveClass('disclosure-toggle__icon--open');

  fireEvent.click(requestsToggle());

  expect(arrow()).toHaveClass('disclosure-toggle__icon', 'disclosure-toggle__icon--open');
});

// Phase 6b section E: the Notion row in the Requests toggle.
const openRequests = (route = {}, path = '/settings') => {
  const api = openSettings(route, path);
  fireEvent.click(requestsToggle());

  return api;
};

test('6b E1 the open Requests toggle holds the "Connect Notion" button and no "No requests yet."', () => {
  openRequests();

  expect(button(CONNECT_NOTION)).toBeInTheDocument();
  expect(screen.queryByText(NO_REQUESTS)).not.toBeInTheDocument();
});

test('6b E2 the Notion button draws the inline Notion logo hidden from screen readers and keeps its name', () => {
  openRequests();

  const logo = button(CONNECT_NOTION).querySelector('svg');
  expect(logo).toHaveClass('notion-logo');
  expect(logo?.querySelector('path')).not.toBeNull();
  expect(logo).toHaveAttribute('aria-hidden', 'true');
  expect(button(CONNECT_NOTION)).toHaveAccessibleName(CONNECT_NOTION);
});

test('6b E2b the Notion button shows the text "Notion" at the right of its logo', () => {
  openRequests();

  const notion = button(CONNECT_NOTION);
  const label = within(notion).getByText('Notion');
  const logo = notion.querySelector('svg')!;
  expect(logo.compareDocumentPosition(label) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // The visible text is part of the button's name, so a voice command "click Notion" finds it.
  expect(notion).toHaveAccessibleName(expect.stringContaining('Notion'));
});

test('6b E3 opening the Settings page calls GetNotionConnection once', async () => {
  const api = openSettings();

  await act(async () => Promise.resolve());

  const calls = api.callsTo('GetNotionConnection');
  expect(calls).toHaveLength(1);
  expect(calls[0].method).toBe('GET');
  expect(calls[0].url.origin).toBe(API_URL);
});

const notionAnswer = (isConnected: boolean, workspaceName: string | null) => ({
  'GET /api/GetNotionConnection': { body: { isConnected, workspaceName } },
});

test.each([
  ['E4', false, null, 'Not connected'],
  ['E5', true, 'Study Notes', 'Connected: Study Notes'],
  ['E6', true, null, 'Connected'],
])('6b %s isConnected %s with workspace %s reads "%s"', async (_, isConnected, workspaceName, text) => {
  openRequests(notionAnswer(isConnected, workspaceName));

  expect(await screen.findByText(text)).toBeInTheDocument();
});

const NOTION_CONNECT_URL = `${API_URL}/api/NotionConnect`;

const clickConnect = () => {
  vi.mocked(moveTo).mockClear();
  fireEvent.click(button(CONNECT_NOTION));
};

test.each([
  ['E7', 'Not connected', notionAnswer(false, null)],
  ['E8 (reconnect)', 'Connected: Study Notes', notionAnswer(true, 'Study Notes')],
  ['E10 when GetNotionConnection fails', 'Not connected', { 'GET /api/GetNotionConnection': networkFailure }],
])('6b %s the row reads "%s" and the Notion button moves the browser to the API sign-in start', async (_, text, route) => {
  openRequests(route);
  expect(await screen.findByText(text)).toBeInTheDocument();

  clickConnect();

  expect(moveTo).toHaveBeenCalledExactlyOnceWith(NOTION_CONNECT_URL);
});

test('6b E4-E6 while GetNotionConnection is pending the row shows no state, so a connected Notion never reads "Not connected"', async () => {
  const pending = deferred();
  openRequests({ 'GET /api/GetNotionConnection': () => pending.promise });

  expect(screen.queryByText('Not connected')).not.toBeInTheDocument();
  await act(async () => pending.resolve({ body: { isConnected: true, workspaceName: 'Study Notes' } }));

  expect(screen.getByText('Connected: Study Notes')).toBeInTheDocument();
});

test('6b E9 the row has no Disconnect button', async () => {
  openRequests(notionAnswer(true, 'Study Notes'));
  await screen.findByText('Connected: Study Notes');

  expect(screen.queryByRole('button', { name: /disconnect/i })).not.toBeInTheDocument();
});

test('6b E11 ?notion=connected opens the Requests toggle with the state from GetNotionConnection and starts no build', async () => {
  const api = openSettings(notionAnswer(true, 'Study Notes'), '/settings?notion=connected');

  expect(requestsToggle()).toHaveAttribute('aria-expanded', 'true');
  expect(await screen.findByText('Connected: Study Notes')).toBeInTheDocument();
  expect(api.callsTo('Update_Collections')).toHaveLength(0);
});

test('6b E12 ?notion=failed opens the Requests toggle with the alert "Notion could not be connected."', async () => {
  openSettings({}, '/settings?notion=failed');

  expect(requestsToggle()).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('alert')).toHaveTextContent('Notion could not be connected.');
  expect(await screen.findByText('Not connected')).toBeInTheDocument();
});

test('6b E11 ?notion=connected shows no alert', async () => {
  openSettings(notionAnswer(true, 'Study Notes'), '/settings?notion=connected');

  await screen.findByText('Connected: Study Notes');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test.each(['connected', 'failed'])(
  '6b E13 ?notion=%s is removed from the address and the page keeps the result',
  async (result) => {
    openSettings({}, `/settings?notion=${result}`);

    await waitFor(() => expect(screen.getByTestId(LOCATION_TEST_ID)).toHaveTextContent(/^\/settings$/));
    expect(requestsToggle()).toHaveAttribute('aria-expanded', 'true');
    expect(screen.queryAllByRole('alert')).toHaveLength(result === 'failed' ? 1 : 0);
  },
);

test('6b E14 the Settings page opened without ?notion shows the Requests toggle closed', () => {
  openSettings({}, '/settings?other=1');

  expect(requestsToggle()).toHaveAttribute('aria-expanded', 'false');
  expect(screen.getByTestId(LOCATION_TEST_ID)).toHaveTextContent('/settings?other=1');
});

// Phase 6b section F: the i tooltip of the Notion row.
const ABOUT_NOTION = 'About Notion';
const NOTION_TIP = 'Connect Notion pages';

test('6b F1 an i button named "About Notion" is at the right of the Notion button, in the same row', () => {
  openRequests();

  const notion = button(CONNECT_NOTION);
  const about = button(ABOUT_NOTION);
  expect(notion.compareDocumentPosition(about) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(notion.closest('.notion-connect__row')).toContainElement(about);
  expect(about.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
});

const expectNotionTipShown = () => {
  const tip = screen.getByRole('tooltip');
  expect(tip).toHaveTextContent(NOTION_TIP);
  // F6: the i button names the tooltip it shows.
  expect(button(ABOUT_NOTION)).toHaveAttribute('aria-describedby', tip.id);
};

test.each([
  ['F2 the pointer moves over it', fireEvent.mouseEnter],
  ['F3 it gets keyboard focus', fireEvent.focus],
  ['F4 it is clicked or tapped', fireEvent.click],
])('6b when %s, the i button shows "Connect Notion pages" (F6 role tooltip, aria-describedby)', (_, show) => {
  openRequests();
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

  show(button(ABOUT_NOTION));

  expectNotionTipShown();
});

test.each([
  ['Escape is pressed', (about: HTMLElement) => fireEvent.keyDown(about, { key: 'Escape' })],
  ['the pointer leaves', fireEvent.mouseLeave],
  ['the focus leaves', fireEvent.blur],
])('6b F5 the shown tooltip is hidden when %s', (_, hide) => {
  openRequests();
  fireEvent.focus(button(ABOUT_NOTION));
  expectNotionTipShown();

  hide(button(ABOUT_NOTION));

  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  expect(button(ABOUT_NOTION)).not.toHaveAttribute('aria-describedby');
});

// A tap goes pointer down, focus, click; the tip was hidden at the pointer down, so the tap shows it.
const tap = (target: HTMLElement) => {
  fireEvent.pointerDown(target);
  fireEvent.focus(target);
  fireEvent.click(target);
};

test('6b review SRS-9 a first tap on the i button shows the tip, a second tap hides it', () => {
  openRequests();

  tap(button(ABOUT_NOTION));
  expectNotionTipShown();

  tap(button(ABOUT_NOTION));
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
});

test('6b review SRS-9 after a tap hid the tip, Enter on the i button (a click with no pointer) shows it again', () => {
  openRequests();
  tap(button(ABOUT_NOTION));
  tap(button(ABOUT_NOTION));

  fireEvent.click(button(ABOUT_NOTION));

  expectNotionTipShown();
});

test('6b F5 another key keeps the tooltip shown', () => {
  openRequests();
  fireEvent.focus(button(ABOUT_NOTION));

  fireEvent.keyDown(button(ABOUT_NOTION), { key: 'Tab' });

  expectNotionTipShown();
});

test('6b F7 the Notion tip starts at the i button and grows to the right, so it stays on a phone screen', () => {
  openRequests();

  fireEvent.focus(button(ABOUT_NOTION));

  expect(screen.getByRole('tooltip')).toHaveClass('tooltip__text', 'tooltip__text--start');
});

test('P2 the "Update embeddings" tip keeps ending at its i button', () => {
  openSettings();

  fireEvent.focus(button('About updating embeddings'));

  expect(screen.getByRole('tooltip')).not.toHaveClass('tooltip__text--start');
});

const TMDB_NOTICE = 'This product uses the TMDB API but is not endorsed or certified by TMDB.';

test('5c H1 the Settings page shows a Credits block with the TMDB notice under the other rows', () => {
  openSettings();

  const heading = screen.getByRole('heading', { level: 2, name: 'Credits' });
  const notice = screen.getByText(TMDB_NOTICE);
  expect(heading.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(
    button('Enable notifications').compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});

test('5c H2 the Credits block shows the TMDB logo from a local file with the alternative text "TMDB"', () => {
  openSettings();

  const logo = screen.getByRole('img', { name: 'TMDB' });
  const source = logo.getAttribute('src') ?? '';
  expect(source).toMatch(/tmdb_logo\.svg|^data:image\/svg\+xml/);
  expect(source).not.toMatch(/^(https?:)?\/\//);
  expect(screen.getByRole('heading', { level: 2, name: 'Credits' }).parentElement).toContainElement(logo);
});
