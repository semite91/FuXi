// Phase 5a section I: reading the stored Word Content.
import { expect, test } from 'vitest';
import { parseWordContent } from './word_content';

const json = (value: unknown) => JSON.stringify(value);

test.each(['story', 'quote', 'film reference'])('5a I5 the text method "%s" gives its title and content', (method) => {
  const stored = json({ method, title: 'A mayfly', content: 'It lives one day.', source_reference: null });

  expect(parseWordContent(stored)).toEqual({ kind: 'text', title: 'A mayfly', content: 'It lives one day.' });
});

test('5a I5 a source reference does not change the text', () => {
  const stored = json({ method: 'story', title: 'T', content: 'C', source_reference: 'Notion / Diary' });

  expect(parseWordContent(stored)).toEqual({ kind: 'text', title: 'T', content: 'C' });
});

test('5a I6 the photo method gives its https image address', () => {
  const stored = json({ method: 'photo', image_url: 'https://images.test/mayfly.jpg' });

  expect(parseWordContent(stored)).toEqual({ kind: 'photo', imageUrl: 'https://images.test/mayfly.jpg' });
});

test('5a I7 the music method gives the song title, artist, address and lyric excerpt', () => {
  const stored = json({
    method: 'music',
    song_title: 'Yesterday',
    artist: 'The Beatles',
    song_url: 'https://music.test/yesterday',
    lyrics_excerpt: 'All my troubles seemed so far away',
  });

  expect(parseWordContent(stored)).toEqual({
    kind: 'music',
    songTitle: 'Yesterday',
    artist: 'The Beatles',
    songUrl: 'https://music.test/yesterday',
    lyricsExcerpt: 'All my troubles seemed so far away',
  });
});

test.each([
  ['http', 'http://images.test/a.jpg'],
  ['javascript', 'javascript:alert(1)'],
  ['data', 'data:image/png;base64,AAAA'],
  ['relative', '/a.jpg'],
  ['not an address', 'mayfly'],
])('5a I9 a %s image address is not available', (_, imageUrl) => {
  expect(parseWordContent(json({ method: 'photo', image_url: imageUrl }))).toEqual({ kind: 'unavailable' });
});

test.each([
  ['http', 'http://music.test/a'],
  ['javascript', 'javascript:alert(1)'],
])('5a I9 a %s song address is not available', (_, songUrl) => {
  const stored = json({ method: 'music', song_title: 'S', artist: 'A', song_url: songUrl, lyrics_excerpt: 'L' });

  expect(parseWordContent(stored)).toEqual({ kind: 'unavailable' });
});

test.each([
  ['plain text', 'A story about a mayfly.'],
  ['a JSON number', '42'],
  ['a JSON string', '"quoted"'],
  ['a JSON array', '[1,2]'],
  ['a JSON object without method', '{"title":"T"}'],
])('5a I10 %s is shown as a story text without a title', (_, stored) => {
  expect(parseWordContent(stored)).toEqual({ kind: 'text', title: null, content: stored });
});

test.each([
  ['an unknown method', { method: 'poem', title: 'T', content: 'C' }],
  ['a method that is not text', { method: 5, title: 'T', content: 'C' }],
  ['a text without content', { method: 'story', title: 'T' }],
  ['a text with an empty title', { method: 'quote', title: ' ', content: 'C' }],
  ['a photo without an address', { method: 'photo' }],
  ['a photo address that is not text', { method: 'photo', image_url: 7 }],
  ['a music without an artist', { method: 'music', song_title: 'S', song_url: 'https://m.test', lyrics_excerpt: 'L' }],
  ['a music with an empty excerpt', { method: 'music', song_title: 'S', artist: 'A', song_url: 'https://m.test', lyrics_excerpt: '' }],
])('5a I11 %s is not available', (_, value) => {
  expect(parseWordContent(json(value))).toEqual({ kind: 'unavailable' });
});

test('an empty content is not available', () => {
  expect(parseWordContent('  ')).toEqual({ kind: 'unavailable' });
});
