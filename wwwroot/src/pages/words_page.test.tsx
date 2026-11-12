// Section J: the Words page.
import { act, fireEvent, screen, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { deferred, mockApi, problem, type RecordedCall } from '../test/api_mock';
import { WORD_ONE_ID, WORD_THREE_ID, WORD_TWO_ID, filteredWord } from '../test/data';
import { renderApp } from '../test/render_app';

const WORDS = [
  filteredWord(WORD_ONE_ID, 'banana', {
    isKnown: true,
    knownCount: 7,
    shownCount: 12,
    isRotated: true,
    counter: 3,
    lastShownDate: '2026-10-30T22:00:00Z',
  }),
  filteredWord(WORD_TWO_ID, 'Apple', { isReinforcement: true, knownCount: 1, shownCount: 5 }),
  filteredWord(WORD_THREE_ID, 'cherry', { knownCount: 4, shownCount: 9 }),
];

const openWords = (routes = {}) => {
  const api = mockApi({ 'GET /api/GetWordsByFilter': { body: WORDS }, ...routes });
  renderApp('/words');

  return api;
};

const button = (name: string) => screen.getByRole('button', { name });
const openFilters = () => fireEvent.click(button('Open filters'));
const field = (label: string) => screen.getByLabelText(label);
const setField = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });
const apply = () => fireEvent.click(button('Apply'));
const table = () => screen.getByRole('table', { name: 'Words' });
const bodyRows = () => within(table()).getAllByRole('row').slice(1);
const names = () => bodyRows().map((row) => within(row).getAllByRole('cell')[0].textContent);

const filterBy = async (label: string, value: string) => {
  openFilters();
  setField(label, value);
  apply();
  await screen.findByRole('button', { name: 'banana' });
};

test('J1 the page opens without an API call and without rows', () => {
  const api = openWords();

  expect(api.calls).toHaveLength(0);
  expect(bodyRows()).toHaveLength(0);
});

test('J2 the table has the seven headers', () => {
  openWords();

  const headers = within(table()).getAllByRole('columnheader').map((header) => header.textContent);
  expect(headers).toEqual([
    'Name',
    'Is known',
    'Is reinforcement',
    'Known count',
    'Shown count',
    'Recursive known count',
    'Last shown date',
  ]);
});

test('J3 the filter button opens the panel with four fields and J4 the selects offer All, Yes, No', () => {
  openWords();
  openFilters();

  expect(screen.getByRole('dialog', { name: 'Filters' })).toBeInTheDocument();
  expect(field('Name')).toHaveAttribute('type', 'text');
  ['Is reinforcement', 'Is known', 'Is active word'].forEach((label) => {
    const options = within(field(label)).getAllByRole('option').map((option) => option.textContent);
    expect(options).toEqual(['All', 'Yes', 'No']);
  });
});

test('J5 Apply calls GetWordsByFilter once and closes the panel', async () => {
  const api = openWords();

  await filterBy('Is known', 'yes');

  expect(api.callsTo('GetWordsByFilter')).toHaveLength(1);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

test('J6 "Is active word" Yes is sent as isRotated=true and J7 fields set to All are left out', async () => {
  const api = openWords();

  await filterBy('Is active word', 'yes');

  const query = api.callsTo('GetWordsByFilter')[0].url.searchParams;
  expect([...query.keys()]).toEqual(['isRotated']);
  expect(query.get('isRotated')).toBe('true');
});

test('J8 the Name is trimmed', async () => {
  const api = openWords();

  await filterBy('Name', '  run  ');

  expect(api.callsTo('GetWordsByFilter')[0].url.searchParams.get('name')).toBe('run');
});

test('J9 an empty filter calls nothing', () => {
  const api = openWords();
  openFilters();
  setField('Name', '   ');

  apply();

  expect(api.calls).toHaveLength(0);
  expect(bodyRows()).toHaveLength(0);
});

test('J10 Clear empties every field and calls nothing', () => {
  const api = openWords();
  openFilters();
  setField('Name', 'run');
  setField('Is known', 'no');

  fireEvent.click(button('Clear'));

  expect(field('Name')).toHaveValue('');
  expect(field('Is known')).toHaveValue('');
  expect(api.calls).toHaveLength(0);
});

test('J11 closing the panel without Apply keeps the applied filter and the rows', async () => {
  openWords();
  await filterBy('Is known', 'yes');

  openFilters();
  setField('Is known', 'no');
  fireEvent.click(screen.getAllByRole('button', { name: 'Close filters' })[1]);
  openFilters();

  expect(field('Is known')).toHaveValue('yes');
  expect(bodyRows()).toHaveLength(3);
});

test('J12 a pending call shows skeleton rows, "Loading words" and aria-busy', async () => {
  const pending = deferred();
  openWords({ 'GET /api/GetWordsByFilter': () => pending.promise });
  openFilters();
  setField('Name', 'a');
  apply();

  expect(table()).toHaveAttribute('aria-busy', 'true');
  expect(screen.getByText('Loading words')).toBeInTheDocument();
  expect(document.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
  await act(async () => pending.resolve({ body: [] }));
  expect(table()).toHaveAttribute('aria-busy', 'false');
});

test('J13 one row per Word, J14 Counter or "-", J15 dd.MM.yyyy or "-"', async () => {
  openWords();
  await filterBy('Name', 'a');

  expect(bodyRows()).toHaveLength(3);
  const cells = (index: number) => within(bodyRows()[index]).getAllByRole('cell').map((cell) => cell.textContent);
  expect(cells(0)).toEqual(['banana', 'Yes', 'No', '7', '12', '3', '31.10.2026']);
  expect(cells(1)).toEqual(['Apple', 'No', 'Yes', '1', '5', '-', '-']);
});

test('J16 an empty result shows "No words match these filters."', async () => {
  openWords({ 'GET /api/GetWordsByFilter': { body: [] } });
  openFilters();
  setField('Name', 'zzz');
  apply();

  expect(await screen.findByText('No words match these filters.')).toBeInTheDocument();
});

test('J17 a sort button sorts ascending without a call and J18 again sorts descending', async () => {
  const api = openWords();
  await filterBy('Name', 'a');

  fireEvent.click(button('Sort by Name'));
  expect(names()).toEqual(['Apple', 'banana', 'cherry']);
  fireEvent.click(button('Sort by Name'));
  expect(names()).toEqual(['cherry', 'banana', 'Apple']);
  expect(screen.getByRole('columnheader', { name: /^Name/ })).toHaveAttribute('aria-sort', 'descending');

  fireEvent.click(button('Sort by Shown count'));
  expect(names()).toEqual(['Apple', 'cherry', 'banana']);
  expect(api.callsTo('GetWordsByFilter')).toHaveLength(1);
});

test('J19 a click on a Name opens its History dialog and J20 Escape, backdrop and close button close it', async () => {
  const api = openWords({ 'GET /api/GetWordHistory': { body: [{ isKnown: true, date: '2026-10-30T10:00:00Z' }] } });
  await filterBy('Name', 'a');

  fireEvent.click(button('banana'));
  const dialog = await screen.findByRole('dialog', { name: 'banana' });
  expect(await within(dialog).findByText('30.10.2026')).toBeInTheDocument();
  expect(api.callsTo('GetWordHistory')[0].url.searchParams.get('wordId')).toBe(WORD_ONE_ID);

  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

  fireEvent.click(button('banana'));
  fireEvent.click(await screen.findByRole('button', { name: 'Close dialog' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

  fireEvent.click(button('banana'));
  fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

test('J21 a failed call shows an error and no row', async () => {
  openWords({ 'GET /api/GetWordsByFilter': problem(400, 'IsKnown is not a boolean.') });
  openFilters();
  setField('Is known', 'yes');
  apply();

  expect(await screen.findByRole('alert')).toHaveTextContent('IsKnown is not a boolean.');
  expect(bodyRows()).toHaveLength(0);
});

test('review: a late history answer does not land on another Word', async () => {
  const late = deferred();
  const api = openWords({
    'GET /api/GetWordHistory': (call: RecordedCall) =>
      call.url.searchParams.get('wordId') === WORD_ONE_ID
        ? late.promise
        : { body: [{ isKnown: false, date: '2026-10-01T10:00:00Z' }] },
  });
  await filterBy('Name', 'a');

  fireEvent.click(button('banana'));
  fireEvent.keyDown(document, { key: 'Escape' });
  fireEvent.click(button('Apple'));
  const dialog = await screen.findByRole('dialog', { name: 'Apple' });
  await within(dialog).findByText('01.10.2026');
  await act(async () => late.resolve({ body: [{ isKnown: true, date: '2026-10-30T10:00:00Z' }] }));

  expect(within(dialog).queryByText('30.10.2026')).not.toBeInTheDocument();
  expect(within(dialog).getByText('01.10.2026')).toBeInTheDocument();
  expect(api.callsTo('GetWordHistory')).toHaveLength(2);
});

test('review: an older filter answer does not replace a newer one', async () => {
  const late = deferred();
  openWords({
    'GET /api/GetWordsByFilter': (call: RecordedCall) =>
      call.url.searchParams.get('isKnown') === 'true' ? late.promise : { body: [WORDS[1]] },
  });
  openFilters();
  setField('Is known', 'yes');
  apply();
  openFilters();
  setField('Is known', 'no');
  apply();
  await screen.findByRole('button', { name: 'Apple' });

  await act(async () => late.resolve({ body: [WORDS[0]] }));

  expect(names()).toEqual(['Apple']);
});
