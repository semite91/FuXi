// Phase 5a section I: the Word Content from the RAG engine on the Flashcard.
import { act, cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import { deferred, mockApi, problem, type Answer, type RecordedCall } from '../test/api_mock';
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

test('5a I1 two cards with empty Content are one group: POST /GetWordContent is called once with name and translation', async () => {
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
  const api = openActive(WITHOUT_CONTENT, { 'POST /GetWordContent': { body: [{ name: 'Serendipity', translation: 'Serendipity translation', content: MUSIC }] } });
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

test('5a I7 music with a lyric excerpt shows the song title, artist, the lyric excerpt in quotes and a link to the song', async () => {
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
  openActive([WITHOUT_CONTENT[0]], { 'POST /GetWordContent': { body: [{ name: 'Ephemeral', translation: 'Ephemeral translation', content: PHOTO }] } });
  await screen.findByRole('heading', { level: 1, name: 'Ephemeral' });

  fireEvent.click(screen.getByRole('button', { name: 'Yes' }));

  expect(await screen.findByRole('img', { name: 'Ephemeral' })).toHaveAttribute('src', 'https://images.test/mayfly.jpg');
});

const MUSIC_WITHOUT_EXCERPT = JSON.stringify({ ...JSON.parse(MUSIC), lyrics_excerpt: ' ' });

test('5a I19 music without a lyric excerpt shows the title, artist and link without a quote', async () => {
  await backWith(MUSIC_WITHOUT_EXCERPT);

  expect(screen.getByText('Yesterday')).toBeInTheDocument();
  expect(screen.getByText('The Beatles')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Listen' })).toHaveAttribute('href', 'https://music.test/yesterday');
  expect(document.querySelector('.flashcard-back__content q')).toBeNull();
  expect(screen.queryByText(UNAVAILABLE)).not.toBeInTheDocument();
});

test('5a I18 text content with a source reference shows the source as a caption', async () => {
  await backWith(STORY);

  const caption = screen.getByText('Notion / Diary');
  expect(caption).toHaveClass('word-content-text__source');
  expect(caption.querySelector('*')).toBeNull();
});

test.each([
  ['null', null],
  ['blank', '  '],
])('5a I18 text content with a %s source reference shows no caption', async (_, source) => {
  await backWith(JSON.stringify({ ...JSON.parse(STORY), source_reference: source }));

  expect(screen.getByText('It lives <b>one</b> day.')).toBeInTheDocument();
  expect(document.querySelector('.word-content-text__source')).toBeNull();
});

const GROUP_CARD_COUNT = 12;
const nameOf = (position: number) => `Word ${position}`;
const storyOf = (name: string) => `${name} story`;
const manyCards = (count: number) =>
  Array.from({ length: count }, (_, offset) => cardWord(`id-${offset + 1}`, nameOf(offset + 1), { content: null }));
const meaningsIn = (call: RecordedCall) => (call.body as { words: { name: string; translation: string }[] }).words;
const namesIn = (call: RecordedCall) => meaningsIn(call).map((word) => word.name);
/** The engine echoes each asked name and translation with its content. */
const storiesFor = (call: RecordedCall): Answer => ({
  body: meaningsIn(call).map(({ name, translation }) => ({ name, translation, content: storyOf(name) })),
});

/** Every GetWordContent call waits until the test answers it. */
const pendingGroups = () => {
  const answers: ((answer: Answer) => void)[] = [];
  const route = () => {
    const pending = deferred<Answer>();
    answers.push(pending.resolve);

    return pending.promise;
  };

  return { answers, route };
};

/** Answers the card on the screen and moves to the next one, count times. */
const skipCards = async (count: number) => {
  for (let step = 0; step < count; step += 1) {
    fireEvent.click(await screen.findByRole('button', { name: 'Yes' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Next word' }));
  }
};

const showBack = async (name: string) => {
  await screen.findByRole('heading', { level: 1, name });
  fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
  await screen.findByRole('heading', { level: 2, name: `${name} translation` });
};

test('5a I15 given 12 cards without content, 3 requests of 5, 5 and 2 words are sent one after another', async () => {
  const groups = pendingGroups();
  const api = openActive(manyCards(GROUP_CARD_COUNT), { 'POST /GetWordContent': groups.route });
  const calls = () => api.callsTo('GetWordContent');

  await waitFor(() => expect(calls()).toHaveLength(1));
  expect(namesIn(calls()[0])).toEqual([1, 2, 3, 4, 5].map(nameOf));
  await act(async () => groups.answers[0](storiesFor(calls()[0])));

  await waitFor(() => expect(calls()).toHaveLength(2));
  expect(namesIn(calls()[1])).toEqual([6, 7, 8, 9, 10].map(nameOf));
  await act(async () => groups.answers[1](storiesFor(calls()[1])));

  await waitFor(() => expect(calls()).toHaveLength(3));
  expect(namesIn(calls()[2])).toEqual([11, 12].map(nameOf));
  await act(async () => groups.answers[2](storiesFor(calls()[2])));

  await waitFor(() => expect(api.callsTo('UpdateWordContent')).toHaveLength(GROUP_CARD_COUNT));
  expect(calls()).toHaveLength(3);
});

test('5a I15 while a group is waiting, the next group is not sent', async () => {
  const groups = pendingGroups();
  const api = openActive(manyCards(GROUP_CARD_COUNT), { 'POST /GetWordContent': groups.route });
  await waitFor(() => expect(api.callsTo('GetWordContent')).toHaveLength(1));

  await act(async () => new Promise((done) => setTimeout(done, 20)));

  expect(api.callsTo('GetWordContent')).toHaveLength(1);
});

test('5a I21 given two cards with the same name and translation, when content is asked, then the pair is sent once and both cards get the content', async () => {
  const cards = [
    cardWord(WORD_ONE_ID, 'Ephemeral', { content: null }),
    cardWord(WORD_TWO_ID, 'Ephemeral', { content: null }),
  ];
  const api = openActive(cards, { 'POST /GetWordContent': storiesFor });
  await waitFor(() => expect(api.callsTo('UpdateWordContent')).toHaveLength(2));

  expect(api.callsTo('GetWordContent')).toHaveLength(1);
  expect(meaningsIn(api.callsTo('GetWordContent')[0])).toEqual([
    { name: 'Ephemeral', translation: 'Ephemeral translation' },
  ]);
  expect(api.callsTo('UpdateWordContent').map((call) => call.body)).toEqual([
    { id: WORD_ONE_ID, content: 'Ephemeral story' },
    { id: WORD_TWO_ID, content: 'Ephemeral story' },
  ]);
  await showBack('Ephemeral');
  expect(screen.getByText('Ephemeral story')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next word' }));
  await showBack('Ephemeral');
  expect(screen.getByText('Ephemeral story')).toBeInTheDocument();
});

const BANK_MONEY = 'banka';
const BANK_RIVER = 'kıyı';
const bankStoryOf = (translation: string) => `bank as ${translation}`;

const showBankBack = async (translation: string) => {
  await screen.findByRole('heading', { level: 1, name: 'bank' });
  fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
  await screen.findByRole('heading', { level: 2, name: translation });
};

test("5a I20 given two cards named 'bank' with different translations, when content is asked, then both pairs are sent and each card gets the content of its own translation", async () => {
  const cards = [
    cardWord(WORD_ONE_ID, 'bank', { translation: BANK_MONEY, content: null }),
    cardWord(WORD_TWO_ID, 'bank', { translation: BANK_RIVER, content: null }),
  ];
  // The answer comes in reverse order, so only the name and translation can match it to a card.
  const api = openActive(cards, {
    'POST /GetWordContent': (call: RecordedCall): Answer => ({
      body: [...meaningsIn(call)].reverse().map(({ name, translation }) => ({
        name,
        translation,
        content: bankStoryOf(translation),
      })),
    }),
  });
  await waitFor(() => expect(api.callsTo('UpdateWordContent')).toHaveLength(2));

  expect(api.callsTo('GetWordContent')).toHaveLength(1);
  expect(meaningsIn(api.callsTo('GetWordContent')[0])).toEqual([
    { name: 'bank', translation: BANK_MONEY },
    { name: 'bank', translation: BANK_RIVER },
  ]);
  expect(api.callsTo('UpdateWordContent').map((call) => call.body)).toEqual([
    { id: WORD_ONE_ID, content: bankStoryOf(BANK_MONEY) },
    { id: WORD_TWO_ID, content: bankStoryOf(BANK_RIVER) },
  ]);
  await showBankBack(BANK_MONEY);
  expect(screen.getByText(bankStoryOf(BANK_MONEY))).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next word' }));
  await showBankBack(BANK_RIVER);
  expect(screen.getByText(bankStoryOf(BANK_RIVER))).toBeInTheDocument();
});

test('5a I16 a failed second group makes only its cards say "Content is not available." and the third group is asked', async () => {
  const CARD_COUNT = 11;
  const FAILED_GROUP = 2;
  let callCount = 0;
  const api = openActive(manyCards(CARD_COUNT), {
    'POST /GetWordContent': (call: RecordedCall) => {
      callCount += 1;

      return callCount === FAILED_GROUP ? problem(503, 'Not ready.') : storiesFor(call);
    },
  });

  await waitFor(() => expect(api.callsTo('GetWordContent')).toHaveLength(3));
  expect(namesIn(api.callsTo('GetWordContent')[2])).toEqual([nameOf(11)]);
  await waitFor(() => expect(api.callsTo('UpdateWordContent')).toHaveLength(6));
  expect(api.callsTo('UpdateWordContent').map((call) => (call.body as { id: string }).id)).toEqual(
    ['id-1', 'id-2', 'id-3', 'id-4', 'id-5', 'id-11'],
  );

  await showBack(nameOf(1));
  expect(screen.getByText(storyOf(nameOf(1)))).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next word' }));
  await skipCards(4);
  await showBack(nameOf(6));
  expect(screen.getByText(UNAVAILABLE)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next word' }));
  await skipCards(4);
  await showBack(nameOf(11));
  expect(screen.getByText(storyOf(nameOf(11)))).toBeInTheDocument();
  expect(screen.queryByText('Not ready.')).not.toBeInTheDocument();
});

test('5a I17 the first group answer shows its content before the next group returns', async () => {
  const groups = pendingGroups();
  const api = openActive(manyCards(6), { 'POST /GetWordContent': groups.route });
  await waitFor(() => expect(api.callsTo('GetWordContent')).toHaveLength(1));

  await act(async () => groups.answers[0](storiesFor(api.callsTo('GetWordContent')[0])));
  await waitFor(() => expect(api.callsTo('GetWordContent')).toHaveLength(2));
  await waitFor(() => expect(api.callsTo('UpdateWordContent')).toHaveLength(5));

  await showBack(nameOf(1));
  expect(screen.getByText(storyOf(nameOf(1)))).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next word' }));
  await skipCards(4);
  await showBack(nameOf(6));
  expect(screen.getByText('Loading content')).toBeInTheDocument();
});

test('5a I15 when the deck is closed, the remaining groups are not sent', async () => {
  const groups = pendingGroups();
  const api = openActive(manyCards(GROUP_CARD_COUNT), { 'POST /GetWordContent': groups.route });
  await waitFor(() => expect(api.callsTo('GetWordContent')).toHaveLength(1));

  cleanup();
  await act(async () => groups.answers[0](storiesFor(api.callsTo('GetWordContent')[0])));
  await act(async () => new Promise((done) => setTimeout(done, 20)));

  expect(api.callsTo('GetWordContent')).toHaveLength(1);
  expect(api.callsTo('UpdateWordContent')).toHaveLength(0);
});
