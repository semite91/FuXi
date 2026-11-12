// Sections N and O: the Schedule page. Tests run in Europe/Istanbul (UTC+3), see vite.config.ts.
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { deferred, mockApi, problem, type RecordedCall } from '../test/api_mock';
import { renderApp } from '../test/render_app';

// Thursday 12 November 2026, 10:00 local time.
const NOW = new Date('2026-11-12T07:00:00Z');
const NO_CONTENT = { status: 204 };

const WINDOW_ONE = { id: 'w1', startDate: '2026-11-12T06:00:00Z', endDate: '2026-11-12T08:00:00Z' };
const WINDOW_TWO = { id: 'w2', startDate: '2026-11-12T11:00:00Z', endDate: '2026-11-12T12:00:00Z' };
const WINDOW_THREE = { id: 'w3', startDate: '2026-11-12T14:00:00Z', endDate: '2026-11-12T15:00:00Z' };
// 13 November 22:00 until 14 November 02:00 local time.
const OVERNIGHT = { id: 'w4', startDate: '2026-11-13T19:00:00Z', endDate: '2026-11-13T23:00:00Z' };

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});

const openSchedule = (windows: object[] = [], routes = {}) => {
  const api = mockApi({
    'GET /api/GetSchedule': { body: windows },
    'POST /api/UpdateSchedule': { body: { id: 'new' } },
    'DELETE /api/DeleteSchedule': NO_CONTENT,
    ...routes,
  });
  renderApp('/schedule');

  return api;
};

const period = (call: RecordedCall) => call.url.searchParams.getAll('period');
const button = (name: string) => screen.getByRole('button', { name });
const label = () => screen.getByText(/November|December|October|–|Nov/, { selector: 'p' });
const scheduleCalls = (api: ReturnType<typeof mockApi>) => api.callsTo('GetSchedule');
const dayCell = (day: number) =>
  screen.getAllByText(String(day), { selector: '.schedule-month__number' }).map((number) => number.parentElement!);
const currentMonthCell = (day: number) =>
  dayCell(day).find((cell) => !cell.classList.contains('schedule-month__cell--outside'))!;

test('N1 the month view of this month opens with Mon to Sun', async () => {
  openSchedule();

  expect(label()).toHaveTextContent('November 2026');
  expect(screen.getByText('Mon')).toBeInTheDocument();
  expect(screen.getByText('Sun')).toBeInTheDocument();
  expect(button('Month')).toHaveAttribute('aria-pressed', 'true');
});

test('N2 GetSchedule is called once with the visible range and N3 in UTC with Z', async () => {
  const api = openSchedule();
  await waitFor(() => expect(scheduleCalls(api)).toHaveLength(1));

  // The grid runs from Monday 26 October to Monday 7 December, local midnight.
  expect(period(scheduleCalls(api)[0])).toEqual(['2026-10-25T21:00:00.000Z', '2026-12-06T21:00:00.000Z']);
});

test('N4 Next and N5 Previous move the month and load its range', async () => {
  const api = openSchedule();

  fireEvent.click(button('Next'));
  expect(label()).toHaveTextContent('December 2026');
  await waitFor(() => expect(scheduleCalls(api)).toHaveLength(2));
  expect(period(scheduleCalls(api)[1])[0]).toBe('2026-11-29T21:00:00.000Z');

  fireEvent.click(button('Previous'));
  fireEvent.click(button('Previous'));
  expect(label()).toHaveTextContent('October 2026');
  await waitFor(() => expect(scheduleCalls(api)).toHaveLength(4));
});

test('N6 Today returns to the range that holds today', () => {
  openSchedule();
  fireEvent.click(button('Next'));
  fireEvent.click(button('Next'));

  fireEvent.click(button('Today'));

  expect(label()).toHaveTextContent('November 2026');
});

test('N7 Week shows seven day rows from Monday and N10 loads nothing new inside the loaded month', async () => {
  const api = openSchedule();
  await waitFor(() => expect(scheduleCalls(api)).toHaveLength(1));

  fireEvent.click(button('Week'));

  expect(button('Week')).toHaveAttribute('aria-pressed', 'true');
  const rows = screen.getAllByRole('listitem').map((row) => row.firstChild?.textContent);
  expect(rows).toEqual(['Mon 9', 'Tue 10', 'Wed 11', 'Thu 12', 'Fri 13', 'Sat 14', 'Sun 15']);
  expect(label()).toHaveTextContent('9 – 15 Nov 2026');
  expect(scheduleCalls(api)).toHaveLength(1);
});

test('N8 Day shows the hours of the day and N9 Next moves one day', () => {
  openSchedule();

  fireEvent.click(button('Day'));
  expect(button('Day')).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getAllByRole('listitem')).toHaveLength(24);
  expect(label()).toHaveTextContent('Thu, 12 Nov 2026');

  fireEvent.click(button('Next'));
  expect(label()).toHaveTextContent('Fri, 13 Nov 2026');
});

test('N9 Week moves seven days and N10 loads the new range when it leaves the loaded one', async () => {
  const api = openSchedule();
  fireEvent.click(button('Week'));

  for (let week = 0; week < 4; week += 1) {
    fireEvent.click(button('Next'));
  }

  expect(label()).toHaveTextContent('7 – 13 Dec 2026');
  await waitFor(() => expect(scheduleCalls(api)).toHaveLength(2));
  expect(period(scheduleCalls(api)[1])).toEqual(['2026-12-06T21:00:00.000Z', '2026-12-13T21:00:00.000Z']);
});

test('N11 the month label reads like "November 2026"', () => {
  openSchedule();

  expect(label().textContent).toBe('November 2026');
});

test('N12 a window shows its local start time and N14 three windows show two chips and "+1"', async () => {
  openSchedule([WINDOW_ONE, WINDOW_TWO, WINDOW_THREE]);

  const cell = currentMonthCell(12);
  expect(await within(cell).findByRole('button', { name: 'Edit entry at 09:00' })).toHaveTextContent('09:00');
  expect(within(cell).getByRole('button', { name: 'Edit entry at 14:00' })).toBeInTheDocument();
  expect(within(cell).getByRole('button', { name: 'Show all entries of 12 November' })).toHaveTextContent('+1');
});

test('N13 a window that continues from the day before reads "cont."', async () => {
  openSchedule([OVERNIGHT]);

  expect(await within(currentMonthCell(13)).findByText('22:00')).toBeInTheDocument();
  expect(within(currentMonthCell(14)).getByText('cont.')).toBeInTheDocument();
});

test('N15 "+1" opens the Day view of that day', async () => {
  openSchedule([WINDOW_ONE, WINDOW_TWO, WINDOW_THREE]);

  fireEvent.click(await screen.findByRole('button', { name: 'Show all entries of 12 November' }));

  expect(button('Day')).toHaveAttribute('aria-pressed', 'true');
  expect(label()).toHaveTextContent('Thu, 12 Nov 2026');
  expect(screen.getByText('09:00–11:00')).toBeInTheDocument();
});

test('N16 today is marked', () => {
  openSchedule();

  expect(currentMonthCell(12).querySelector('[aria-current="date"]')).not.toBeNull();
  expect(currentMonthCell(11).querySelector('[aria-current="date"]')).toBeNull();
});

test('N17 a failed GetSchedule shows an error and no chip', async () => {
  openSchedule([], { 'GET /api/GetSchedule': problem(500, 'Server is down.') });

  expect(await screen.findByRole('alert')).toHaveTextContent('Server is down.');
  expect(document.querySelector('.schedule-month__chip')).toBeNull();
});

// O. Entry dialog
const dialog = () => screen.getByRole('dialog');
const input = (name: string) => within(dialog()).getByLabelText(name);
const setInput = (name: string, value: string) => fireEvent.change(input(name), { target: { value } });
const save = () => act(async () => fireEvent.click(within(dialog()).getByRole('button', { name: 'Save' })));
const updates = (api: ReturnType<typeof mockApi>) => api.callsTo('UpdateSchedule');

test('O1 New entry opens 09:00 to 10:00 of the shown date and O2 the Title is "Selected" and disabled', () => {
  openSchedule();

  fireEvent.click(button('New entry'));

  expect(screen.getByRole('dialog', { name: 'New entry' })).toBeInTheDocument();
  expect(input('Start')).toHaveValue('2026-11-12T09:00');
  expect(input('End')).toHaveValue('2026-11-12T10:00');
  expect(input('Title')).toHaveValue('Selected');
  expect(input('Title')).toBeDisabled();
});

test('O3 a new entry is saved in UTC without an id and O7 the dialog closes and the window shows', async () => {
  const api = openSchedule();
  fireEvent.click(button('New entry'));
  api.set('GET /api/GetSchedule', { body: [WINDOW_ONE] });

  await save();

  expect(updates(api)[0].body).toEqual({ startDate: '2026-11-12T06:00:00.000Z', endDate: '2026-11-12T07:00:00.000Z' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(await screen.findByRole('button', { name: 'Edit entry at 09:00' })).toBeInTheDocument();
});

test('O4 a chip opens Edit entry with its local times and O5 saves with its id', async () => {
  const api = openSchedule([WINDOW_ONE]);
  fireEvent.click(await screen.findByRole('button', { name: 'Edit entry at 09:00' }));

  expect(screen.getByRole('dialog', { name: 'Edit entry' })).toBeInTheDocument();
  expect(input('Start')).toHaveValue('2026-11-12T09:00');
  expect(input('End')).toHaveValue('2026-11-12T11:00');
  setInput('End', '2026-11-12T12:30');
  await save();

  expect(updates(api)[0].body).toEqual({
    id: 'w1',
    startDate: '2026-11-12T06:00:00.000Z',
    endDate: '2026-11-12T09:30:00.000Z',
  });
});

test('O6 an end that is not later than the start shows the rule and calls nothing', async () => {
  const api = openSchedule();
  fireEvent.click(button('New entry'));
  setInput('End', '2026-11-12T09:00');

  await save();

  expect(within(dialog()).getByRole('alert')).toHaveTextContent('The end must be later than the start.');
  expect(updates(api)).toHaveLength(0);
});

test('O8 a 409 answer keeps the dialog and explains the overlap', async () => {
  openSchedule([], { 'POST /api/UpdateSchedule': problem(409, 'Overlap.') });
  fireEvent.click(button('New entry'));

  await save();

  expect(within(dialog()).getByRole('alert')).toHaveTextContent('This Notification Window overlaps another one.');
});

test('O9 another failure keeps the dialog with an error', async () => {
  openSchedule([], { 'POST /api/UpdateSchedule': problem(400, 'The start is not a date-time.') });
  fireEvent.click(button('New entry'));

  await save();

  expect(within(dialog()).getByRole('alert')).toHaveTextContent('The start is not a date-time.');
});

test('O10 Edit entry has Delete and O11 New entry has none', async () => {
  openSchedule([WINDOW_ONE]);

  fireEvent.click(button('New entry'));
  expect(within(dialog()).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  fireEvent.click(within(dialog()).getByRole('button', { name: 'Cancel' }));

  fireEvent.click(await screen.findByRole('button', { name: 'Edit entry at 09:00' }));
  expect(within(dialog()).getByRole('button', { name: 'Delete' })).toBeInTheDocument();
});

test('O12 Delete calls DeleteSchedule with the id and O13 the chip is gone', async () => {
  const api = openSchedule([WINDOW_ONE]);
  fireEvent.click(await screen.findByRole('button', { name: 'Edit entry at 09:00' }));
  api.set('GET /api/GetSchedule', { body: [] });

  await act(async () => fireEvent.click(within(dialog()).getByRole('button', { name: 'Delete' })));

  expect(api.callsTo('DeleteSchedule')[0].url.searchParams.get('id')).toBe('w1');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Edit entry at 09:00' })).not.toBeInTheDocument());
});

test('O14 a failed delete keeps the dialog with an error', async () => {
  openSchedule([WINDOW_ONE], { 'DELETE /api/DeleteSchedule': problem(404, 'The Notification Window was not found.') });
  fireEvent.click(await screen.findByRole('button', { name: 'Edit entry at 09:00' }));

  await act(async () => fireEvent.click(within(dialog()).getByRole('button', { name: 'Delete' })));

  expect(within(dialog()).getByRole('alert')).toHaveTextContent('The Notification Window was not found.');
});

test('O15 Cancel, the backdrop and Escape close the dialog without a call', () => {
  const api = openSchedule();

  fireEvent.click(button('New entry'));
  fireEvent.click(within(dialog()).getByRole('button', { name: 'Cancel' }));
  fireEvent.click(button('New entry'));
  fireEvent.click(button('Close dialog'));
  fireEvent.click(button('New entry'));
  fireEvent.keyDown(document, { key: 'Escape' });

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(updates(api)).toHaveLength(0);
});

test('O16 a second click while saving sends nothing', async () => {
  const pending = deferred();
  const api = openSchedule([], { 'POST /api/UpdateSchedule': () => pending.promise });
  fireEvent.click(button('New entry'));
  const saveButton = within(dialog()).getByRole('button', { name: 'Save' });

  fireEvent.click(saveButton);
  fireEvent.click(saveButton);
  await act(async () => pending.resolve({ body: { id: 'new' } }));

  expect(updates(api)).toHaveLength(1);
});
