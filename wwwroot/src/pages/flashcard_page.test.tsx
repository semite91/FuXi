// Sections D to I: the Flashcard carousel.
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { deferred, mockApi, networkFailure, problem, type Answer } from '../test/api_mock';
import { THREE_CARDS, TWO_CARDS, WORD_ONE_ID, WORD_TWO_ID, cardWord } from '../test/data';
import { renderApp } from '../test/render_app';

const NO_CONTENT = { status: 204 };
const HISTORY = [
  { isKnown: true, date: '2026-10-30T21:30:00Z' },
  { isKnown: false, date: '2026-10-28T08:00:00Z' },
];

const answerRoutes = {
  'POST /api/UpdateWordKnownStatus': NO_CONTENT,
  'POST /api/UpdateIsReinforcement': NO_CONTENT,
  'POST /api/UpdateWordContent': NO_CONTENT,
  'GET /api/GetWordHistory': { body: HISTORY },
};

const openActive = (cards = TWO_CARDS, routes = {}) => {
  const api = mockApi({ 'GET /api/GetWordsByActive': { body: cards }, ...answerRoutes, ...routes });
  renderApp('/active');

  return api;
};

const word = (name: string) => screen.findByRole('heading', { level: 1, name });
const translation = (text: string) => screen.findByRole('heading', { level: 2, name: text });
const button = (name: string) => screen.getByRole('button', { name });
const answerYes = () => fireEvent.click(button('Yes'));

const toBack = async (cards = TWO_CARDS, routes = {}) => {
  const api = openActive(cards, routes);
  await word(cards[0].name);
  answerYes();
  await translation(cards[0].translation);

  return api;
};

// D. Data source
test('D1 /flashcard?wordIds calls GetCardWords once with the same value', async () => {
  const api = mockApi({ 'GET /api/GetCardWords': { body: TWO_CARDS } });
  renderApp(`/flashcard?wordIds=${WORD_ONE_ID},${WORD_TWO_ID}`);
  await word('Ephemeral');

  expect(api.callsTo('GetCardWords')).toHaveLength(1);
  expect(api.callsTo('GetCardWords')[0].url.searchParams.get('wordIds')).toBe(`${WORD_ONE_ID},${WORD_TWO_ID}`);
  expect(api.callsTo('GetWordsByActive')).toHaveLength(0);
});

test('D2 /flashcard without wordIds calls GetWordsByActive and not GetCardWords', async () => {
  const api = mockApi({ 'GET /api/GetWordsByActive': { body: TWO_CARDS } });
  renderApp('/flashcard');
  await word('Ephemeral');

  expect(api.callsTo('GetWordsByActive')).toHaveLength(1);
  expect(api.callsTo('GetCardWords')).toHaveLength(0);
});

test('D3 /active calls GetWordsByActive once and D4 shows the first front side', async () => {
  const api = openActive();

  expect(await word('Ephemeral')).toBeInTheDocument();
  expect(api.callsTo('GetWordsByActive')).toHaveLength(1);
  expect(screen.getByText('Do you know this word?')).toBeInTheDocument();
});

test('D5 an empty result shows the encouragement as a status', async () => {
  openActive([]);

  const message = await screen.findByText('Keep working like this; there are no words to review at the moment.');
  expect(message).toHaveAttribute('role', 'status');
});

test('D6 a pending request shows a loading state and no card', async () => {
  const pending = deferred();
  mockApi({ 'GET /api/GetWordsByActive': () => pending.promise });
  renderApp('/active');

  expect(screen.getByRole('status')).toHaveTextContent('Loading');
  expect(screen.queryByText('Do you know this word?')).not.toBeInTheDocument();
  await act(async () => pending.resolve({ body: [] }));
});

test('D7 a failed request shows an error and no card', async () => {
  mockApi({ 'GET /api/GetWordsByActive': problem(500, 'Server is down.') });
  renderApp('/active');

  expect(await screen.findByRole('alert')).toHaveTextContent('Server is down.');
  expect(screen.queryByText('Do you know this word?')).not.toBeInTheDocument();
});

// E. Front side
test('E1 the front side has the question, the Word, No and Yes; E2 no translation or content', async () => {
  openActive();
  await word('Ephemeral');

  expect(screen.getByText('Do you know this word?')).toBeInTheDocument();
  expect(button('No')).toBeInTheDocument();
  expect(button('Yes')).toBeInTheDocument();
  expect(screen.queryByText('Ephemeral translation')).not.toBeInTheDocument();
  expect(screen.queryByText('Ephemeral content')).not.toBeInTheDocument();
});

test.each([
  ['E3', 'Yes', true],
  ['E4', 'No', false],
])('%s %s sends isKnown %s and E5 the card turns', async (_, label, isKnown) => {
  const api = openActive();
  await word('Ephemeral');

  fireEvent.click(button(label));

  expect(await translation('Ephemeral translation')).toBeInTheDocument();
  expect(api.callsTo('UpdateWordKnownStatus')).toHaveLength(1);
  expect(api.callsTo('UpdateWordKnownStatus')[0].body).toEqual({ wordId: WORD_ONE_ID, isKnown });
});

test('E6 a second click while the answer is pending sends nothing', async () => {
  const pending = deferred();
  const api = openActive(TWO_CARDS, { 'POST /api/UpdateWordKnownStatus': () => pending.promise });
  await word('Ephemeral');

  answerYes();
  answerYes();
  fireEvent.click(button('No'));
  await act(async () => pending.resolve(NO_CONTENT));

  expect(api.callsTo('UpdateWordKnownStatus')).toHaveLength(1);
});

test('E7 a failed answer keeps the front side and shows an error', async () => {
  openActive(TWO_CARDS, { 'POST /api/UpdateWordKnownStatus': problem(404, 'The Word is not in the Rotation.') });
  await word('Ephemeral');

  answerYes();

  expect(await screen.findByRole('alert')).toHaveTextContent('The Word is not in the Rotation.');
  expect(button('Yes')).toBeInTheDocument();
});

// F. Back side
test('F1 the translation is the large text and F2 the content is plain text', async () => {
  await toBack();

  expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Ephemeral translation');
  expect(screen.getByText('Ephemeral content')).toBeInTheDocument();
});

test('F3 HTML in the content is shown as text', async () => {
  const html = '<img src=x onerror=alert(1)><b>bold</b>';
  await toBack([cardWord(WORD_ONE_ID, 'Ephemeral', { content: html })]);

  expect(screen.getByText(html)).toBeInTheDocument();
  expect(document.querySelector('img[src="x"]')).toBeNull();
  expect(document.querySelector('b')).toBeNull();
});

test('F4 one dot per card, the current one is marked', async () => {
  await toBack(THREE_CARDS);

  const dots = document.querySelectorAll('.flashcard-back__dot');
  expect(dots).toHaveLength(3);
  expect([...dots].map((dot) => dot.getAttribute('data-current'))).toEqual(['true', 'false', 'false']);
});

test('F5 the back side has no image area, link or caption line', async () => {
  await toBack();

  expect(screen.queryByRole('img', { name: 'Image placeholder' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

test('F6 the reinforcement button is named and F7 its tooltip shows on hover and focus', async () => {
  await toBack();
  const reinforcement = button('Is reinforcement');

  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  fireEvent.mouseEnter(reinforcement.parentElement!);
  expect(screen.getByRole('tooltip')).toHaveTextContent('Is reinforcement');
  fireEvent.mouseLeave(reinforcement.parentElement!);
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  fireEvent.focus(reinforcement);
  expect(screen.getByRole('tooltip')).toHaveTextContent('Is reinforcement');
});

test('F8 the reinforcement button sends true and F9 shows the next front side', async () => {
  const api = await toBack();

  fireEvent.click(button('Is reinforcement'));

  expect(await word('Serendipity')).toBeInTheDocument();
  expect(api.callsTo('UpdateIsReinforcement')[0].body).toEqual({ wordId: WORD_ONE_ID, isReinforcement: true });
});

test('F10 reinforcing the last card shows the Done screen', async () => {
  await toBack([TWO_CARDS[0]]);

  fireEvent.click(button('Is reinforcement'));

  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Done'));
  expect(screen.queryByText('Ephemeral translation')).not.toBeInTheDocument();
});

test('F11 a failed reinforcement keeps the card and shows an error', async () => {
  await toBack(TWO_CARDS, { 'POST /api/UpdateIsReinforcement': networkFailure });

  fireEvent.click(button('Is reinforcement'));

  expect(await screen.findByRole('alert')).toHaveTextContent('The API cannot be reached.');
  expect(screen.getByText('Ephemeral translation')).toBeInTheDocument();
});

// G. Word History
const historyToggle = () => button('History');

test('G1 the History toggle starts closed', async () => {
  await toBack();

  expect(historyToggle()).toHaveAttribute('aria-expanded', 'false');
});

test('G2 the first opening calls GetWordHistory, G3 shows the rows, G4 Yes and No, G5 local dates', async () => {
  const api = await toBack();

  fireEvent.click(historyToggle());
  const table = await screen.findByRole('table');

  expect(api.callsTo('GetWordHistory')[0].url.searchParams.get('wordId')).toBe(WORD_ONE_ID);
  expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Is It known', 'Date']);
  const rows = within(table).getAllByRole('row').slice(1);
  expect(rows.map((row) => row.textContent)).toEqual(['Yes31.10.2026', 'No28.10.2026']);
});

test('G6 a second click hides the list and G7 opening again does not call the API', async () => {
  const api = await toBack();

  fireEvent.click(historyToggle());
  await screen.findByRole('table');
  fireEvent.click(historyToggle());
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(historyToggle()).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(historyToggle());

  expect(await screen.findByRole('table')).toBeInTheDocument();
  expect(api.callsTo('GetWordHistory')).toHaveLength(1);
});

test('G8 the history is loaded after the answer, so the new answer is part of it', async () => {
  const api = await toBack();
  const answerIndex = api.calls.findIndex((call) => call.path.endsWith('UpdateWordKnownStatus'));

  fireEvent.click(historyToggle());
  await screen.findByRole('table');

  const historyIndex = api.calls.findIndex((call) => call.path.endsWith('GetWordHistory'));
  expect(historyIndex).toBeGreaterThan(answerIndex);
});

test('G9 a Word without history shows an empty list', async () => {
  await toBack(TWO_CARDS, { 'GET /api/GetWordHistory': { body: [] } });

  fireEvent.click(historyToggle());

  const table = await screen.findByRole('table');
  expect(within(table).getAllByRole('row')).toHaveLength(1);
});

test('G10 a failed history shows an error and the next opening tries again', async () => {
  const api = await toBack(TWO_CARDS, { 'GET /api/GetWordHistory': problem(500, 'Failed.') });

  fireEvent.click(historyToggle());
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  fireEvent.click(historyToggle());
  api.set('GET /api/GetWordHistory', { body: HISTORY });
  fireEvent.click(historyToggle());

  expect(await screen.findByRole('table')).toBeInTheDocument();
  expect(api.callsTo('GetWordHistory')).toHaveLength(2);
});

// H. Moving between cards
test('H1 the front side has no arrows', async () => {
  openActive();
  await word('Ephemeral');

  expect(screen.queryByRole('button', { name: 'Previous word' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Next word' })).not.toBeInTheDocument();
});

test('H2 next shows the next front side and H3 the first back side has no previous arrow', async () => {
  await toBack();

  expect(screen.queryByRole('button', { name: 'Previous word' })).not.toBeInTheDocument();
  fireEvent.click(button('Next word'));

  expect(await word('Serendipity')).toBeInTheDocument();
});

test('H4 previous shows the back side again, H5 without Yes and No, H6 next returns to the side it had', async () => {
  await toBack(THREE_CARDS);
  fireEvent.click(button('Next word'));
  await word('Serendipity');
  answerYes();
  await translation('Serendipity translation');

  fireEvent.click(button('Previous word'));
  expect(await translation('Ephemeral translation')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Yes' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'No' })).not.toBeInTheDocument();

  fireEvent.click(button('Next word'));
  expect(await translation('Serendipity translation')).toBeInTheDocument();
  fireEvent.click(button('Next word'));
  expect(await word('Ubiquitous')).toBeInTheDocument();
});

test('H7 the last back side has no next arrow and a Done button; H8 Done shows the Done screen', async () => {
  await toBack([TWO_CARDS[0]]);

  expect(screen.queryByRole('button', { name: 'Next word' })).not.toBeInTheDocument();
  fireEvent.click(button('Done'));

  expect(screen.getByRole('status')).toHaveTextContent('Done');
  expect(screen.queryByText('Ephemeral translation')).not.toBeInTheDocument();
});

test('H9 moving sends no answer', async () => {
  const api = await toBack(THREE_CARDS);

  fireEvent.click(button('Next word'));
  await word('Serendipity');

  expect(api.callsTo('UpdateWordKnownStatus')).toHaveLength(1);
});

// I. Word Content flow
const WITHOUT_CONTENT = [
  cardWord(WORD_ONE_ID, 'Ephemeral', { content: null }),
  cardWord(WORD_TWO_ID, 'Serendipity', { content: '   ' }),
];

test('I1 Words without content are asked for once, joined with a comma; I3 spaces count as empty', async () => {
  const api = openActive(WITHOUT_CONTENT, { 'GET /GetWordContent': { body: [] } });
  await word('Ephemeral');
  await waitFor(() => expect(api.callsTo('GetWordContent')).toHaveLength(1));

  expect(api.callsTo('GetWordContent')[0].url.searchParams.get('words')).toBe('Ephemeral,Serendipity');
});

test('I2 cards that all have content do not call GetWordContent', async () => {
  const api = openActive();
  await word('Ephemeral');

  expect(api.callsTo('GetWordContent')).toHaveLength(0);
});

test('I4 generated content is set by Name, I5 stored once per Word, I6 a missing Word gets none', async () => {
  const api = openActive(WITHOUT_CONTENT, {
    'GET /GetWordContent': { body: [{ name: 'Ephemeral', content: 'A story about a mayfly.' }] },
  });
  await word('Ephemeral');
  await waitFor(() => expect(api.callsTo('UpdateWordContent')).toHaveLength(1));

  expect(api.callsTo('UpdateWordContent')[0].body).toEqual({ id: WORD_ONE_ID, content: 'A story about a mayfly.' });
  answerYes();
  expect(await screen.findByText('A story about a mayfly.')).toBeInTheDocument();
  fireEvent.click(button('Next word'));
  answerYes();
  expect(await screen.findByText('Content is not available.')).toBeInTheDocument();
});

test('I7 a pending content shows a skeleton and I8 the content replaces it; I11 cards are not blocked', async () => {
  const pending = deferred<Answer>();
  openActive(WITHOUT_CONTENT, { 'GET /GetWordContent': () => pending.promise });
  await word('Ephemeral');

  answerYes();
  await translation('Ephemeral translation');
  expect(screen.getByText('Loading content')).toBeInTheDocument();
  expect(document.querySelector('.skeleton')).not.toBeNull();

  await act(async () => pending.resolve({ body: [{ name: 'Ephemeral', content: 'Arrived.' }] }));

  expect(await screen.findByText('Arrived.')).toBeInTheDocument();
  expect(document.querySelector('.skeleton')).toBeNull();
});

test('I9 a failed GetWordContent shows that content is not available and the card still works', async () => {
  openActive(WITHOUT_CONTENT, { 'GET /GetWordContent': networkFailure });
  await word('Ephemeral');

  answerYes();

  expect(await screen.findByText('Content is not available.')).toBeInTheDocument();
  fireEvent.click(button('Next word'));
  expect(await word('Serendipity')).toBeInTheDocument();
});

test('I10 a failed UpdateWordContent keeps the generated content on the card', async () => {
  openActive([WITHOUT_CONTENT[0]], {
    'GET /GetWordContent': { body: [{ name: 'Ephemeral', content: 'Kept.' }] },
    'POST /api/UpdateWordContent': problem(500, 'Failed.'),
  });
  await word('Ephemeral');

  answerYes();

  expect(await screen.findByText('Kept.')).toBeInTheDocument();
});
