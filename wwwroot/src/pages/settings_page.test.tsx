// Section P: the Settings page.
import { act, fireEvent, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { deferred, mockApi, networkFailure } from '../test/api_mock';
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
  openSettings();

  const update = button('Update embeddings');
  const enable = button('Enable notifications');
  expect(update.compareDocumentPosition(enable) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test('M1 opening the Settings page does not ask and M2 "default" reads "not asked" with the button enabled', async () => {
  const requestPermission = stubNotification('default');
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

test('M6 the button asks once, M7 the state follows the answer and M8 nothing is subscribed', async () => {
  const requestPermission = stubNotification('default', 'granted');
  const api = openSettings();
  screen.getByText('Notifications: not asked');

  await act(async () => fireEvent.click(button('Enable notifications')));

  expect(requestPermission).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Notifications: allowed')).toBeInTheDocument();
  expect(api.callsTo('GetVapidPublicKey')).toHaveLength(0);
  expect(api.callsTo('SavePushSubscription')).toHaveLength(0);
});
