// Phase 5a section I: the Word Content from the RAG engine on the Flashcard.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import { mockApi, problem } from '../test/api_mock';
import { WORD_ONE_ID, WORD_TWO_ID, cardWord } from '../test/data';
import { renderApp } from '../test/render_app';

const NO_CONTENT = { status: 204 };
const UNAVAILABLE = 'Content is not available.';

const STORY = JSON.stringify({
  method: 'story',
  title: 'The mayfly',
  content: 'It lives <b>one</b> day.',
  source_reference: 'Notion / Diary',
});
const PHOTO = JSON.stringify({ method: 'photo', image_url: 'https://images.test/mayfly.jpg' });
const MUSIC = JSON.stringify({
  method: 'music',
  song_title: 'Yesterday',
  artist: 'The Beatles',
  song_url: 'https://music.test/yesterday',
  lyrics_excerpt: 'All my troubles seemed so far away',
});

const WITHOUT_CONTENT = [
  cardWord(WORD_ONE_ID, 'Ephemeral', { content: null }),
  cardWord(WORD_TWO_ID, 'Serendipity', { content: '' }),
];

const openActive = (cards = WITHOUT_CONTENT, routes = {}) => {
  const api = mockApi({
    'GET /api/GetWordsByActive': { body: cards },
    'POST /api/UpdateWordKnownStatus': NO_CONTENT,
    'POST /api/UpdateWordContent': NO_CONTENT,
    ...routes,
  });
  renderApp('/active');

  return api;
};

/** Opens the back side of a single card that already has this stored content. */
const backWith = async (content: string) => {
  openActive([cardWord(WORD_ONE_ID, 'Ephemeral', { content })]);
  await screen.findByRole('heading', { level: 1, name: 'Ephemeral' });
  fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
  await screen.findByRole('heading', { level: 2, name: 'Ephemeral translation' });
};

test('5a I1 cards with empty Content call POST /GetWordContent once with name and translation', async () => {
  const api = openActive(WITHOUT_CONTENT, { 'POST /GetWordContent': { body: [] } });
  await waitFor(() => expect(api.callsTo('GetWordContent')).toHaveLength(1));

  expect(api.callsTo('GetWordContent')[0].method).toBe('POST');
  expect(api.callsTo('GetWordContent')[0].body).toEqual({
    words: [
      { name: 'Ephemeral', translation: 'Ephemeral translation' },
      { name: 'Serendipity', translation: 'Serendipity translation' },
    ],
  });
});

test('5a I3 a 503 from GetWordContent makes the waiting cards say "Content is not available."', async () => {
  openActive(WITHOUT_CONTENT, { 'POST /GetWordContent': problem(503, 'Not ready.') });
  await screen.findByRole('heading', { level: 1, name: 'Ephemeral' });

  fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
  expect(await screen.findByText(UNAVAILABLE)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next word' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Yes' }));

  expect(await screen.findByText(UNAVAILABLE)).toBeInTheDocument();
  expect(screen.queryByText('Not ready.')).not.toBeInTheDocument();
});

test('5a I4 a returned content JSON is stored by UpdateWordContent as the same string', async () => {
  const api = openActive(WITHOUT_CONTENT, { 'POST /GetWordContent': { body: [{ name: 'Serendipity', content: MUSIC }] } });
  await waitFor(() => expect(api.callsTo('UpdateWordContent')).toHaveLength(1));

  expect(api.callsTo('UpdateWordContent')[0].body).toEqual({ id: WORD_TWO_ID, content: MUSIC });
});

test('5a I5 a text method shows its title and content as plain text', async () => {
  await backWith(STORY);

  expect(screen.getByRole('heading', { level: 3, name: 'The mayfly' })).toBeInTheDocument();
  expect(screen.getByText('It lives <b>one</b> day.')).toBeInTheDocument();
  expect(document.querySelector('.flashcard-back__content b')).toBeNull();
  expect(screen.queryByText(/"method"/)).not.toBeInTheDocument();
});

test('5a I6 a photo shows the image with the Word name as its alt text', async () => {
  await backWith(PHOTO);

  const image = screen.getByRole('img', { name: 'Ephemeral' });
  expect(image).toHaveAttribute('src', 'https://images.test/mayfly.jpg');
  expect(image).toHaveAttribute('loading', 'lazy');
});

test('5a I7 music shows the song title, artist, the lyric excerpt in quotes and a link to the song', async () => {
  await backWith(MUSIC);

  expect(screen.getByText('Yesterday')).toBeInTheDocument();
  expect(screen.getByText('The Beatles')).toBeInTheDocument();
  expect(screen.getByText('All my troubles seemed so far away').tagName).toBe('Q');
  expect(screen.getByRole('link', { name: 'Listen' })).toHaveAttribute('href', 'https://music.test/yesterday');
});

test('5a I8 the music link opens in a new tab with rel "noopener noreferrer"', async () => {
  await backWith(MUSIC);

  const link = screen.getByRole('link', { name: 'Listen' });
  expect(link).toHaveAttribute('target', '_blank');
  expect(link).toHaveAttribute('rel', 'noopener noreferrer');
});

test.each([
  ['image_url', JSON.stringify({ method: 'photo', image_url: 'http://images.test/mayfly.jpg' })],
  ['song_url', JSON.stringify({ ...JSON.parse(MUSIC), song_url: 'javascript:alert(1)' })],
])('5a I9 a %s that is not https creates no image or link', async (_, content) => {
  await backWith(content);

  expect(screen.getByText(UNAVAILABLE)).toBeInTheDocument();
  expect(document.querySelector('.flashcard-back__content img')).toBeNull();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

test('5a I10 an old plain-text Content is shown as a story text', async () => {
  await backWith('A story about a mayfly.');

  expect(screen.getByText('A story about a mayfly.')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();
});

test.each([
  ['an unknown method', JSON.stringify({ method: 'poem', title: 'T', content: 'C' })],
  ['missing fields', JSON.stringify({ method: 'music', song_title: 'Yesterday' })],
])('5a I11 content JSON with %s shows "Content is not available."', async (_, content) => {
  await backWith(content);

  expect(screen.getByText(UNAVAILABLE)).toBeInTheDocument();
});

test('5a I12 a picture that fails to load is replaced by "Content is not available."', async () => {
  await backWith(PHOTO);

  fireEvent.error(screen.getByRole('img', { name: 'Ephemeral' }));

  expect(await screen.findByText(UNAVAILABLE)).toBeInTheDocument();
  expect(screen.queryByRole('img', { name: 'Ephemeral' })).not.toBeInTheDocument();
});

test('5a I6 a photo returned by the engine is shown after it arrives', async () => {
  openActive([WITHOUT_CONTENT[0]], { 'POST /GetWordContent': { body: [{ name: 'Ephemeral', content: PHOTO }] } });
  await screen.findByRole('heading', { level: 1, name: 'Ephemeral' });

  fireEvent.click(screen.getByRole('button', { name: 'Yes' }));

  expect(await screen.findByRole('img', { name: 'Ephemeral' })).toHaveAttribute('src', 'https://images.test/mayfly.jpg');
});
