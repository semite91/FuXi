// Sections L and M: the Configs page and the notification permission.
import { act, fireEvent, screen, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { mockApi, problem } from '../test/api_mock';
import { CONFIGS } from '../test/data';
import { renderApp } from '../test/render_app';

const NO_CONTENT = { status: 204 };

const stubNotification = (permission: NotificationPermission, answer: NotificationPermission = permission) => {
  const requestPermission = vi.fn(async () => answer);
  vi.stubGlobal('Notification', { permission, requestPermission });

  return requestPermission;
};

const openConfigs = (routes = {}) => {
  const api = mockApi({
    'GET /api/GetConfigs': { body: CONFIGS },
    'POST /api/UpdateConfig': NO_CONTENT,
    'POST /api/UpdateNotificationPeriod': NO_CONTENT,
    ...routes,
  });
  renderApp('/config');

  return api;
};

const button = (name: string) => screen.getByRole('button', { name });
const editRow = async (name: string) => {
  fireEvent.click(await screen.findByRole('button', { name: `Edit ${name}` }));

  return screen.getByRole('dialog', { name });
};
const valueOf = (name: string) =>
  within(screen.getByRole('row', { name: new RegExp(name) })).getAllByRole('cell')[1].textContent;

test('L1 the page calls GetConfigs once and L2 shows Name, Value and the edit button', async () => {
  stubNotification('default');
  const api = openConfigs();

  expect(await screen.findByRole('button', { name: 'Edit Rotation Count' })).toBeInTheDocument();
  expect(api.callsTo('GetConfigs')).toHaveLength(1);
  expect(valueOf('Rotation Count')).toBe('20');
});

test('L3 the edit dialog shows the Name and Value; L4 Number, L5 Date and L6 other types', async () => {
  stubNotification('default');
  openConfigs();

  const numberDialog = await editRow('Rotation Count');
  expect(within(numberDialog).getByRole('heading', { name: 'Rotation Count' })).toBeInTheDocument();
  expect(within(numberDialog).getByLabelText('Rotation Count')).toHaveAttribute('type', 'number');
  expect(within(numberDialog).getByLabelText('Rotation Count')).toHaveValue(20);
  fireEvent.keyDown(document, { key: 'Escape' });

  const dateDialog = await editRow('Start date');
  expect(within(dateDialog).getByLabelText('Start date')).toHaveAttribute('type', 'date');
  fireEvent.keyDown(document, { key: 'Escape' });

  const textDialog = await editRow('Notebook title');
  expect(within(textDialog).getByLabelText('Notebook title')).toHaveAttribute('type', 'text');
});

test('L7 a normal row is saved with UpdateConfig and L9 the row shows the new value', async () => {
  stubNotification('default');
  const api = openConfigs();
  const dialog = await editRow('Rotation Count');

  fireEvent.change(within(dialog).getByLabelText('Rotation Count'), { target: { value: '25' } });
  await act(async () => fireEvent.click(button('Save')));

  expect(api.callsTo('UpdateConfig')[0].body).toEqual({ id: 'c1', value: '25' });
  expect(api.callsTo('UpdateNotificationPeriod')).toHaveLength(0);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(valueOf('Rotation Count')).toBe('25');
});

test('L8 the NotificationPeriod row is saved with UpdateNotificationPeriod', async () => {
  stubNotification('default');
  const api = openConfigs();
  const dialog = await editRow('Notification period');

  fireEvent.change(within(dialog).getByLabelText('Notification period'), { target: { value: '30' } });
  await act(async () => fireEvent.click(button('Save')));

  expect(api.callsTo('UpdateNotificationPeriod')[0].body).toEqual({ id: 'c2', value: '30' });
  expect(api.callsTo('UpdateConfig')).toHaveLength(0);
});

test('L10 an empty value calls nothing and keeps the dialog', async () => {
  stubNotification('default');
  const api = openConfigs();
  const dialog = await editRow('Notebook title');

  fireEvent.change(within(dialog).getByLabelText('Notebook title'), { target: { value: '  ' } });
  fireEvent.click(button('Save'));

  expect(api.callsTo('UpdateConfig')).toHaveLength(0);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('L11 a 400 answer keeps the dialog, shows the detail and keeps the old value', async () => {
  stubNotification('default');
  openConfigs({ 'POST /api/UpdateConfig': problem(400, 'The value must be a whole number greater than zero.') });
  const dialog = await editRow('Rotation Count');

  fireEvent.change(within(dialog).getByLabelText('Rotation Count'), { target: { value: '0' } });
  fireEvent.click(button('Save'));

  expect(await within(dialog).findByRole('alert')).toHaveTextContent('The value must be a whole number greater than zero.');
  expect(valueOf('Rotation Count')).toBe('20');
});

test('L12 the backdrop and Escape close the dialog without a call', async () => {
  stubNotification('default');
  const api = openConfigs();

  await editRow('Rotation Count');
  fireEvent.click(button('Close dialog'));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await editRow('Rotation Count');
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

  expect(api.calls).toHaveLength(1);
});

test('L13 a failed GetConfigs shows an error', async () => {
  stubNotification('default');
  openConfigs({ 'GET /api/GetConfigs': problem(500, 'Server is down.') });

  expect(await screen.findByRole('alert')).toHaveTextContent('Server is down.');
});

test('M1 opening the page does not ask and M2 "default" reads "not asked" with the button enabled', async () => {
  const requestPermission = stubNotification('default');
  openConfigs();

  expect(await screen.findByText('Notifications: not asked')).toBeInTheDocument();
  expect(button('Enable notifications')).toBeEnabled();
  expect(requestPermission).not.toHaveBeenCalled();
});

test.each([
  ['M3', 'granted', 'Notifications: allowed'],
  ['M4', 'denied', 'Notifications: blocked'],
] as const)('%s permission %s reads "%s"', async (_, permission, text) => {
  stubNotification(permission);
  openConfigs();

  expect(await screen.findByText(text)).toBeInTheDocument();
});

test('M5 a browser without notifications reads "not supported" and disables the button', async () => {
  vi.stubGlobal('Notification', undefined);
  delete (window as { Notification?: unknown }).Notification;
  openConfigs();

  expect(await screen.findByText('Notifications: not supported')).toBeInTheDocument();
  expect(button('Enable notifications')).toBeDisabled();
});

test('M6 the button asks once, M7 the state follows the answer and M8 nothing is subscribed', async () => {
  const requestPermission = stubNotification('default', 'granted');
  const api = openConfigs();
  await screen.findByText('Notifications: not asked');

  await act(async () => fireEvent.click(button('Enable notifications')));

  expect(requestPermission).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Notifications: allowed')).toBeInTheDocument();
  expect(api.callsTo('GetVapidPublicKey')).toHaveLength(0);
  expect(api.callsTo('SavePushSubscription')).toHaveLength(0);
});
