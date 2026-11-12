// Section P: the Settings page.
import { act, fireEvent, screen } from '@testing-library/react';
import { expect, onTestFinished, test, vi } from 'vitest';
import { deferred, mockApi, networkFailure, problem } from '../test/api_mock';
import { renderApp } from '../test/render_app';

const openSettings = (route = {}) => {
  const api = mockApi({ 'POST /Update_Collections': { status: 204 }, ...route });
  renderApp('/settings');

  return api;
};

const button = (name: string) => screen.getByRole('button', { name });

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

const fakeSubscription = (endpoint = ENDPOINT) => ({
  toJSON: () => ({ endpoint, keys: { p256dh: P256DH, auth: AUTH } }),
});

type FakeSubscription = ReturnType<typeof fakeSubscription>;

/** A browser with a service worker and PushManager. jsdom has neither. */
const stubPush = (existing: FakeSubscription | null = null) => {
  const pushManager = {
    getSubscription: vi.fn(async () => existing),
    subscribe: vi.fn(async (_options: PushSubscriptionOptionsInit) => fakeSubscription()),
  };
  vi.stubGlobal('PushManager', class {});
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: { ready: Promise.resolve({ pushManager }) },
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
  expect(api.calls).toHaveLength(0);
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
  expect(api.calls).toHaveLength(0);
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
  expect(api.calls).toHaveLength(0);
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
  expect(saves[0].body).toEqual({ endpoint: ENDPOINT, p256dh: P256DH, auth: AUTH });
});

test('I7 a saved subscription shows "Notifications: allowed" and no error', async () => {
  stubNotification('default', 'granted');
  stubPush();
  const api = openSettings(PUSH_ROUTES);

  await enableNotifications();

  expect(api.callsTo('SavePushSubscription')).toHaveLength(1);
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

test('I10 with "granted" and a browser subscription, a click sends it again and creates no new one', async () => {
  const existing = fakeSubscription('https://updates.push.services.mozilla.com/wpush/v2/existing');
  stubNotification('granted');
  const pushManager = stubPush(existing);
  const api = openSettings(PUSH_ROUTES);
  expect(button('Enable notifications')).toBeEnabled();

  await enableNotifications();

  expect(pushManager.subscribe).not.toHaveBeenCalled();
  expect(api.callsTo('GetVapidPublicKey')).toHaveLength(0);
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
